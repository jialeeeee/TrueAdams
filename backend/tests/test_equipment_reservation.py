"""Tests for SCRUM-44 "Reserve Equipment for an Event".

Each test names the case it automates in docs/test-cases/SCRUM-44-reserve-equipment.md
(TC-44-xx). Seed data RS-SEED: the USERS in tests/seed_data.py, plus R1-R5 and the
equipment below. The equipment catalogue is shared with real data, so every category
and equipment type here ends with this run's suffix.

Model (db/equipment_reservations.sql): EquipmentReservation
    event_id, requirement_id (NULL once the requirement is removed), resource_id,
    quantity, start_time, end_time (Singapore time, half-open), status ("reserved" or
    "released"), reserved_by_id, reserved_at, released_at, release_reason

Endpoints (JWT required, else 401; the User row is loaded on every request)
    GET  /api/events/<id>/equipment-reservations   the event's coordinator, Technical Support
        200 PAGE = {"event": {"id", "title", "status", "start_time", "end_time", "coordinator"},
                    "reservation_period": {"start_time", "end_time"} | null,
                    "can_reserve", "notice", "message",
                    "requirements": [REQ, ...], "released": [RES, ...]}
        REQ = {"id", "equipment_type", "quantity", "technical_requirements", "technical_note",
               "reserved_quantity", "remaining_quantity", "available_to_reserve",
               "state": "can_reserve" | "fully_reserved" | "none_available", "state_label",
               "options": [{"id", "name", "category", "quantity_available",
                            "reserved_for_other_events", "reserved_for_this_event",
                            "available_to_reserve"}],
               "excluded": [{"id", "name", "reason", "detail"}],
               "reservations": [RES, ...]}
        RES = {"id", "requirement_id", "resource": {"id", "name"}, "quantity", "start_time",
               "end_time", "status", "reserved_by", "reserved_at", "released_at",
               "release_reason"}
    POST /api/events/<id>/equipment-reservations   Technical Support Staff
        {"requirement_id": 1, "items": [{"resource_id": 2, "quantity": 2}, ...]}
        201 {"confirmation", "saved": true, "reservations": [RES, ...],
             "notification": {"in_app", "email_queued"}, ...PAGE}
    Checks, first failure wins: 401 -> 404 (event) -> 403 -> 400 (not a JSON object) ->
    422 (requirement_id) -> 404 (requirement) -> 409 (event not approved) -> 422 (times
    missing) -> 409 (fully reserved) -> 422 {"fields": {"items"}} -> 409 (no suitable
    equipment available, "available_quantity": 0) -> 409 (more than available,
    "available_quantity", "shortfalls") -> 503 {"retryable": true}.
"""

from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app import tasks
from app.models import EquipmentRequirement, Event, Notification, Resource
from tests import seed_data
from tests.base import RUN_ID, AppTestCase

SUFFIX = f" #{RUN_ID}"
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."

# RS-SEED. `organiser` and `coordinator` refer to seed_data USERS keys.
EVENTS = [
    {"key": "R1", "title": "Charity Gala", "status": "approved", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 5, 18, 0),
     "end_time": datetime(2026, 12, 5, 23, 0)},
    # Overlaps R1 from 20:00 to 23:00.
    {"key": "R2", "title": "Winter Concert", "status": "approved", "organiser": "evan",
     "coordinator": "ben", "start_time": datetime(2026, 12, 5, 20, 0),
     "end_time": datetime(2026, 12, 5, 23, 30)},
    # Starts when R1 ends, so it only touches it.
    {"key": "R3", "title": "After-party", "status": "approved", "organiser": "evan",
     "coordinator": "ben", "start_time": datetime(2026, 12, 5, 23, 0),
     "end_time": datetime(2026, 12, 6, 2, 0)},
    {"key": "R4", "title": "Book Fair", "status": "submitted", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 10, 9, 0),
     "end_time": datetime(2026, 12, 10, 17, 0)},
    {"key": "R5", "title": "Spring Fair", "status": "cancelled", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 5, 18, 0),
     "end_time": datetime(2026, 12, 5, 23, 0)},
]
# Each event's requirements, in the order recorded: (type, quantity, technical requirements).
REQUIREMENTS = {
    "R1": [("Wireless microphone", 3, "Lapel"), ("Projector", 1, None),
           ("Hologram projector", 1, None), ("Speaker", 2, None)],
    "R2": [("Wireless microphone", 2, None)],
    "R3": [("Wireless microphone", 2, None)],
    "R4": [("Wireless microphone", 1, None)],
    "R5": [("Wireless microphone", 1, None)],
}
# (name, category, quantity available)
EQUIPMENT = [("Shure SLX-D", "Wireless microphone", 2),
             ("Sennheiser EW-D", "wireless  MICROPHONE", 2),
             ("Epson EB-L", "Projector", 1),
             ("BenQ LU935", "Projector", 2),
             ("JBL EON", "Speaker", None),
             ("Bose S1", "Speaker", 1)]


