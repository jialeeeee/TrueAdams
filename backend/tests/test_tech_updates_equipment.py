"""Tests for SCRUM-97 "Technical Support updates an event's equipment requirements".

Each test names the case it automates in
docs/test-cases/SCRUM-97-tech-updates-equipment-requirements.md (TC-97-xx). Seed data TU-SEED:
SCRUM-42's EQ-SEED (tests/test_equipment_requirements.py), SCRUM-96's sam and draft G6
(tests/test_tech_views_equipment.py), plus tom, a second Technical Support member.

The endpoint is SCRUM-42's, see that file's docstring for its contract:
    PATCH /api/events/<id>/equipment-requirements/<rid>/arrangement    Technical Support only
        body {"status", "note"?, "last_saved_at"?}
        401 -> 404 (no such event, or a draft: A6) -> 403 -> 404 requirement
            -> 409 (cancelled or rejected) -> 400/422 -> 409 {"reload": true} (the
            coordinator changed it since last_saved_at: A5) -> 200
        503 {"error", "retryable": true} when it can't be read or saved; nothing changes
"""

import unittest
from datetime import datetime
from unittest import mock

from sqlalchemy.exc import SQLAlchemyError

from app import tasks
from app.models import Event, Notification
from tests.test_equipment_requirements import MIC, _model
from tests.test_tech_views_equipment import PROJECTOR, TechViewTestCase

TECH_ONLY = "Only Technical Support Staff can update equipment arrangements."
NOT_SAVED = ("The arrangement was not saved, and the recorded requirements are unchanged. "
             "Please try again.")
EVENT_NOT_FOUND = "Event not found."
REQUIREMENT_NOT_FOUND = "Equipment requirement not found."
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."
NOTE = "Two lapel mics held at the AV store"

# Everyone in TU-SEED who is not Technical Support, including G1's own coordinator (A7).
REFUSED = ("alice", "ben", "chloe", "dana", "evan", "farah", "gus", "admin", "lena", "sam")


class TechUpdateTestCase(TechViewTestCase):
    def setUp(self):
        super().setUp()
        self.users["tom"] = self.make_user(role="tech_staff")

    def seen(self, requirement_id, event="G1"):
        """The requirement's last_saved_at as Technical Support's page shows it (A5)."""
        page = self.view(event, user="hana").get_json()
        return self.by_id(page, requirement_id)["last_saved_at"]

    def update(self, requirement_id, user="hana", event="G1", **body):
        """An update sent as the page sends it: with the details it showed (A5)."""
        body.setdefault("last_saved_at", self.seen(requirement_id, event))
        return self.arrange(requirement_id, event=event, user=user, **body)

    def row(self, requirement_id):
        model = _model()
        stored = self.stored(requirement_id)
        return {c.key: getattr(stored, c.key) for c in model.__table__.columns}

    def snapshot(self):
        """Everything an update could change: G1's requirements, G1, and notifications."""
        model = _model()
        self.db.session.expire_all()
        rows = (model.query.filter_by(event_id=self.events["G1"].id)
                .order_by(model.id).all())
        event = self.db.session.get(Event, self.events["G1"].id)
        user_ids = [u.id for u in self.users.values()]
        return {
            "requirements": [self.row(r.id) for r in rows],
            "event": {c.key: getattr(event, c.key) for c in Event.__table__.columns},
            "notifications": Notification.query.filter(
                Notification.recipient_id.in_(user_ids)).count(),
        }

    def assert_not_saved(self, response):
        body = self.assert_error(response, 503)
        self.assertEqual(body["error"], NOT_SAVED)
        self.assertIs(body["retryable"], True)
        self.assertNotIn("requirement", body)
        self.assertNotIn("simulated", response.get_data(as_text=True))
        return body

    def failing_commit(self):
        return mock.patch.object(self.db.session, "commit",
                                 side_effect=SQLAlchemyError("simulated outage"))

    def draft_requirement(self):
        """A requirement saved directly against the draft G6 (it can't get one otherwise)."""
        row = _model()(event_id=self.events["G6"].id, recorded_by_id=self.users["dana"].id,
                       status="requested", **MIC)
        self.db.session.add(row)
        self.db.session.commit()
        return row.id


# ---------- AC1: an update is saved with who and when ----------


