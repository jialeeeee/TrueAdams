"""Tests for SCRUM-42 "Record Equipment Requirements for an Event".

Each test names the case it automates in docs/test-cases/SCRUM-42-equipment-requirements.md
(TC-42-xx). Seed data EQ-SEED: the USERS and LEADS in tests/seed_data.py, plus G1-G5 below.

Model (db/equipment_requirements.sql): EquipmentRequirement, one row per item
    event_id, equipment_type, quantity, technical_requirements (NULL = none recorded),
    status ("requested" | "being_arranged" | "unavailable"), arrangement_note,
    recorded_by_id, recorded_at, last_saved_at, arrangement_updated_by_id,
    arrangement_updated_at   (audit times are naive UTC)

Endpoints (JWT required, else 401; the User row is loaded on every request)
    GET    /api/events/<id>/equipment-requirements          coordinator or tech staff
        200 {"event": {"id", "title", "status", "start_time", "end_time", "coordinator"},
             "organiser_note", "requirements": [REQUIREMENT, ...], "can_edit",
             "can_update_arrangements", "notice", "message"}
    POST   /api/events/<id>/equipment-requirements          the event's coordinator
        201 {"confirmation", "requirement": REQUIREMENT, ...the GET payload}
    PUT    /api/events/<id>/equipment-requirements/<rid>    the event's coordinator
    DELETE /api/events/<id>/equipment-requirements/<rid>    the event's coordinator
        200 {"confirmation", ...the GET payload} (PUT adds "requirement")
    PATCH  /api/events/<id>/equipment-requirements/<rid>/arrangement   tech staff
        body {"status", "note"?}; 200 {"confirmation", "requirement", ...the GET payload}
    GET    /api/events/equipment-requests                   tech staff
        200 {"events": [{"id", "title", "status", "start_time", "end_time", "coordinator",
                         "requirement_count", "status_counts"}], "message"}

    REQUIREMENT = {"id", "equipment_type", "quantity", "technical_requirements", "status",
                   "status_label", "arrangement_note", "recorded_at", "last_saved_at",
                   "arrangement_updated_at", "arrangement_updated_by"}

    Checks, first failure wins: 401 -> 404 event -> 403 -> 404 requirement -> 409
    (cancelled or rejected event) -> 400 (not a JSON object) -> 422 {"error", "fields"}.
    A database failure is 503 {"error", "retryable": true} and changes nothing.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.models import Event, Resource
from tests import seed_data
from tests.base import AppTestCase

URL = "/api/events/{}/equipment-requirements"
REQUESTS_URL = "/api/events/equipment-requests"
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."

ORGANISER_NOTE = "Two wireless microphones and a projector"
MIC = {"equipment_type": "Wireless microphone", "quantity": 2,
       "technical_requirements": "Lapel, with spare batteries"}

# EQ-SEED. `organiser` and `coordinator` refer to seed_data USERS keys.
EVENTS = [
    {"key": "G1", "title": "Charity Gala", "status": "approved", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 5, 18, 0),
     "end_time": datetime(2026, 12, 5, 23, 0), "equipment_requirements": ORGANISER_NOTE},
    {"key": "G2", "title": "Product Launch", "status": "submitted", "organiser": "evan",
     "coordinator": "ben", "start_time": datetime(2026, 11, 20, 14, 0),
     "end_time": datetime(2026, 11, 20, 16, 0)},
    {"key": "G3", "title": "Spring Fair", "status": "cancelled", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 11, 1, 10, 0),
     "end_time": datetime(2026, 11, 1, 16, 0)},
    {"key": "G4", "title": "Winter Fest", "status": "rejected", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 20, 10, 0),
     "end_time": datetime(2026, 12, 20, 16, 0)},
    {"key": "G5", "title": "Tech Talk", "status": "under_review", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 11, 15, 9, 0),
     "end_time": datetime(2026, 11, 15, 11, 0)},
]


def _model():
    # Imported here so the tests fail on behaviour, not on import, until the model exists.
    from app.models import EquipmentRequirement

    return EquipmentRequirement


class EquipmentTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS + seed_data.LEADS)
        self.events = self.seed_events(EVENTS, self.users)

    # ---------- Calls ----------

    def headers(self, user):
        return self.auth_headers(self.users[user])

    def url(self, event, requirement_id=None, suffix=""):
        base = URL.format(self.events[event].id if isinstance(event, str) else event)
        return base + (f"/{requirement_id}" if requirement_id is not None else "") + suffix

    def view(self, event="G1", user="alice", headers=None):
        return self.client.get(self.url(event), headers=headers or self.headers(user))

    def record(self, event="G1", user="alice", body=None, headers=None, **fields):
        body = body if body is not None else {**MIC, **fields}
        return self.client.post(self.url(event), json=body,
                                headers=headers or self.headers(user))

    def edit(self, requirement_id, event="G1", user="alice", body=None, headers=None,
             **fields):
        body = body if body is not None else {**MIC, **fields}
        return self.client.put(self.url(event, requirement_id), json=body,
                               headers=headers or self.headers(user))

    def remove(self, requirement_id, event="G1", user="alice", headers=None):
        return self.client.delete(self.url(event, requirement_id),
                                  headers=headers or self.headers(user))

    def arrange(self, requirement_id, event="G1", user="hana", headers=None, **body):
        return self.client.patch(self.url(event, requirement_id, "/arrangement"), json=body,
                                 headers=headers or self.headers(user))

    def requests_list(self, user="hana", headers=None):
        return self.client.get(REQUESTS_URL, headers=headers or self.headers(user))

    # ---------- Setup and checks ----------

    def recorded_id(self, event="G1", **fields):
        """Record a requirement as the event's coordinator and return its id."""
        coordinator = "ben" if event == "G2" else "alice"
        response = self.record(event, coordinator, **fields)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["requirement"]["id"]

    def insert(self, event, **fields):
        """A requirement saved directly, e.g. against an event that can't be changed."""
        values = {**MIC, "status": "requested", **fields}
        row = _model()(event_id=self.events[event].id,
                       recorded_by_id=self.events[event].coordinator_id, **values)
        self.db.session.add(row)
        self.db.session.commit()
        return row.id

    def recorded(self, event="G1"):
        """What is stored for the event: (type, quantity, technical requirements, status)."""
        model = _model()
        self.db.session.expire_all()
        rows = (model.query.filter_by(event_id=self.events[event].id)
                .order_by(model.id).all())
        return [(r.equipment_type, r.quantity, r.technical_requirements, r.status)
                for r in rows]

    def stored(self, requirement_id):
        self.db.session.expire_all()
        return self.db.session.get(_model(), requirement_id)

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        return body

    def assert_fields(self, response, *fields):
        body = self.assert_error(response, 422)
        self.assertEqual(set(body["fields"]), set(fields), body)
        return body

    def by_id(self, payload, requirement_id):
        return next(r for r in payload["requirements"] if r["id"] == requirement_id)