def _reservation_model():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.models import EquipmentReservation

    return EquipmentReservation


def _unavailability_model():
    from app.models import EquipmentUnavailability

    return EquipmentUnavailability


def base(text):
    """The type or category without this run's suffix."""
    return text[:-len(SUFFIX)] if text.endswith(SUFFIX) else text


class ReservationTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.events = self.seed_events(EVENTS, self.users)
        self.items = {name: self.make_resource(name=name, category=category + SUFFIX,
                                               quantity_available=quantity)
                      for name, category, quantity in EQUIPMENT}
        # The model's default (0) replaces None on insert, so "not recorded" is set after.
        for name, _, quantity in EQUIPMENT:
            if quantity is None:
                self.items[name].quantity_available = None
        self.db.session.commit()
        self.requirements = {}
        for event, rows in REQUIREMENTS.items():
            for equipment_type, quantity, technical in rows:
                row = EquipmentRequirement(event_id=self.events[event].id,
                                           equipment_type=equipment_type + SUFFIX,
                                           quantity=quantity, technical_requirements=technical,
                                           recorded_by_id=self.users["alice"].id)
                self.db.session.add(row)
                self.db.session.commit()
                self.requirements[(event, equipment_type)] = row
        self.db.session.add(_unavailability_model()(
            resource_id=self.items["Epson EB-L"].id, start_time=datetime(2026, 12, 5, 17, 0),
            end_time=datetime(2026, 12, 5, 19, 0), reason="Lamp replacement"))
        self.db.session.commit()
        # Emails are asserted on, never sent.
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------- Calls ----------

    def url(self, event="R1"):
        event_id = self.events[event].id if isinstance(event, str) else event
        return f"/api/events/{event_id}/equipment-reservations"

    def headers(self, user):
        return self.auth_headers(self.users[user])

    def page(self, event="R1", user="hana"):
        response = self.client.get(self.url(event), headers=self.headers(user))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def requirement(self, page, equipment_type):
        return next(r for r in page["requirements"] if base(r["equipment_type"]) == equipment_type)

    def option(self, requirement, name):
        return next(o for o in requirement["options"] if o["name"] == name)

    def body(self, event, equipment_type, *selection):
        """A reservation body: the requirement and (item name, quantity) pairs."""
        return {"requirement_id": self.requirements[(event, equipment_type)].id,
                "items": [{"resource_id": self.items[name].id, "quantity": quantity}
                          for name, quantity in selection]}

    def reserve(self, event, equipment_type, *selection, user="hana"):
        return self.client.post(self.url(event), json=self.body(event, equipment_type, *selection),
                                headers=self.headers(user))

    def reserved(self, event, equipment_type, *selection):
        response = self.reserve(event, equipment_type, *selection)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    # ---------- Reading back ----------

    def rows(self, event=None, status=None):
        model = _reservation_model()
        query = model.query
        if event is not None:
            query = query.filter_by(event_id=self.events[event].id)
        if status is not None:
            query = query.filter_by(status=status)
        self.db.session.expire_all()
        return query.order_by(model.id).all()

    def notifications(self, user):
        self.db.session.expire_all()
        return Notification.query.filter_by(recipient_id=self.users[user].id).all()

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error", "").strip())
        self.assertNotIn("confirmation", body)
        return body

    def assert_nothing_reserved(self, event="R1"):
        self.assertEqual(self.rows(event), [])
        self.assertEqual(self.notifications("alice"), [])
        self.email.assert_not_called()


# ---------- AC1: select an event and view its requirements and reservation period ----------