class UpdateTests(TechUpdateTestCase):
    # TC-97-01 · AC1 (A2, A3)
    def test_tc_97_01_an_update_is_saved_with_who_and_when(self):
        mic_id = self.recorded_id()
        projector_id = self.recorded_id(**PROJECTOR)
        before = self.row(mic_id)
        projector = self.row(projector_id)
        seen = self.seen(mic_id)

        started = datetime.utcnow()
        response = self.update(mic_id, status="being_arranged", note=NOTE, last_saved_at=seen)
        finished = datetime.utcnow()

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertIn("Being arranged", body["confirmation"])
        after = self.row(mic_id)
        self.assertEqual((after["status"], after["arrangement_note"]), ("being_arranged", NOTE))
        self.assertEqual(after["arrangement_updated_by_id"], self.users["hana"].id)
        self.assertTrue(started <= after["arrangement_updated_at"] <= finished,
                        after["arrangement_updated_at"])
        for column in ("equipment_type", "quantity", "technical_requirements", "recorded_at",
                       "recorded_by_id", "last_saved_at"):
            self.assertEqual(after[column], before[column], column)
        requirement = body["requirement"]
        self.assertEqual(requirement["arrangement_updated_by"],
                         {"id": self.users["hana"].id, "email": self.users["hana"].email})
        self.assertEqual(requirement["arrangement_updated_at"],
                         after["arrangement_updated_at"].isoformat())
        self.assertEqual(requirement["last_saved_at"], seen)
        self.assertEqual(self.row(projector_id), projector)

    # TC-97-02 · AC1 (A3, A5)
    def test_tc_97_02_each_update_records_who_and_when(self):
        mic_id = self.recorded_id()
        first = self.update(mic_id, status="being_arranged", note=NOTE)
        self.assertEqual(first.status_code, 200, first.get_json())
        hana_at = self.row(mic_id)["arrangement_updated_at"]

        second = self.update(mic_id, user="tom", status="unavailable",
                             note="Only one lapel mic in stock")

        self.assertEqual(second.status_code, 200, second.get_json())
        row = self.row(mic_id)
        self.assertEqual((row["status"], row["arrangement_note"]),
                         ("unavailable", "Only one lapel mic in stock"))
        self.assertEqual(row["arrangement_updated_by_id"], self.users["tom"].id)
        self.assertGreaterEqual(row["arrangement_updated_at"], hana_at)
        self.assertEqual(second.get_json()["requirement"]["arrangement_updated_by"]["email"],
                         self.users["tom"].email)

    # TC-97-03 · AC1 (A2)
    def test_tc_97_03_every_status_can_be_set_and_the_note_changed(self):
        mic_id = self.recorded_id()
        for status in ("being_arranged", "unavailable", "requested"):
            with self.subTest(status=status):
                response = self.update(mic_id, status=status, note=f"{NOTE} ({status})")
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(self.row(mic_id)["status"], status)

        kept = self.update(mic_id, status="being_arranged")
        self.assertEqual(kept.status_code, 200, kept.get_json())
        self.assertEqual(self.row(mic_id)["arrangement_note"], f"{NOTE} (requested)")
        for cleared in ("   ", None):
            with self.subTest(note=cleared):
                self.update(mic_id, status="being_arranged", note=NOTE)
                response = self.update(mic_id, status="being_arranged", note=cleared)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertIsNone(self.row(mic_id)["arrangement_note"])

    # TC-97-04 · AC1 (A4)
    def test_tc_97_04_an_update_that_changes_nothing_keeps_who_and_when(self):
        mic_id = self.recorded_id()
        self.assertEqual(self.update(mic_id, status="being_arranged", note=NOTE).status_code, 200)
        before = self.row(mic_id)

        for body in ({"status": "being_arranged", "note": f"  {NOTE} "},
                     {"status": "being_arranged"}):
            with self.subTest(body=body):
                response = self.update(mic_id, user="tom", **body)
                self.assertEqual(response.status_code, 200, response.get_json())
                self.assertEqual(response.get_json()["confirmation"],
                                 "No changes were made to the arrangement for "
                                 "2 × Wireless microphone.")
                self.assertEqual(self.row(mic_id), before)
                self.assertEqual(
                    response.get_json()["requirement"]["arrangement_updated_by"]["id"],
                    self.users["hana"].id)

    # TC-97-05 · AC1, AC2 (A5)
    def test_tc_97_05_an_update_for_changed_details_is_refused(self):
        mic_id = self.recorded_id()
        seen = self.seen(mic_id)
        changed = self.edit(mic_id, quantity=5)
        self.assertEqual(changed.status_code, 200, changed.get_json())
        before = self.row(mic_id)

        stale = self.update(mic_id, status="being_arranged", note=NOTE, last_saved_at=seen)

        body = self.assert_error(stale, 409)
        self.assertIs(body.get("reload"), True)
        self.assertIn("not saved", body["error"])
        self.assertIn("5 × Wireless microphone", body["error"])
        self.assertEqual(self.row(mic_id), before)
        self.assertEqual((before["status"], before["arrangement_note"],
                          before["arrangement_updated_by_id"]), ("requested", None, None))

        again = self.update(mic_id, status="being_arranged", note=NOTE)
        self.assertEqual(again.status_code, 200, again.get_json())
        self.assertEqual(self.row(mic_id)["status"], "being_arranged")

    # TC-97-06 · AC1, AC2 (A2)
    def test_tc_97_06_only_the_arrangement_can_be_changed(self):
        mic_id = self.recorded_id()
        details = {k: self.row(mic_id)[k]
                   for k in ("equipment_type", "quantity", "technical_requirements")}

        response = self.update(mic_id, status="being_arranged", equipment_type="Projector",
                               quantity=9, technical_requirements="4K")

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual({k: self.row(mic_id)[k] for k in details}, details)
        before = self.row(mic_id)
        self.assert_fields(self.update(mic_id, status="reserved"), "status")
        self.assert_fields(self.update(mic_id, status="unavailable", note="x" * 1001), "note")
        self.assertEqual(self.row(mic_id), before)