# ---------- AC1: the coordinator enters equipment requirements ----------


class RecordTests(EquipmentTestCase):
    # TC-42-01 · AC1, AC3
    def test_tc_42_01_records_type_quantity_and_technical_requirements(self):
        response = self.record(body={"equipment_type": "  Wireless   microphone ",
                                     "quantity": 2,
                                     "technical_requirements": " Lapel, with spare batteries "})

        self.assertEqual(response.status_code, 201, response.get_json())
        body = response.get_json()
        requirement = body["requirement"]
        self.assertEqual(requirement["equipment_type"], "Wireless microphone")
        self.assertEqual(requirement["quantity"], 2)
        self.assertEqual(requirement["technical_requirements"], "Lapel, with spare batteries")
        self.assertEqual(requirement["status"], "requested")
        self.assertEqual(requirement["status_label"], "Requested")
        self.assertIn("2 × Wireless microphone", body["confirmation"])
        self.assertEqual(self.recorded(), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "requested")])
        row = self.stored(requirement["id"])
        self.assertEqual(row.recorded_by_id, self.users["alice"].id)
        self.assertIsNotNone(row.recorded_at)

    # TC-42-02 · AC1
    def test_tc_42_02_technical_requirements_are_optional(self):
        projector = self.record(body={"equipment_type": "Projector", "quantity": 1})
        screen = self.record(body={"equipment_type": "Screen", "quantity": 1,
                                   "technical_requirements": "   "})

        self.assertEqual(projector.status_code, 201, projector.get_json())
        self.assertEqual(screen.status_code, 201, screen.get_json())
        self.assertIsNone(projector.get_json()["requirement"]["technical_requirements"])
        self.assertEqual(self.recorded(), [("Projector", 1, None, "requested"),
                                           ("Screen", 1, None, "requested")])

    # TC-42-03 · AC1, AC3
    def test_tc_42_03_several_requirements_listed_in_the_order_recorded(self):
        self.recorded_id()
        self.recorded_id(equipment_type="Projector", quantity=1, technical_requirements=None)
        self.recorded_id(quantity=1, technical_requirements="Handheld")

        listed = self.view().get_json()["requirements"]

        self.assertEqual(
            [(r["equipment_type"], r["quantity"], r["technical_requirements"]) for r in listed],
            [("Wireless microphone", 2, "Lapel, with spare batteries"),
             ("Projector", 1, None),
             ("Wireless microphone", 1, "Handheld")])

    # TC-42-04 · AC1
    def test_tc_42_04_only_the_events_coordinator_can_record_edit_or_remove(self):
        requirement_id = self.recorded_id()
        for user in ("ben", "chloe", "dana", "hana", "gus", "farah", "admin", "lena"):
            with self.subTest(user=user):
                response = self.record(user=user, equipment_type="Projector")
                body = self.assert_error(response, 403)
                self.assertNotIn("Charity Gala", body["error"])
        for user in ("ben", "hana"):
            with self.subTest(user=user, action="edit and remove"):
                self.assert_error(self.edit(requirement_id, user=user, quantity=9), 403)
                self.assert_error(self.remove(requirement_id, user=user), 403)

        self.assertEqual(self.recorded(), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "requested")])

    # TC-42-05 · AC1, AC3
    def test_tc_42_05_the_coordinator_can_edit_and_remove_a_requirement(self):
        requirement_id = self.recorded_id()

        edited = self.edit(requirement_id, quantity=3, technical_requirements="Handheld")
        self.assertEqual(edited.status_code, 200, edited.get_json())
        self.assertEqual(edited.get_json()["requirement"]["quantity"], 3)
        listed = self.view().get_json()["requirements"]
        self.assertEqual([(r["quantity"], r["technical_requirements"]) for r in listed],
                         [(3, "Handheld")])

        removed = self.remove(requirement_id)
        self.assertEqual(removed.status_code, 200, removed.get_json())
        self.assertIn("Wireless microphone", removed.get_json()["confirmation"])
        self.assertEqual(removed.get_json()["requirements"], [])
        self.assertEqual(self.recorded(), [])

    # TC-42-06 · AC1, AC4 (A8)
    def test_tc_42_06_editing_the_details_sends_it_back_to_requested(self):
        requirement_id = self.recorded_id()
        note = "Two lapel mics held at the AV store"
        self.assertEqual(
            self.arrange(requirement_id, status="being_arranged", note=note).status_code, 200)

        unchanged = self.edit(requirement_id)
        self.assertEqual(unchanged.status_code, 200, unchanged.get_json())
        self.assertEqual(unchanged.get_json()["requirement"]["status"], "being_arranged")

        changed = self.edit(requirement_id, quantity=3)
        self.assertEqual(changed.status_code, 200, changed.get_json())
        requirement = changed.get_json()["requirement"]
        self.assertEqual(requirement["status"], "requested")
        self.assertEqual(requirement["arrangement_note"], note)
        self.assertIn("Requested", changed.get_json()["confirmation"])

    # TC-42-07 · AC1 (A4)
    def test_tc_42_07_cancelled_and_rejected_events_cannot_be_changed(self):
        for event, status in (("G3", "cancelled"), ("G4", "rejected")):
            with self.subTest(event=event):
                body = self.assert_error(self.record(event), 409)
                self.assertIn(status, body["error"])
                self.assertEqual(self.recorded(event), [])
        existing = self.insert("G3")
        self.assert_error(self.edit(existing, event="G3", quantity=5), 409)
        self.assert_error(self.remove(existing, event="G3"), 409)
        self.assert_error(self.arrange(existing, event="G3", status="being_arranged"), 409)
        self.assertEqual(self.recorded("G3"), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "requested")])

        self.assertEqual(self.record("G5").status_code, 201)

    # TC-42-08 · AC1
    def test_tc_42_08_signed_out_unknown_event_and_other_events_requirement(self):
        requirement_id = self.recorded_id()
        ghost = self.make_user(role="coordinator")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["alice"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                calls = [
                    self.client.get(self.url("G1"), headers=headers),
                    self.client.post(self.url("G1"), json=MIC, headers=headers),
                    self.client.put(self.url("G1", requirement_id), json=MIC, headers=headers),
                    self.client.delete(self.url("G1", requirement_id), headers=headers),
                    self.client.patch(self.url("G1", requirement_id, "/arrangement"),
                                      json={"status": "being_arranged"}, headers=headers),
                    self.client.get(REQUESTS_URL, headers=headers),
                ]
                for response in calls:
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn("Charity Gala", response.get_data(as_text=True))
        deleted = self.client.get(self.url("G1"), headers=ghost_headers)
        self.assertEqual(deleted.get_json()["error"], SESSION_EXPIRED)

        missing_event = self.record(self.missing_id(Event))
        self.assertEqual(self.assert_error(missing_event, 404)["error"], "Event not found.")

        # G5 is also alice's event, but the requirement belongs to G1.
        for response in (self.edit(requirement_id, event="G5", quantity=9),
                         self.remove(requirement_id, event="G5"),
                         self.arrange(requirement_id, event="G5", status="being_arranged"),
                         self.edit(self.missing_id(_model()), quantity=9)):
            self.assertEqual(self.assert_error(response, 404)["error"],
                             "Equipment requirement not found.")
        self.assertEqual(self.recorded(), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "requested")])