class ViewTests(ReservationTestCase):
    # TC-44-01 · AC1
    def test_tc_44_01_shows_the_requirements_and_the_reservation_period(self):
        page = self.page()

        self.assertEqual(page["event"]["title"], "Charity Gala")
        self.assertEqual(page["event"]["coordinator"]["id"], self.users["alice"].id)
        self.assertEqual(page["reservation_period"],
                         {"start_time": "2026-12-05T18:00:00", "end_time": "2026-12-05T23:00:00"})
        self.assertEqual(
            [(base(r["equipment_type"]), r["quantity"], r["technical_requirements"])
             for r in page["requirements"]],
            [("Wireless microphone", 3, "Lapel"), ("Projector", 1, None),
             ("Hologram projector", 1, None), ("Speaker", 2, None)])
        self.assertIs(page["can_reserve"], True)
        self.assertIsNone(page["notice"])
        self.assertIn("Lapel", self.requirement(page, "Wireless microphone")["technical_note"])

    # TC-44-02 · AC1, AC2
    def test_tc_44_02_shows_the_suitable_equipment_and_how_much_can_be_reserved(self):
        page = self.page()
        microphones = self.requirement(page, "Wireless microphone")
        projector = self.requirement(page, "Projector")
        speakers = self.requirement(page, "Speaker")

        self.assertEqual({o["name"]: o["available_to_reserve"] for o in microphones["options"]},
                         {"Shure SLX-D": 2, "Sennheiser EW-D": 2})
        self.assertEqual((microphones["reserved_quantity"], microphones["remaining_quantity"],
                          microphones["available_to_reserve"], microphones["state"]),
                         (0, 3, 4, "can_reserve"))
        # The Epson is unavailable during the event; the JBL has no quantity recorded.
        self.assertEqual([o["name"] for o in projector["options"]], ["BenQ LU935"])
        self.assertEqual([e["name"] for e in projector["excluded"]], ["Epson EB-L"])
        self.assertIn("Lamp replacement", projector["excluded"][0]["detail"])
        self.assertEqual([o["name"] for o in speakers["options"]], ["Bose S1"])
        self.assertEqual([e["reason"] for e in speakers["excluded"]], ["quantity_not_recorded"])

    # TC-44-03 · AC1
    def test_tc_44_03_the_coordinator_can_view_but_not_reserve(self):
        page = self.page(user="alice")

        self.assertIs(page["can_reserve"], False)
        self.assertEqual(len(page["requirements"]), 4)

    # TC-44-04 · AC1
    def test_tc_44_04_events_that_are_not_approved_can_be_viewed_but_not_reserved(self):
        submitted, cancelled = self.page("R4"), self.page("R5")

        self.assertIs(submitted["can_reserve"], False)
        self.assertIn("approved", submitted["notice"])
        self.assertIn("submitted", submitted["notice"])
        self.assertIs(cancelled["can_reserve"], False)
        self.assertIn("cancelled", cancelled["notice"])

    # TC-44-05 · AC1
    def test_tc_44_05_who_may_view_and_in_what_order(self):
        ghost = self.make_user(role="tech_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        self.assertEqual(self.client.get(self.url()).status_code, 401)
        body = self.assert_error(self.client.get(self.url(), headers=ghost_headers), 401)
        self.assertEqual(body["error"], SESSION_EXPIRED)
        self.assert_error(self.client.get(self.url(self.missing_id(Event)),
                                          headers=self.headers("hana")), 404)
        for user in ("ben", "dana", "gus", "admin", "farah"):
            with self.subTest(user=user):
                body = self.assert_error(self.client.get(self.url(), headers=self.headers(user)),
                                         403)
                self.assertNotIn("requirements", body)
                self.assertNotIn("Charity Gala", body["error"])

    # TC-44-06 · AC1
    def test_tc_44_06_an_event_with_no_requirements_says_so(self):
        event = self.make_event(organiser=self.users["dana"], status="approved",
                                coordinator_id=self.users["alice"].id)

        page = self.page(event.id)

        self.assertEqual(page["requirements"], [])
        self.assertEqual(page["message"],
                         "No equipment requirements have been recorded for this event.")

    # TC-44-07 · AC1
    def test_tc_44_07_a_failed_load_is_an_error_not_an_empty_page(self):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if "FROM equipment_reservations" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            response = self.client.get(self.url(), headers=self.headers("hana"))
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertNotIn("simulated outage", body["error"])
        self.assertNotIn("requirements", body)


# ---------- AC2 + AC3: reserve the selected equipment; the reservation is recorded ----------


class ReserveTests(ReservationTestCase):
    # TC-44-08 · AC2, AC3
    def test_tc_44_08_a_reservation_records_the_equipment_quantities_period_and_event(self):
        result = self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2),
                               ("Sennheiser EW-D", 1))

        rows = self.rows("R1")
        requirement = self.requirements[("R1", "Wireless microphone")]
        self.assertEqual(
            [(r.requirement_id, r.resource_id, r.quantity, r.start_time, r.end_time, r.status,
              r.reserved_by_id) for r in rows],
            [(requirement.id, self.items["Shure SLX-D"].id, 2, datetime(2026, 12, 5, 18, 0),
              datetime(2026, 12, 5, 23, 0), "reserved", self.users["hana"].id),
             (requirement.id, self.items["Sennheiser EW-D"].id, 1, datetime(2026, 12, 5, 18, 0),
              datetime(2026, 12, 5, 23, 0), "reserved", self.users["hana"].id)])
        self.assertTrue(all(r.reserved_at is not None for r in rows))
        self.assertIs(result["saved"], True)
        self.assertEqual([(r["resource"]["name"], r["quantity"]) for r in result["reservations"]],
                         [("Shure SLX-D", 2), ("Sennheiser EW-D", 1)])

    # TC-44-09 · AC3
    def test_tc_44_09_the_confirmation_names_the_equipment_quantities_period_and_event(self):
        result = self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2),
                               ("Sennheiser EW-D", 1))

        confirmation = result["confirmation"]
        for text in ("2 × Shure SLX-D", "1 × Sennheiser EW-D", "Charity Gala",
                     "2026-12-05 18:00", "2026-12-05 23:00", "Wireless microphone"):
            self.assertIn(text, confirmation)
        microphones = self.requirement(result, "Wireless microphone")
        self.assertEqual((microphones["reserved_quantity"], microphones["remaining_quantity"],
                          microphones["state"]), (3, 0, "fully_reserved"))
        self.assertEqual([(r["resource"]["name"], r["quantity"], r["reserved_by"]["id"])
                          for r in microphones["reservations"]],
                         [("Shure SLX-D", 2, self.users["hana"].id),
                          ("Sennheiser EW-D", 1, self.users["hana"].id)])

    # TC-44-10 · AC2, AC5
    def test_tc_44_10_exactly_the_available_quantity_can_be_reserved(self):
        # Fewer than the requirement needs may be reserved; the rest stays to reserve (A6).
        result = self.reserved("R1", "Speaker", ("Bose S1", 1))

        speakers = self.requirement(result, "Speaker")
        self.assertEqual((speakers["reserved_quantity"], speakers["remaining_quantity"],
                          speakers["available_to_reserve"], speakers["state"]),
                         (1, 1, 0, "none_available"))

    # TC-44-11 · AC2
    def test_tc_44_11_more_can_be_reserved_later_up_to_what_the_requirement_needs(self):
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 1))
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 1), ("Sennheiser EW-D", 1))

        page = self.page()
        microphones = self.requirement(page, "Wireless microphone")
        self.assertEqual((microphones["reserved_quantity"], microphones["state"]),
                         (3, "fully_reserved"))
        self.assertEqual(self.option(microphones, "Shure SLX-D")["reserved_for_this_event"], 2)
        self.assertEqual(self.option(microphones, "Shure SLX-D")["available_to_reserve"], 0)

    # TC-44-12 · AC2
    def test_tc_44_12_a_fully_reserved_requirement_cannot_be_reserved_again(self):
        self.reserved("R1", "Projector", ("BenQ LU935", 1))

        body = self.assert_error(self.reserve("R1", "Projector", ("BenQ LU935", 1)), 409)

        self.assertIn("already fully reserved", body["error"])
        self.assertEqual(len(self.rows("R1")), 1)

    # TC-44-13 · AC2
    def test_tc_44_13_the_selection_is_validated_and_nothing_is_reserved_when_it_is_wrong(self):
        microphones = self.requirements[("R1", "Wireless microphone")].id
        shure = self.items["Shure SLX-D"].id
        cases = {
            "no items": ({"requirement_id": microphones, "items": []}, "Select at least one"),
            "items not a list": ({"requirement_id": microphones, "items": "Shure"},
                                 "Select at least one"),
            "zero": ({"requirement_id": microphones,
                      "items": [{"resource_id": shure, "quantity": 0}]}, "whole number"),
            "fraction": ({"requirement_id": microphones,
                          "items": [{"resource_id": shure, "quantity": 1.5}]}, "whole number"),
            "text": ({"requirement_id": microphones,
                      "items": [{"resource_id": shure, "quantity": "2"}]}, "whole number"),
            "true": ({"requirement_id": microphones,
                      "items": [{"resource_id": shure, "quantity": True}]}, "whole number"),
            "unknown item": ({"requirement_id": microphones,
                              "items": [{"resource_id": self.missing_id(Resource),
                                         "quantity": 1}]}, "was not found"),
            "unsuitable item": ({"requirement_id": microphones,
                                 "items": [{"resource_id": self.items["BenQ LU935"].id,
                                            "quantity": 1}]}, "not suitable"),
            "twice": ({"requirement_id": microphones,
                       "items": [{"resource_id": shure, "quantity": 1},
                                 {"resource_id": shure, "quantity": 1}]}, "more than once"),
            "more than needed": ({"requirement_id": microphones,
                                  "items": [{"resource_id": shure, "quantity": 2},
                                            {"resource_id": self.items["Sennheiser EW-D"].id,
                                             "quantity": 2}]}, "no more than 3"),
        }
        for case, (body, expected) in cases.items():
            with self.subTest(case=case):
                response = self.client.post(self.url(), json=body, headers=self.headers("hana"))
                error = self.assert_error(response, 422)
                self.assertIn(expected, error["fields"]["items"])
        self.assert_nothing_reserved()

    # TC-44-14 · AC2
    def test_tc_44_14_the_requirement_must_be_one_of_the_events(self):
        for requirement_id in (None, "1", True):
            with self.subTest(requirement_id=requirement_id):
                body = self.assert_error(self.client.post(
                    self.url(), json={"requirement_id": requirement_id, "items": []},
                    headers=self.headers("hana")), 422)
                self.assertIn("requirement_id", body["fields"])
        for requirement_id in (self.missing_id(EquipmentRequirement),
                               self.requirements[("R2", "Wireless microphone")].id):
            with self.subTest(requirement_id=requirement_id):
                body = self.assert_error(self.client.post(
                    self.url(), json={"requirement_id": requirement_id,
                                      "items": [{"resource_id": self.items["Shure SLX-D"].id,
                                                 "quantity": 1}]},
                    headers=self.headers("hana")), 404)
                self.assertEqual(body["error"], "Equipment requirement not found.")
        self.assert_nothing_reserved()

    # TC-44-15 · AC2
    def test_tc_44_15_availability_is_checked_again_when_reserving(self):
        page = self.page()
        self.assertEqual(self.option(self.requirement(page, "Wireless microphone"),
                                     "Shure SLX-D")["available_to_reserve"], 2)
        # Meanwhile the overlapping Winter Concert reserves one of the two.
        self.reserved("R2", "Wireless microphone", ("Shure SLX-D", 1))

        body = self.assert_error(self.reserve("R1", "Wireless microphone", ("Shure SLX-D", 2)), 409)

        self.assertEqual(body["shortfalls"], [{"resource_id": self.items["Shure SLX-D"].id,
                                               "name": "Shure SLX-D", "requested_quantity": 2,
                                               "available_quantity": 1}])
        self.assertEqual(self.rows("R1"), [])

    # TC-44-16 · AC2
    def test_tc_44_16_reserving_locks_the_event_requirement_and_equipment_first(self):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sa_event.listen(self.db.engine, "before_cursor_execute", record)
        try:
            self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 1))
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", record)

        locked = [s for s in statements if "FOR UPDATE" in s]
        for table in ("events", "equipment_requirements", "resources"):
            with self.subTest(table=table):
                self.assertTrue(any(f"FROM {table}" in s for s in locked), locked)
        first_insert = next(i for i, s in enumerate(statements)
                            if s.startswith("INSERT INTO equipment_reservations"))
        self.assertTrue(any("FROM resources" in s for s in statements[:first_insert] if "FOR UPDATE" in s))


