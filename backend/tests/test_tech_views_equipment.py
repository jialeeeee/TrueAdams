"""Tests for SCRUM-96 "Technical Support views an event's equipment requirements".

Each test names the case it automates in
docs/test-cases/SCRUM-96-tech-views-equipment-requirements.md (TC-96-xx). Seed data TS-SEED:
SCRUM-42's EQ-SEED (tests/test_equipment_requirements.py) plus sam (Safety Officer) and the
draft G6 below.

The endpoint is SCRUM-42's, see that file's docstring for its contract:
    GET /api/events/<id>/equipment-requirements    Technical Support or the event's coordinator
        401 -> 404 (no such event, or a draft: A3) -> 403 (anyone else) -> 200
        503 {"error", "retryable": true} when the event or its requirements can't be read
"""

import unittest
from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app import tasks
from app.models import Event, Notification
from tests.test_equipment_requirements import MIC, ORGANISER_NOTE, EquipmentTestCase, _model

VIEW_DENIED = "You are not allowed to view this event's equipment requirements."
NOT_LOADED = "The equipment requirements could not be loaded. Please try again."
EVENT_NOT_FOUND = "Event not found."
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."

PROJECTOR = {"equipment_type": "Projector", "quantity": 1, "technical_requirements": None}
DRAFT_NOTE = "Smoke machine and strobe lights"
DRAFT = {"key": "G6", "title": "Harbour Lights Festival", "status": "draft", "organiser": "dana",
         "coordinator": None, "start_time": datetime(2026, 12, 12, 19, 0),
         "end_time": datetime(2026, 12, 12, 22, 0), "equipment_requirements": DRAFT_NOTE}

# Everyone in TS-SEED who is neither Technical Support nor G1's coordinator (A2).
REFUSED = ("ben", "chloe", "dana", "evan", "farah", "gus", "admin", "lena", "sam")


class TechViewTestCase(EquipmentTestCase):
    def setUp(self):
        super().setUp()
        self.users["sam"] = self.make_user(role="safety_officer")
        self.events.update(self.seed_events([DRAFT], self.users))

    def assert_unavailable(self, response):
        body = self.assert_error(response, 503)
        self.assertEqual(body["error"], NOT_LOADED)
        self.assertIs(body["retryable"], True)
        for key in ("requirements", "event", "message"):
            self.assertNotIn(key, body)
        self.assertNotIn("simulated", response.get_data(as_text=True))
        return body

    def failing_reads(self, table):
        """While active, every read from `table` fails as if the database were down."""
        def fail(conn, cursor, statement, parameters, context, executemany):
            if f"FROM {table}" in statement:
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        def stop():
            if sa_event.contains(self.db.engine, "before_cursor_execute", fail):
                sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        self.addCleanup(stop)  # Even if the test fails before stopping it.
        return stop


# ---------- AC1: Technical Support open an event's requirements and see them ----------