# ---------- AC2: invalid requirements are identified and not saved ----------


class ValidationTests(EquipmentTestCase):
    # TC-42-09 · AC2
    def test_tc_42_09_equipment_type_is_required_and_at_most_100_characters(self):
        without_type = {"quantity": 2}
        for body in (without_type, {**MIC, "equipment_type": None},
                     {**MIC, "equipment_type": ""}, {**MIC, "equipment_type": "   "},
                     {**MIC, "equipment_type": 42}, {**MIC, "equipment_type": "x" * 101}):
            with self.subTest(body=body):
                self.assert_fields(self.record(body=body), "equipment_type")
        self.assertEqual(self.recorded(), [])

        self.assertEqual(self.record(equipment_type="x" * 100).status_code, 201)

    # TC-42-10 · AC2
    def test_tc_42_10_quantity_must_be_a_whole_number_from_1_to_1000(self):
        without_quantity = {"equipment_type": "Projector"}
        self.assert_fields(self.record(body=without_quantity), "quantity")
        for quantity in (None, 0, -1, 1.5, "2", True, 1001):
            with self.subTest(quantity=quantity):
                self.assert_fields(self.record(quantity=quantity), "quantity")
        self.assertEqual(self.recorded(), [])

        self.assertEqual(self.record(quantity=1).status_code, 201)
        self.assertEqual(
            self.record(quantity=1000, technical_requirements="Spares").status_code, 201)

    # TC-42-11 · AC2
    def test_tc_42_11_technical_requirements_must_be_text_up_to_1000_characters(self):
        for value in (5, ["a"], "x" * 1001):
            with self.subTest(value=str(value)[:20]):
                self.assert_fields(self.record(technical_requirements=value),
                                   "technical_requirements")
        self.assertEqual(self.recorded(), [])

        self.assertEqual(self.record(technical_requirements="x" * 1000).status_code, 201)

    # TC-42-12 · AC2, AC3
    def test_tc_42_12_every_problem_is_named_and_the_corrected_entry_saves(self):
        response = self.record(body={"equipment_type": "", "quantity": 0,
                                     "technical_requirements": 7})

        body = self.assert_fields(response, "equipment_type", "quantity",
                                  "technical_requirements")
        for message in body["fields"].values():
            self.assertTrue(message.strip())
        self.assertEqual(self.recorded(), [])

        self.assertEqual(self.record().status_code, 201)
        self.assertEqual(len(self.recorded()), 1)

    # TC-42-13 · AC2 (A5)
    def test_tc_42_13_the_same_requirement_cannot_be_recorded_twice(self):
        self.recorded_id()

        duplicate = self.record(equipment_type="wireless MICROPHONE", quantity=1,
                                technical_requirements="lapel,  with spare batteries")

        body = self.assert_fields(duplicate, "equipment_type")
        self.assertIn("quantity", body["fields"]["equipment_type"])
        handheld = self.recorded_id(technical_requirements="Handheld")
        self.assert_fields(self.edit(handheld), "equipment_type")
        self.assertEqual(self.recorded(), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "requested"),
            ("Wireless microphone", 2, "Handheld", "requested")])

    # TC-42-14 · AC2, AC7
    def test_tc_42_14_an_invalid_edit_leaves_the_requirement_unchanged(self):
        requirement_id = self.recorded_id()

        self.assert_fields(self.edit(requirement_id, quantity=-3), "quantity")

        self.assertEqual(self.recorded(), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "requested")])

    # TC-42-15 · AC2
    def test_tc_42_15_the_body_must_be_a_json_object(self):
        headers = self.headers("alice")
        for label, kwargs in {"no body": {}, "list": {"json": [MIC]},
                              "string": {"json": "Wireless microphone"}}.items():
            with self.subTest(body=label):
                response = self.client.post(self.url("G1"), headers=headers, **kwargs)
                body = self.assert_error(response, 400)
                self.assertEqual(body["error"], "Send the equipment requirement as a JSON object.")
        self.assertEqual(self.recorded(), [])