# ---------- AC4: reserved quantities are deducted for overlapping events ----------


class DeductionTests(ReservationTestCase):
    # TC-44-17 · AC4
    def test_tc_44_17_an_overlapping_event_can_no_longer_reserve_what_was_reserved(self):
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2))

        concert = self.requirement(self.page("R2"), "Wireless microphone")
        shure = self.option(concert, "Shure SLX-D")

        self.assertEqual((shure["quantity_available"], shure["reserved_for_other_events"],
                          shure["available_to_reserve"]), (2, 2, 0))
        self.assertEqual(concert["available_to_reserve"], 2)  # the two Sennheisers

    # TC-44-18 · AC4
    def test_tc_44_18_an_event_that_only_touches_the_period_is_not_affected(self):
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2))

        after_party = self.requirement(self.page("R3"), "Wireless microphone")

        self.assertEqual(self.option(after_party, "Shure SLX-D")["available_to_reserve"], 2)

    # TC-44-19 · AC4
    def test_tc_44_19_the_availability_check_deducts_reservations_for_overlapping_events(self):
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2))

        def check(event):
            response = self.client.get(f"/api/events/{self.events[event].id}/equipment-availability",
                                       headers=self.headers("hana"))
            self.assertEqual(response.status_code, 200, response.get_json())
            return response.get_json()["checks"][0]

        concert, gala = check("R2"), check("R1")
        self.assertEqual(concert["available_quantity"], 2)
        shure = next(s for s in concert["suitable"] if s["name"] == "Shure SLX-D")
        self.assertEqual((shure["quantity_available"], shure["reserved_for_other_events"],
                          shure["available_quantity"]), (2, 2, 0))
        # The gala's own reservation is still available to the gala.
        self.assertEqual(gala["available_quantity"], 4)
        self.assertEqual(check("R3")["available_quantity"], 4)

    # TC-44-20 · AC4, AC5
    def test_tc_44_20_reserving_what_another_event_holds_is_refused_with_the_available_quantity(self):
        self.reserved("R2", "Wireless microphone", ("Shure SLX-D", 2))

        body = self.assert_error(self.reserve("R1", "Wireless microphone", ("Shure SLX-D", 1)), 409)

        self.assertEqual(body["shortfalls"][0]["available_quantity"], 0)
        self.assertEqual(body["available_quantity"], 2)  # the Sennheisers are still free
        self.assertEqual(self.rows("R1"), [])

    # TC-44-21 · AC4
    def test_tc_44_21_requirements_of_one_event_cannot_reserve_the_same_units_twice(self):
        extra = EquipmentRequirement(event_id=self.events["R1"].id,
                                     equipment_type="Wireless microphone" + SUFFIX, quantity=2,
                                     technical_requirements="Handheld",
                                     recorded_by_id=self.users["alice"].id)
        self.db.session.add(extra)
        self.db.session.commit()
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2))

        response = self.client.post(self.url(), json={
            "requirement_id": extra.id,
            "items": [{"resource_id": self.items["Shure SLX-D"].id, "quantity": 1}]},
            headers=self.headers("hana"))

        body = self.assert_error(response, 409)
        self.assertEqual(body["shortfalls"][0]["available_quantity"], 0)