class OpenTests(TechViewTestCase):
    # TC-96-01 · AC1 (A4)
    def test_tc_96_01_technical_support_see_types_quantities_and_technical_requirements(self):
        mic_id = self.recorded_id()
        projector_id = self.recorded_id(**PROJECTOR)

        response = self.view(user="hana")

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["event"]["id"], self.events["G1"].id)
        self.assertEqual(body["event"]["title"], "Charity Gala")
        self.assertEqual(body["event"]["status"], "approved")
        self.assertEqual((body["event"]["start_time"], body["event"]["end_time"]),
                         ("2026-12-05T18:00:00", "2026-12-05T23:00:00"))
        self.assertEqual(body["event"]["coordinator"]["id"], self.users["alice"].id)
        self.assertEqual(body["organiser_note"], ORGANISER_NOTE)
        self.assertEqual(
            [(r["id"], r["equipment_type"], r["quantity"], r["technical_requirements"],
              r["status_label"]) for r in body["requirements"]],
            [(mic_id, "Wireless microphone", 2, "Lapel, with spare batteries", "Requested"),
             (projector_id, "Projector", 1, None, "Requested")])
        self.assertEqual((body["can_update_arrangements"], body["can_edit"]), (True, False))
        self.assertIsNone(body["message"])

    # TC-96-02 · AC1 (A3)
    def test_tc_96_02_every_event_that_has_left_draft_can_be_opened(self):
        for key in ("G1", "G2", "G5"):
            self.recorded_id(key)
        for key in ("G3", "G4"):
            self.insert(key)

        for key in ("G1", "G2", "G5", "G3", "G4"):
            with self.subTest(event=key):
                response = self.view(key, user="hana")
                self.assertEqual(response.status_code, 200, response.get_json())
                body = response.get_json()
                self.assertEqual(body["event"]["id"], self.events[key].id)
                self.assertEqual([(r["equipment_type"], r["quantity"])
                                  for r in body["requirements"]],
                                 [("Wireless microphone", 2)])
                closed = self.events[key].status in ("cancelled", "rejected")
                self.assertEqual(body["can_update_arrangements"], not closed)
                if closed:
                    self.assertIn(self.events[key].status, body["notice"])
                else:
                    self.assertIsNone(body["notice"])

    # TC-96-03 · AC1 (A1)
    def test_tc_96_03_each_listed_event_opens_with_its_requirements(self):
        self.recorded_id()
        self.recorded_id(**PROJECTOR)
        self.recorded_id("G2")

        listing = self.requests_list()

        self.assertEqual(listing.status_code, 200, listing.get_json())
        ours = {self.events["G1"].id, self.events["G2"].id}
        listed = [e for e in listing.get_json()["events"] if e["id"] in ours]
        self.assertEqual({e["id"] for e in listed}, ours)
        for entry in listed:
            with self.subTest(event=entry["title"]):
                response = self.view(entry["id"], user="hana")
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["event"]["title"], entry["title"])
                self.assertEqual(len(response.get_json()["requirements"]),
                                 entry["requirement_count"])

    # TC-96-04 · AC1 (A4)
    def test_tc_96_04_technical_support_see_what_has_been_arranged(self):
        mic_id = self.recorded_id()
        note = "Two lapel mics held at the AV store"
        self.assertEqual(self.arrange(mic_id, status="being_arranged", note=note).status_code,
                         200)

        mic = self.by_id(self.view(user="hana").get_json(), mic_id)

        self.assertEqual((mic["equipment_type"], mic["quantity"], mic["technical_requirements"]),
                         ("Wireless microphone", 2, "Lapel, with spare batteries"))
        self.assertEqual((mic["status"], mic["status_label"]), ("being_arranged", "Being arranged"))
        self.assertEqual(mic["arrangement_note"], note)
        self.assertEqual(mic["arrangement_updated_by"]["id"], self.users["hana"].id)
        self.assertTrue(mic["arrangement_updated_at"])

    # TC-96-05 · AC1, AC2 (A3)
    def test_tc_96_05_a_drafts_equipment_requirements_are_not_found(self):
        unknown = self.view(self.missing_id(Event), user="hana")
        self.assertEqual(self.assert_error(unknown, 404)["error"], EVENT_NOT_FOUND)

        for user in ("hana", "dana"):
            with self.subTest(user=user):
                response = self.view("G6", user=user)
                body = self.assert_error(response, 404)
                self.assertEqual(body, unknown.get_json())
                text = response.get_data(as_text=True)
                for detail in ("Harbour Lights Festival", DRAFT_NOTE, "2026-12-12"):
                    self.assertNotIn(detail, text)


# ---------- AC2: only Technical Support Staff can view; nothing changes ----------