# ---------- AC3: saved requirements are recorded against the event and viewed ----------


class ViewTests(EquipmentTestCase):
    # TC-42-16 · AC3
    def test_tc_42_16_saved_requirements_are_shown_against_the_event(self):
        requirement_id = self.recorded_id()

        response = self.view(headers=self.auth_headers(self.users["alice"]))

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["event"]["id"], self.events["G1"].id)
        self.assertEqual(body["event"]["title"], "Charity Gala")
        self.assertEqual(body["event"]["status"], "approved")
        self.assertEqual(body["event"]["start_time"], "2026-12-05T18:00:00")
        self.assertEqual(body["event"]["end_time"], "2026-12-05T23:00:00")
        self.assertEqual(body["event"]["coordinator"]["id"], self.users["alice"].id)
        self.assertEqual(body["organiser_note"], ORGANISER_NOTE)
        self.assertIsNone(body["message"])
        requirement = self.by_id(body, requirement_id)
        self.assertEqual(
            {k: requirement[k] for k in ("equipment_type", "quantity", "technical_requirements",
                                         "status", "status_label", "arrangement_note",
                                         "arrangement_updated_by")},
            {"equipment_type": "Wireless microphone", "quantity": 2,
             "technical_requirements": "Lapel, with spare batteries", "status": "requested",
             "status_label": "Requested", "arrangement_note": None,
             "arrangement_updated_by": None})
        self.assertTrue(requirement["recorded_at"])
        self.assertEqual(self.view("G2", "ben").get_json()["requirements"], [])

    # TC-42-17 · AC3
    def test_tc_42_17_an_event_with_no_requirements_says_so(self):
        body = self.view("G5").get_json()

        self.assertEqual(body["requirements"], [])
        self.assertEqual(body["message"], "No equipment requirements have been recorded for this event.")
        self.assertIsNone(body["organiser_note"])

    # TC-42-18 · AC3 (A4)
    def test_tc_42_18_cancelled_events_can_be_viewed_but_not_changed(self):
        self.insert("G3")
        for user in ("alice", "hana"):
            with self.subTest(user=user):
                response = self.view("G3", user)
                self.assertEqual(response.status_code, 200, response.get_json())
                body = response.get_json()
                self.assertEqual(len(body["requirements"]), 1)
                self.assertIs(body["can_edit"], False)
                self.assertIs(body["can_update_arrangements"], False)
                self.assertIn("cancelled", body["notice"])
        self.assertIsNone(self.view("G1").get_json()["notice"])