# ---------- AC2: only Technical Support Staff can update; nothing changes ----------


class AccessTests(TechUpdateTestCase):
    # TC-97-07 · AC2 (A7)
    def test_tc_97_07_everyone_else_is_refused_without_details(self):
        mic_id = self.recorded_id()
        seen = self.seen(mic_id)
        for user in REFUSED:
            with self.subTest(user=user):
                response = self.update(mic_id, user=user, status="being_arranged",
                                       last_saved_at=seen)
                body = self.assert_error(response, 403)
                self.assertEqual(body, {"error": TECH_ONLY})
                text = response.get_data(as_text=True)
                for detail in ("Charity Gala", "Wireless microphone"):
                    self.assertNotIn(detail, text)

    # TC-97-08 · AC2 (A7)
    def test_tc_97_08_a_refused_update_changes_nothing(self):
        mic_id = self.recorded_id()
        self.recorded_id(**PROJECTOR)
        self.assertEqual(self.update(mic_id, status="being_arranged", note=NOTE).status_code, 200)
        seen = self.seen(mic_id)
        before = self.snapshot()

        with mock.patch.object(tasks.send_notification_email, "delay") as email:
            for user in REFUSED:
                response = self.update(mic_id, user=user, status="unavailable",
                                       note="Changed by someone else", last_saved_at=seen)
                self.assertEqual(response.status_code, 403, user)

        self.assertEqual(self.snapshot(), before)
        email.assert_not_called()

    # TC-97-09 · AC2 (A7)
    def test_tc_97_09_the_stored_role_decides_on_every_request(self):
        mic_id = self.recorded_id()
        seen = self.seen(mic_id)
        hana, farah = self.headers("hana"), self.headers("farah")
        self.users["hana"].role = "attendee"
        self.users["farah"].role = "tech_staff"
        self.db.session.commit()

        refused = self.arrange(mic_id, headers=hana, status="unavailable", last_saved_at=seen)
        self.assertEqual(self.assert_error(refused, 403)["error"], TECH_ONLY)
        self.assertEqual(self.row(mic_id)["status"], "requested")
        promoted = self.arrange(mic_id, headers=farah, status="being_arranged",
                                last_saved_at=seen)
        self.assertEqual(promoted.status_code, 200, promoted.get_json())
        self.assertEqual(self.row(mic_id)["arrangement_updated_by_id"], self.users["farah"].id)

    # TC-97-10 · AC2 (A6, A7)
    def test_tc_97_10_signed_out_unknown_drafts_and_closed(self):
        mic_id = self.recorded_id()
        projector_id = self.recorded_id(**PROJECTOR)
        draft_id = self.draft_requirement()
        closed_id = self.insert("G3")
        before = self.snapshot()
        ghost = self.make_user(role="tech_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()

        no_token = self.client.patch(self.url("G1", mic_id, "/arrangement"),
                                     json={"status": "being_arranged"})
        self.assertEqual(no_token.status_code, 401)
        deleted = self.arrange(mic_id, headers=ghost_headers, status="being_arranged")
        self.assertEqual(self.assert_error(deleted, 401)["error"], SESSION_EXPIRED)

        for user in ("hana", "farah"):
            with self.subTest(user=user, case="unknown event"):
                body = self.assert_error(self.arrange(mic_id, event=self.missing_id(Event),
                                                      user=user, status="being_arranged"), 404)
                self.assertEqual(body["error"], EVENT_NOT_FOUND)
            with self.subTest(user=user, case="draft"):
                response = self.arrange(draft_id, event="G6", user=user, status="being_arranged")
                self.assertEqual(self.assert_error(response, 404)["error"], EVENT_NOT_FOUND)
                self.assertNotIn("Harbour Lights Festival", response.get_data(as_text=True))

        missing = self.missing_id(_model())
        for requirement_id, event in ((missing, "G1"), (projector_id, "G2")):
            with self.subTest(requirement=requirement_id, event=event):
                body = self.assert_error(self.arrange(requirement_id, event=event,
                                                      status="being_arranged"), 404)
                self.assertEqual(body["error"], REQUIREMENT_NOT_FOUND)
        closed = self.assert_error(self.arrange(closed_id, event="G3", status="being_arranged"),
                                   409)
        self.assertIn("cancelled", closed["error"])
        refused = self.arrange(missing, user="farah", status="being_arranged")
        self.assertEqual(self.assert_error(refused, 403)["error"], TECH_ONLY)

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.row(draft_id)["status"], "requested")
        self.assertEqual(self.row(closed_id)["status"], "requested")