# ---------- AC5 + AC6: more than available, or nothing suitable available ----------


class RefusalTests(ReservationTestCase):
    # TC-44-22 · AC5
    def test_tc_44_22_more_than_available_is_refused_and_shows_the_available_quantity(self):
        body = self.assert_error(self.reserve("R1", "Speaker", ("Bose S1", 2)), 409)

        self.assertIn("Only 1 × Bose S1", body["error"])
        self.assertIn("Nothing was reserved", body["error"])
        self.assertEqual(body["shortfalls"], [{"resource_id": self.items["Bose S1"].id,
                                               "name": "Bose S1", "requested_quantity": 2,
                                               "available_quantity": 1}])
        self.assertEqual(body["available_quantity"], 1)
        self.assert_nothing_reserved()

    # TC-44-23 · AC5
    def test_tc_44_23_one_item_over_its_availability_stops_the_whole_reservation(self):
        self.reserved("R2", "Wireless microphone", ("Sennheiser EW-D", 1))

        body = self.assert_error(self.reserve("R1", "Wireless microphone", ("Shure SLX-D", 1),
                                              ("Sennheiser EW-D", 2)), 409)

        self.assertEqual([s["name"] for s in body["shortfalls"]], ["Sennheiser EW-D"])
        self.assertEqual(self.rows("R1"), [])

    # TC-44-24 · AC5
    def test_tc_44_24_unavailable_equipment_cannot_be_reserved(self):
        body = self.assert_error(self.reserve("R1", "Projector", ("Epson EB-L", 1)), 409)

        self.assertEqual(body["shortfalls"][0]["available_quantity"], 0)
        self.assertEqual(self.rows("R1"), [])

    # TC-44-25 · AC6
    def test_tc_44_25_no_suitable_equipment_means_no_reservation(self):
        page = self.page()
        hologram = self.requirement(page, "Hologram projector")
        self.assertEqual((hologram["state"], hologram["available_to_reserve"], hologram["options"]),
                         ("none_available", 0, []))
        self.assertEqual(hologram["state_label"], "No suitable equipment is available to reserve")

        response = self.client.post(self.url(), json={
            "requirement_id": self.requirements[("R1", "Hologram projector")].id,
            "items": [{"resource_id": self.items["BenQ LU935"].id, "quantity": 1}]},
            headers=self.headers("hana"))

        self.assert_error(response, 422)  # a projector is not a hologram projector
        self.assert_nothing_reserved()

    # TC-44-26 · AC6
    def test_tc_44_26_when_every_suitable_item_is_taken_nothing_can_be_reserved(self):
        # The overlapping Winter Concert needs, and reserves, all four microphones.
        self.requirements[("R2", "Wireless microphone")].quantity = 4
        self.db.session.commit()
        self.reserved("R2", "Wireless microphone", ("Shure SLX-D", 2), ("Sennheiser EW-D", 2))

        microphones = self.requirement(self.page(), "Wireless microphone")
        self.assertEqual((microphones["state"], microphones["available_to_reserve"]),
                         ("none_available", 0))
        body = self.assert_error(self.reserve("R1", "Wireless microphone", ("Shure SLX-D", 1)), 409)
        self.assertIn("No suitable equipment is available", body["error"])
        self.assertEqual(body["available_quantity"], 0)
        self.assertEqual(self.rows("R1"), [])