# ---------- AC4: Technical Support Staff view and update the requirements ----------


class TechnicalSupportTests(EquipmentTestCase):
    # TC-42-19 · AC4
    def test_tc_42_19_technical_support_can_view_any_events_requirements(self):
        requirement_id = self.recorded_id()

        tech = self.view(user="hana")
        coordinator = self.view(user="alice")

        self.assertEqual(tech.status_code, 200, tech.get_json())
        self.by_id(tech.get_json(), requirement_id)
        self.assertEqual((tech.get_json()["can_edit"], tech.get_json()["can_update_arrangements"]),
                         (False, True))
        self.assertEqual((coordinator.get_json()["can_edit"],
                          coordinator.get_json()["can_update_arrangements"]), (True, False))

    # TC-42-20 · AC4
    def test_tc_42_20_technical_support_see_which_events_need_equipment(self):
        arranging = self.recorded_id()
        self.recorded_id(equipment_type="Projector", quantity=1, technical_requirements=None)
        self.arrange(arranging, status="being_arranged")
        self.recorded_id("G2")
        self.insert("G3")

        response = self.requests_list()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertIsNone(body["message"])
        ours = {event.id: key for key, event in self.events.items()}
        listed = [e for e in body["events"] if e["id"] in ours]
        self.assertEqual([ours[e["id"]] for e in listed], ["G2", "G1"])
        gala = listed[1]
        self.assertEqual(gala["title"], "Charity Gala")
        self.assertEqual(gala["coordinator"]["id"], self.users["alice"].id)
        self.assertEqual(gala["start_time"], "2026-12-05T18:00:00")
        self.assertEqual(gala["requirement_count"], 2)
        self.assertEqual(gala["status_counts"],
                         {"requested": 1, "being_arranged": 1, "unavailable": 0})

    # TC-42-21 · AC4
    def test_tc_42_21_technical_support_update_the_arrangement(self):
        requirement_id = self.recorded_id()
        note = "Two lapel mics held at the AV store"

        response = self.arrange(requirement_id, status="being_arranged", note=f"  {note} ")

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn("Being arranged", response.get_json()["confirmation"])
        requirement = self.by_id(self.view(user="alice").get_json(), requirement_id)
        self.assertEqual(requirement["status"], "being_arranged")
        self.assertEqual(requirement["status_label"], "Being arranged")
        self.assertEqual(requirement["arrangement_note"], note)
        self.assertEqual(requirement["arrangement_updated_by"]["id"], self.users["hana"].id)
        self.assertTrue(requirement["arrangement_updated_at"])
        self.assertEqual(self.recorded(), [
            ("Wireless microphone", 2, "Lapel, with spare batteries", "being_arranged")])

    # TC-42-22 · AC4, AC6
    def test_tc_42_22_only_valid_arrangement_statuses_are_accepted(self):
        requirement_id = self.recorded_id()
        for status in ("reserved", "fulfilled", "done", "", None, 3):
            with self.subTest(status=status):
                self.assert_fields(self.arrange(requirement_id, status=status), "status")
        self.assert_fields(self.arrange(requirement_id, note="Held"), "status")
        self.assert_fields(self.arrange(requirement_id, status="being_arranged",
                                        note="x" * 1001), "note")

        self.assertEqual(self.recorded()[0][3], "requested")
        self.assertIsNone(self.stored(requirement_id).arrangement_note)

    # TC-42-23 · AC4 (A9)
    def test_tc_42_23_only_technical_support_update_and_others_cannot_view(self):
        requirement_id = self.recorded_id()
        for user in ("alice", "ben", "dana", "gus", "admin", "lena"):
            with self.subTest(user=user, action="update"):
                self.assert_error(self.arrange(requirement_id, user=user,
                                               status="being_arranged"), 403)
        list_refusal = self.assert_error(self.requests_list(user="alice"), 403)
        self.assertNotIn("events", list_refusal)
        for user in ("ben", "chloe", "dana", "evan", "farah", "gus", "admin", "lena"):
            with self.subTest(user=user, action="view"):
                response = self.view(user=user)
                body = self.assert_error(response, 403)
                self.assertNotIn("requirements", body)
                self.assertNotIn("Wireless microphone", response.get_data(as_text=True))
                self.assertNotIn("Charity Gala", response.get_data(as_text=True))

        self.assertEqual(self.recorded()[0][3], "requested")