# ---------- AC3: a failed save leaves the requirements unchanged and shows an error ----------


class FailureTests(TechUpdateTestCase):
    # TC-97-11 · AC3 (A8)
    def test_tc_97_11_a_failed_save_changes_nothing(self):
        mic_id = self.recorded_id()
        self.recorded_id(**PROJECTOR)
        self.assertEqual(self.update(mic_id, status="being_arranged", note=NOTE).status_code, 200)
        seen = self.seen(mic_id)
        before = self.snapshot()

        with self.failing_commit():
            response = self.update(mic_id, user="tom", status="unavailable",
                                   note="Only one lapel mic in stock", last_saved_at=seen)

        self.assert_not_saved(response)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.row(mic_id)["arrangement_updated_by_id"], self.users["hana"].id)

    # TC-97-12 · AC3 (A8)
    def test_tc_97_12_a_failed_read_is_a_failure(self):
        mic_id = self.recorded_id()
        hana, seen = self.headers("hana"), self.seen(mic_id)
        url = self.url("G1", mic_id, "/arrangement")  # Before reads start failing.
        body = {"status": "being_arranged", "note": NOTE, "last_saved_at": seen}
        for table in ("events", "equipment_requirements"):
            with self.subTest(table=table):
                stop = self.failing_reads(table)
                response = self.client.patch(url, json=body, headers=hana)
                stop()
                self.assert_not_saved(response)

        self.assertEqual(self.row(mic_id)["status"], "requested")

    # TC-97-13 · AC3 (A8)
    def test_tc_97_13_trying_again_saves_the_update(self):
        mic_id = self.recorded_id()
        seen = self.seen(mic_id)

        with self.failing_commit():
            first = self.update(mic_id, status="being_arranged", note=NOTE, last_saved_at=seen)
        self.assert_not_saved(first)
        self.assertIsNone(self.row(mic_id)["arrangement_updated_at"])

        again = self.update(mic_id, status="being_arranged", note=NOTE, last_saved_at=seen)

        self.assertEqual(again.status_code, 200, again.get_json())
        row = self.row(mic_id)
        self.assertEqual((row["status"], row["arrangement_note"], row["arrangement_updated_by_id"]),
                         ("being_arranged", NOTE, self.users["hana"].id))
        self.assertIsNotNone(row["arrangement_updated_at"])


if __name__ == "__main__":
    unittest.main()