# ---------- AC7: a failed save confirms nothing and changes nothing ----------


class FailedSaveTests(ReservationTestCase):
    def fail_on(self, prefix):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith(prefix):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        return fail

    # TC-44-27 · AC7
    def test_tc_44_27_a_failed_save_confirms_nothing_and_leaves_reservations_unchanged(self):
        self.reserved("R1", "Projector", ("BenQ LU935", 1))
        self.email.reset_mock()
        before = [(r.id, r.resource_id, r.quantity, r.status) for r in self.rows("R1")]
        notifications_before = len(self.notifications("alice"))

        for prefix in ("INSERT INTO equipment_reservations", "INSERT INTO notifications"):
            fail = self.fail_on(prefix)
            self.db.session.expire_all()
            sa_event.listen(self.db.engine, "before_cursor_execute", fail)
            try:
                response = self.reserve("R1", "Wireless microphone", ("Shure SLX-D", 2),
                                        ("Sennheiser EW-D", 1))
            finally:
                sa_event.remove(self.db.engine, "before_cursor_execute", fail)

            with self.subTest(failing=prefix):
                body = self.assert_error(response, 503)
                self.assertIs(body.get("retryable"), True)
                self.assertIn("not reserved", body["error"])
                self.assertIn("unchanged", body["error"])
                self.assertNotIn("simulated outage", body["error"])
                self.assertEqual([(r.id, r.resource_id, r.quantity, r.status)
                                  for r in self.rows("R1")], before)
                self.assertEqual(len(self.notifications("alice")), notifications_before)
                self.email.assert_not_called()