class AccessTests(TechViewTestCase):
    # TC-96-06 · AC2 (A2, A5)
    def test_tc_96_06_everyone_else_is_refused_without_details(self):
        self.recorded_id()
        for user in REFUSED:
            with self.subTest(user=user):
                response = self.view(user=user)
                body = self.assert_error(response, 403)
                self.assertEqual(body["error"], VIEW_DENIED)
                self.assertNotIn("requirements", body)
                text = response.get_data(as_text=True)
                for detail in ("Charity Gala", "Wireless microphone", ORGANISER_NOTE):
                    self.assertNotIn(detail, text)

    # TC-96-07 · AC2 (A5)
    def test_tc_96_07_a_refused_view_changes_nothing(self):
        self.recorded_id()
        arranged = self.recorded_id(**PROJECTOR)
        self.arrange(arranged, status="being_arranged", note="Held at the AV store")
        before = self.snapshot()

        with mock.patch.object(tasks.send_notification_email, "delay") as email:
            for user in REFUSED:
                self.assertEqual(self.view(user=user).status_code, 403, user)
            self.assertEqual(self.view(user="hana").status_code, 200)

        self.assertEqual(self.snapshot(), before)
        email.assert_not_called()

    def snapshot(self):
        """Everything a view could change: the requirements, the event, and notifications."""
        model = _model()
        self.db.session.expire_all()
        columns = [c.key for c in model.__table__.columns]
        rows = (model.query.filter_by(event_id=self.events["G1"].id)
                .order_by(model.id).all())
        event = self.db.session.get(Event, self.events["G1"].id)
        user_ids = [u.id for u in self.users.values()]
        return {
            "requirements": [{c: getattr(r, c) for c in columns} for r in rows],
            "event": {c.key: getattr(event, c.key) for c in Event.__table__.columns},
            "notifications": Notification.query.filter(
                Notification.recipient_id.in_(user_ids)).count(),
        }

    # TC-96-08 · AC2 (A2, A5)
    def test_tc_96_08_the_stored_role_decides_on_every_request(self):
        self.recorded_id()
        hana, farah = self.headers("hana"), self.headers("farah")
        self.users["hana"].role = "attendee"
        self.users["farah"].role = "tech_staff"
        self.db.session.commit()

        self.assertEqual(self.assert_error(self.view(headers=hana), 403)["error"], VIEW_DENIED)
        promoted = self.view(headers=farah)
        self.assertEqual(promoted.status_code, 200, promoted.get_json())
        self.assertEqual(len(promoted.get_json()["requirements"]), 1)

        alice = self.headers("alice")
        self.events["G1"].coordinator_id = self.users["ben"].id
        self.db.session.commit()
        self.assertEqual(self.assert_error(self.view(headers=alice), 403)["error"], VIEW_DENIED)

    # TC-96-09 · AC2
    def test_tc_96_09_signed_out_users_and_unknown_events(self):
        self.recorded_id()
        ghost = self.make_user(role="tech_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        no_token = self.client.get(self.url("G1"))
        self.assertEqual(no_token.status_code, 401)
        deleted = self.view(headers=ghost_headers)
        self.assertEqual(self.assert_error(deleted, 401)["error"], SESSION_EXPIRED)
        for response in (no_token, deleted):
            self.assertNotIn("Charity Gala", response.get_data(as_text=True))

        missing = self.missing_id(Event)
        for user in ("hana", "farah"):
            with self.subTest(user=user):
                body = self.assert_error(self.view(missing, user=user), 404)
                self.assertEqual(body["error"], EVENT_NOT_FOUND)


# ---------- AC3: a failed load explains why and offers a retry ----------


class FailureTests(TechViewTestCase):
    # TC-96-10 · AC3 (A6)
    def test_tc_96_10_a_failed_read_of_the_requirements_is_a_failure(self):
        self.recorded_id()
        hana, url = self.headers("hana"), self.url("G1")  # Before reads start failing.
        # `events` has a column of the same name (the organiser's note), so the event
        # itself still loads; only the requirements table fails.
        stop = self.failing_reads("equipment_requirements")
        response = self.client.get(url, headers=hana)
        stop()

        self.assert_unavailable(response)

    # TC-96-11 · AC3 (A6)
    def test_tc_96_11_a_failed_read_of_the_event_is_a_failure(self):
        self.recorded_id()
        hana, url = self.headers("hana"), self.url("G1")  # Before reads start failing.
        stop = self.failing_reads("events")
        response = self.client.get(url, headers=hana)
        stop()

        self.assert_unavailable(response)

    # TC-96-12 · AC3 (A6)
    def test_tc_96_12_trying_again_loads_the_requirements(self):
        self.recorded_id()
        self.recorded_id(**PROJECTOR)
        hana, url = self.headers("hana"), self.url("G1")  # Before reads start failing.
        stop = self.failing_reads("equipment_requirements")
        first = self.client.get(url, headers=hana)
        stop()

        again = self.view(headers=hana)

        self.assert_unavailable(first)
        self.assertEqual(again.status_code, 200, again.get_json())
        self.assertEqual([(r["equipment_type"], r["quantity"], r["technical_requirements"])
                          for r in again.get_json()["requirements"]],
                         [tuple(MIC.values()), tuple(PROJECTOR.values())])


if __name__ == "__main__":
    unittest.main()