# ---------- AC5 and AC6: recording reserves nothing; unavailable stays recorded ----------


class NoReservationTests(EquipmentTestCase):
    # TC-42-24 · AC5
    def test_tc_42_24_recording_does_not_reserve_or_reduce_availability(self):
        microphones = self.make_resource(name="Shure SLX-D", category="Wireless microphone",
                                         quantity_available=4)

        recorded = self.record()
        self.assertEqual(recorded.status_code, 201, recorded.get_json())
        self.assertIn("does not reserve", recorded.get_json()["confirmation"])
        requirement_id = recorded.get_json()["requirement"]["id"]
        responses = [recorded,
                     self.edit(requirement_id, quantity=3),
                     self.arrange(requirement_id, status="being_arranged")]

        for response in responses:
            self.assertEqual(response.status_code // 100, 2, response.get_json())
            requirement = response.get_json()["requirement"]
            self.assertNotIn(requirement["status"], {"reserved", "fulfilled", "confirmed"})
            for word in ("reserved", "fulfilled", "confirmed"):
                self.assertNotIn(word, requirement["status_label"].lower())
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(Resource, microphones.id).quantity_available, 4)

    # TC-42-25 · AC6
    def test_tc_42_25_a_requirement_with_no_suitable_equipment_can_be_recorded(self):
        response = self.record(equipment_type="Hologram projector", quantity=1,
                               technical_requirements=None)

        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["requirement"]["status"], "requested")
        self.assertEqual(self.recorded(), [("Hologram projector", 1, None, "requested")])

    # TC-42-26 · AC6
    def test_tc_42_26_unavailable_stays_recorded_and_is_not_fulfilled(self):
        requirement_id = self.recorded_id(equipment_type="Hologram projector", quantity=1,
                                          technical_requirements=None)

        response = self.arrange(requirement_id, status="unavailable",
                                note="No supplier can provide one")

        self.assertEqual(response.status_code, 200, response.get_json())
        requirement = self.by_id(self.view(user="alice").get_json(), requirement_id)
        self.assertEqual(requirement["status"], "unavailable")
        self.assertEqual(requirement["status_label"], "Suitable equipment unavailable")
        self.assertEqual(self.recorded(), [("Hologram projector", 1, None, "unavailable")])