# ---------- AC8: the event's coordinator is notified ----------


class NotificationTests(ReservationTestCase):
    # TC-44-28 · AC8
    def test_tc_44_28_the_coordinator_is_told_what_was_reserved(self):
        result = self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2),
                               ("Sennheiser EW-D", 1))

        [notification] = self.notifications("alice")
        self.assertEqual((notification.kind, notification.event_id),
                         ("equipment_reserved", self.events["R1"].id))
        for text in ("2 × Shure SLX-D", "1 × Sennheiser EW-D", "Charity Gala", "Wireless microphone"):
            self.assertIn(text, notification.message)
        self.email.assert_called_once()
        to_address, subject, body = self.email.call_args.args
        self.assertEqual(to_address, self.users["alice"].email)
        self.assertIn("Charity Gala", subject)
        self.assertIn("2 × Shure SLX-D", body)
        self.assertEqual(result["notification"], {"in_app": True, "email_queued": True})
        self.assertEqual(self.notifications("hana"), [])

    # TC-44-29 · AC8
    def test_tc_44_29_an_email_queue_failure_does_not_undo_the_reservation(self):
        self.email.side_effect = ConnectionError("broker down")

        result = self.reserved("R1", "Projector", ("BenQ LU935", 1))

        self.assertEqual(result["notification"], {"in_app": True, "email_queued": False})
        self.assertEqual(len(self.rows("R1", status="reserved")), 1)
        self.assertEqual(len(self.notifications("alice")), 1)


# ---------- AC9: cancelling, or changing the requirements, releases the reservation ----------