# ---------- AC7: a failed save changes nothing and says so ----------


class FailureTests(EquipmentTestCase):
    def failing_commit(self):
        return mock.patch.object(self.db.session, "commit",
                                 side_effect=SQLAlchemyError("simulated outage"))

    def assert_unavailable(self, response):
        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("simulated outage", body["error"])
        return body

    # TC-42-27 · AC7
    def test_tc_42_27_a_failed_save_keeps_existing_requirements(self):
        requirement_id = self.recorded_id()
        before = self.recorded()

        with self.failing_commit():
            failed_record = self.record(equipment_type="Projector", quantity=1)
        self.assertIn("unchanged", self.assert_unavailable(failed_record)["error"])
        self.assertEqual(self.recorded(), before)
        with self.failing_commit():
            failed_edit = self.edit(requirement_id, quantity=3)
        self.assert_unavailable(failed_edit)
        self.assertEqual(self.recorded(), before)
        with self.failing_commit():
            failed_remove = self.remove(requirement_id)
        self.assert_unavailable(failed_remove)
        self.assertEqual(self.recorded(), before)

        retry = self.record(equipment_type="Projector", quantity=1)
        self.assertEqual(retry.status_code, 201, retry.get_json())
        self.assertEqual(len(self.recorded()), 2)

    # TC-42-28 · AC7, AC4
    def test_tc_42_28_a_failed_arrangement_update_changes_nothing(self):
        requirement_id = self.recorded_id()

        with self.failing_commit():
            response = self.arrange(requirement_id, status="being_arranged", note="Held")

        self.assert_unavailable(response)
        row = self.stored(requirement_id)
        self.assertEqual((row.status, row.arrangement_note), ("requested", None))

    # TC-42-29 · AC7, AC3
    def test_tc_42_29_a_failed_load_is_a_failure_not_an_empty_list(self):
        self.recorded_id()
        url, alice, hana = self.url("G1"), self.headers("alice"), self.headers("hana")

        # Only reads of the requirements table fail. `events` has a column of the same
        # name (the organiser's note), so the event itself still loads.
        def fail(conn, cursor, statement, parameters, context, executemany):
            if "FROM equipment_requirements" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            view = self.client.get(url, headers=alice)
            listing = self.requests_list(headers=hana)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.assertNotIn("requirements", self.assert_unavailable(view))
        self.assertNotIn("events", self.assert_unavailable(listing))


if __name__ == "__main__":
    unittest.main()