class ReleaseTests(ReservationTestCase):
    def setUp(self):
        super().setUp()
        self.reserved("R1", "Wireless microphone", ("Shure SLX-D", 2), ("Sennheiser EW-D", 1))
        self.reserved("R1", "Projector", ("BenQ LU935", 1))

    def shure_for_concert(self):
        concert = self.requirement(self.page("R2"), "Wireless microphone")
        return self.option(concert, "Shure SLX-D")["available_to_reserve"]

    # TC-44-30 · AC9
    def test_tc_44_30_cancelling_the_event_releases_its_reservations(self):
        self.assertEqual(self.shure_for_concert(), 0)

        self.events["R1"].status = "cancelled"
        self.db.session.commit()

        rows = self.rows("R1")
        self.assertEqual({r.status for r in rows}, {"released"})
        self.assertTrue(all(r.released_at is not None for r in rows))
        self.assertEqual({r.release_reason for r in rows}, {"The event was cancelled."})
        self.assertEqual(self.shure_for_concert(), 2)
        page = self.page()
        self.assertEqual(len(page["released"]), 3)
        self.assertEqual(self.requirement(page, "Wireless microphone")["reservations"], [])

    # TC-44-31 · AC9
    def test_tc_44_31_changing_a_requirement_releases_only_its_reservations(self):
        microphones = self.requirements[("R1", "Wireless microphone")]

        response = self.client.put(
            f"/api/events/{self.events['R1'].id}/equipment-requirements/{microphones.id}",
            json={"equipment_type": microphones.equipment_type, "quantity": 4,
                  "technical_requirements": "Lapel"},
            headers=self.headers("alice"))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn("reserved equipment was released", response.get_json()["confirmation"])
        released = self.rows("R1", status="released")
        self.assertEqual([r.resource_id for r in released],
                         [self.items["Shure SLX-D"].id, self.items["Sennheiser EW-D"].id])
        self.assertEqual({r.release_reason for r in released},
                         {"The equipment requirement was changed."})
        self.assertEqual([r.resource_id for r in self.rows("R1", status="reserved")],
                         [self.items["BenQ LU935"].id])
        self.assertEqual(self.shure_for_concert(), 2)

    # TC-44-32 · AC9
    def test_tc_44_32_saving_a_requirement_unchanged_releases_nothing(self):
        microphones = self.requirements[("R1", "Wireless microphone")]

        response = self.client.put(
            f"/api/events/{self.events['R1'].id}/equipment-requirements/{microphones.id}",
            json={"equipment_type": microphones.equipment_type, "quantity": 3,
                  "technical_requirements": "Lapel"},
            headers=self.headers("alice"))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.rows("R1", status="released"), [])

    # TC-44-33 · AC9
    def test_tc_44_33_removing_a_requirement_releases_its_reservations_and_keeps_them_as_history(self):
        microphones = self.requirements[("R1", "Wireless microphone")]

        response = self.client.delete(
            f"/api/events/{self.events['R1'].id}/equipment-requirements/{microphones.id}",
            headers=self.headers("alice"))

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn("reserved equipment was released", response.get_json()["confirmation"])
        released = self.rows("R1", status="released")
        self.assertEqual(len(released), 2)
        self.assertTrue(all(r.requirement_id is None for r in released))
        self.assertEqual({r.release_reason for r in released},
                         {"The equipment requirement was removed."})
        self.assertEqual(self.shure_for_concert(), 2)

    # TC-44-34 · AC9
    def test_tc_44_34_changing_the_events_times_releases_its_reservations(self):
        self.events["R1"].start_time = datetime(2026, 12, 5, 19, 0)
        self.db.session.commit()

        self.assertEqual({r.status for r in self.rows("R1")}, {"released"})
        self.assertEqual({r.release_reason for r in self.rows("R1")},
                         {"The event's times were changed."})

    # TC-44-35 · AC9
    def test_tc_44_35_other_changes_to_the_event_release_nothing(self):
        self.events["R1"].title = "Charity Gala 2026"
        self.events["R1"].description = "Black tie"
        self.db.session.commit()

        self.assertEqual({r.status for r in self.rows("R1")}, {"reserved"})


# ---------- Who may reserve, and in what order ----------


class ReserveAccessTests(ReservationTestCase):
    # TC-44-36 · AC1, AC2
    def test_tc_44_36_who_may_reserve_and_in_what_order(self):
        ghost = self.make_user(role="tech_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        body = self.body("R1", "Projector", ("BenQ LU935", 1))

        self.assertEqual(self.client.post(self.url(), json=body).status_code, 401)
        self.assert_error(self.client.post(self.url(), json=body, headers=ghost_headers), 401)
        self.assert_error(self.client.post(self.url(self.missing_id(Event)), json=body,
                                           headers=self.headers("hana")), 404)
        for user in ("alice", "dana", "gus", "admin", "farah"):
            with self.subTest(user=user):
                error = self.assert_error(self.client.post(self.url(), json=body,
                                                           headers=self.headers(user)), 403)
                self.assertIn("Technical Support", error["error"])
        self.assert_error(self.client.post(self.url(), data="not json",
                                           content_type="text/plain",
                                           headers=self.headers("hana")), 400)
        self.assert_nothing_reserved()

    # TC-44-37 · AC1
    def test_tc_44_37_only_approved_events_can_be_reserved_for(self):
        for event in ("R4", "R5"):
            with self.subTest(event=event):
                error = self.assert_error(self.reserve(event, "Wireless microphone",
                                                       ("Shure SLX-D", 1)), 409)
                self.assertIn(self.events[event].status, error["error"])
                self.assertEqual(self.rows(event), [])
