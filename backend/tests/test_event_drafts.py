"""Tests for SCRUM-29 "Save and Resume a Draft Event Request".

Each test names the case it automates from
docs/test-cases/SCRUM-29-draft-event-request.md (TC-29-nn) and the acceptance
criteria it checks. Assumptions A1-A10 and questions Q1-Q6 are defined there.

Model (db/event_drafts.sql)
    Event.start_time, Event.end_time   now nullable, so a draft can leave them empty
    New nullable Event columns:
        purpose, venue_requirements, accessibility_needs,
        equipment_requirements              Text
        expected_attendance                 Integer (>= 1)
        registration_required               Boolean
        last_saved_at, submitted_at         DateTime (naive UTC)

Endpoints (JWT required, else 401; unknown request -> 404; not the caller's -> 403;
already submitted -> 409)
    POST /api/events/drafts              201 draft          (organisers only)
    GET  /api/events/drafts              200 {"drafts": [{"id", "title", "status",
                                               "last_saved_at"}], "message"}
    GET  /api/events/drafts/<id>         200 draft
    PUT  /api/events/drafts/<id>         200 draft          only the fields sent change
    POST /api/events/drafts/<id>/submit  200 request, status "submitted"
                                         400 {"error", "missing": [...]} or {"error", "field"}
    draft = {"id", "status", <DRAFT_FIELDS>, "created_at", "last_saved_at",
             "submitted_at", "missing_for_submission": [...]}
    Field errors are 400 {"error", "field"}. Failed saves are 503 {"error", "retryable": true}.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event
from tests import seed_data
from tests.base import AppTestCase

DRAFTS_URL = "/api/events/drafts"

DRAFT_FIELDS = [
    "title", "purpose", "description", "start_time", "end_time", "expected_attendance",
    "venue_requirements", "accessibility_needs", "equipment_requirements",
    "registration_required",
]
REQUIRED_FOR_SUBMISSION = [
    "title", "purpose", "description", "start_time", "end_time", "expected_attendance",
    "venue_requirements", "registration_required",
]

COMPLETE = {
    "title": "Winter Networking Night",
    "purpose": "Connect alumni working in tech",
    "description": "An evening of short talks followed by networking.",
    "start_time": datetime(2026, 12, 3, 18, 0),
    "end_time": datetime(2026, 12, 3, 21, 0),
    "expected_attendance": 80,
    "venue_requirements": "Theatre layout for 80 with a small stage",
    "accessibility_needs": "Wheelchair access to the stage",
    "equipment_requirements": "Projector and two wireless microphones",
    "registration_required": True,
}

# DR-SEED. `organiser` refers to seed_data.USERS keys.
DRAFTS = {
    "D1": {"organiser": "dana", "status": "draft",
           "last_saved_at": datetime(2026, 9, 20, 10, 0),
           "title": "Harbour Lights Festival", "purpose": "Celebrate the harbour's reopening",
           "start_time": datetime(2026, 12, 12, 17, 0), "expected_attendance": 250},
    "D2": {"organiser": "dana", "status": "draft",
           "last_saved_at": datetime(2026, 9, 25, 16, 30), **COMPLETE},
    "D3": {"organiser": "evan", "status": "draft",
           "last_saved_at": datetime(2026, 9, 22, 9, 0), "title": "Product Launch Planning"},
    "S1": {"organiser": "dana", "status": "submitted",
           "last_saved_at": datetime(2026, 9, 1, 12, 0),
           "submitted_at": datetime(2026, 9, 1, 12, 0),
           **{**COMPLETE, "title": "Charity Gala"}},
}


def api(value):
    """A stored value as the API sends it."""
    return value.isoformat() if isinstance(value, datetime) else value


def as_datetime(value):
    return datetime.fromisoformat(value)


class DraftTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.drafts = {}
        for key, row in DRAFTS.items():
            fields = {k: v for k, v in row.items() if k != "organiser"}
            event = Event(organiser_id=self.users[row["organiser"]].id, **fields)
            self.db.session.add(event)
            self.drafts[key] = event
        self.db.session.commit()

    # ---------- Requests ----------

    def headers(self, user_key="dana"):
        return self.auth_headers(self.users[user_key])

    def url(self, key):
        return f"{DRAFTS_URL}/{self.drafts[key].id}"

    def create(self, body, as_user="dana"):
        return self.client.post(DRAFTS_URL, json=body, headers=self.headers(as_user))

    def save(self, key, body, as_user="dana"):
        return self.client.put(self.url(key), json=body, headers=self.headers(as_user))

    def open(self, key, as_user="dana"):
        return self.client.get(self.url(key), headers=self.headers(as_user))

    def submit(self, key, as_user="dana"):
        return self.client.post(f"{self.url(key)}/submit", headers=self.headers(as_user))

    def listed(self, as_user="dana"):
        response = self.client.get(DRAFTS_URL, headers=self.headers(as_user))
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    # ---------- Reading what was saved ----------

    def stored(self, key_or_id):
        self.db.session.expire_all()
        event_id = self.drafts[key_or_id].id if key_or_id in self.drafts else key_or_id
        event = self.db.session.get(Event, event_id)
        return {c.name: getattr(event, c.name) for c in Event.__table__.columns}

    def request_count(self, user_key="dana"):
        self.db.session.expire_all()
        return Event.query.filter_by(organiser_id=self.users[user_key].id).count()

    # ---------- Assertions ----------

    def assert_error(self, response, status_code, field=None):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        if field is not None:
            self.assertEqual(body.get("field"), field)
        return body


# ---------- AC1: save a request with incomplete information ----------


class SaveIncompleteTests(DraftTestCase):
    # TC-29-01 · AC1, AC2 — a new draft with only an event name.
    def test_save_a_new_draft_with_only_an_event_name(self):
        before = self.request_count()
        started = datetime.utcnow()

        response = self.create({"title": "Spring Garden Party"})

        self.assertEqual(response.status_code, 201, response.get_json())
        body = response.get_json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["title"], "Spring Garden Party")
        for field in DRAFT_FIELDS[1:]:
            with self.subTest(field=field):
                self.assertIsNone(body[field])
        self.assertIsNone(body["submitted_at"])
        self.assertGreaterEqual(as_datetime(body["last_saved_at"]), started)
        stored = self.stored(body["id"])
        self.assertEqual((stored["organiser_id"], stored["status"]),
                         (self.users["dana"].id, "draft"))
        self.assertEqual(self.request_count(), before + 1)

    # TC-29-02 · AC1 — a partly completed draft keeps exactly what was entered.
    def test_save_a_partly_completed_draft(self):
        response = self.create({
            "title": "Spring Garden Party", "purpose": "Annual staff social",
            "expected_attendance": 120, "start_time": "2027-03-20T15:00",
        })

        self.assertEqual(response.status_code, 201, response.get_json())
        stored = self.stored(response.get_json()["id"])
        self.assertEqual(stored["purpose"], "Annual staff social")
        self.assertEqual(stored["expected_attendance"], 120)
        self.assertEqual(stored["start_time"], datetime(2027, 3, 20, 15, 0))
        for field in ("description", "end_time", "venue_requirements",
                      "accessibility_needs", "equipment_requirements",
                      "registration_required"):
            with self.subTest(field=field):
                self.assertIsNone(stored[field])

    # TC-29-03 · AC1, AC5 — an event name is required.
    def test_an_event_name_is_required(self):
        before = self.request_count()
        for label, body in {"missing": {"purpose": "No name"}, "empty": {"title": ""},
                            "blank": {"title": "   "}, "null": {"title": None}}.items():
            with self.subTest(title=label):
                self.assert_error(self.create(body), 400, field="title")
        self.assertEqual(self.request_count(), before)

        saved = self.stored("D1")
        self.assert_error(self.save("D1", {"title": ""}), 400, field="title")
        self.assertEqual(self.stored("D1"), saved)

    # TC-29-04 · AC1, AC5 (boundary) — values of the wrong kind are refused.
    def test_values_of_the_wrong_kind_are_refused(self):
        cases = [
            ("expected_attendance", 0), ("expected_attendance", -5),
            ("expected_attendance", 12.5), ("expected_attendance", "many"),
            ("expected_attendance", True),
            ("start_time", "tomorrow"), ("start_time", "2027-02-30T10:00"),
            ("registration_required", "yes"), ("purpose", 42),
        ]
        saved = self.stored("D1")
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assert_error(self.save("D1", {field: value}), 400, field=field)
                self.assert_error(self.create({"title": "New", field: value}), 400, field=field)
        self.assertEqual(self.stored("D1"), saved)

        with self.subTest(case="unknown field"):
            self.assert_error(self.save("D1", {"budget": 5000}), 400, field="budget")
        with self.subTest(case="not JSON"):
            response = self.client.put(self.url("D1"), data="title=New",
                                       headers=self.headers())
            self.assert_error(response, 400)
        self.assertEqual(self.stored("D1"), saved)

        with self.subTest(case="attendance of 1 is accepted"):
            self.assertEqual(self.save("D1", {"expected_attendance": 1}).status_code, 200)

    # TC-29-05 · AC1 (A3/Q2) — only organisers can create drafts.
    def test_only_organisers_can_create_drafts(self):
        before = self.db.session.query(Event).count()
        for key in ("alice", "admin", "farah", "gus", "hana"):
            with self.subTest(user=key):
                self.assert_error(self.create({"title": "Not mine"}, as_user=key), 403)
        self.db.session.expire_all()
        self.assertEqual(self.db.session.query(Event).count(), before)

    # TC-29-06 · AC1-AC6 — a valid session is required.
    def test_a_valid_session_is_required(self):
        ghost = self.make_user(role="organiser")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(
            identity=str(self.users["dana"].id), expires_delta=timedelta(seconds=-1)
        )
        sessions = {"no token": {}, "expired token": {"Authorization": f"Bearer {expired}"},
                    "deleted user": ghost_headers}
        calls = {
            "create": ("POST", DRAFTS_URL, {"title": "X"}),
            "list": ("GET", DRAFTS_URL, None),
            "open": ("GET", self.url("D1"), None),
            "save": ("PUT", self.url("D1"), {"title": "X"}),
            "submit": ("POST", f"{self.url('D1')}/submit", None),
        }
        saved = self.stored("D1")
        for session, headers in sessions.items():
            for call, (method, url, body) in calls.items():
                with self.subTest(session=session, call=call):
                    response = self.client.open(url, method=method, json=body, headers=headers)
                    self.assertEqual(response.status_code, 401)
        self.assertEqual(self.stored("D1"), saved)


# ---------- AC2: status Draft and last-saved date and time ----------


class DraftStatusTests(DraftTestCase):
    # TC-29-07 · AC2 — a saved request is a Draft with its last-saved time everywhere.
    def test_saved_request_is_a_draft_with_its_last_saved_time(self):
        started = datetime.utcnow()
        created = self.create({"title": "Spring Garden Party"}).get_json()
        finished = datetime.utcnow()

        opened = self.client.get(f"{DRAFTS_URL}/{created['id']}",
                                 headers=self.headers()).get_json()
        in_list = next(d for d in self.listed()["drafts"] if d["id"] == created["id"])

        saved_at = as_datetime(created["last_saved_at"])
        self.assertTrue(started <= saved_at <= finished)
        for body in (created, opened, in_list):
            self.assertEqual(body["status"], "draft")
            self.assertEqual(body["last_saved_at"], created["last_saved_at"])

    # TC-29-08 · AC2, AC4 (boundary) — the last-saved time moves forward with each save.
    def test_last_saved_time_moves_forward_with_each_save(self):
        first = as_datetime(self.save("D1", {"description": "First"}).get_json()["last_saved_at"])
        second = as_datetime(self.save("D1", {"description": "Second"}).get_json()["last_saved_at"])

        self.assertGreater(first, DRAFTS["D1"]["last_saved_at"])
        # Not strictly later: two saves can fall within one tick of a coarse clock.
        self.assertGreaterEqual(second, first)
        self.assertEqual(self.stored("D1")["last_saved_at"], second)

    # TC-29-09 · AC2, AC3 — the drafts list shows only the caller's own drafts.
    def test_drafts_list(self):
        body = self.listed("dana")
        own = {self.drafts[k].id: k for k in DRAFTS}
        dana_listed = [own[d["id"]] for d in body["drafts"] if d["id"] in own]
        self.assertEqual(dana_listed, ["D2", "D1"])
        self.assertIsNone(body["message"])
        d1 = next(d for d in body["drafts"] if d["id"] == self.drafts["D1"].id)
        self.assertEqual(d1, {"id": self.drafts["D1"].id, "title": "Harbour Lights Festival",
                              "status": "draft",
                              "last_saved_at": api(DRAFTS["D1"]["last_saved_at"])})

        self.assertEqual([d["id"] for d in self.listed("evan")["drafts"]],
                         [self.drafts["D3"].id])

        newcomer = self.make_user(role="organiser")
        empty = self.client.get(DRAFTS_URL, headers=self.auth_headers(newcomer)).get_json()
        self.assertEqual(empty["drafts"], [])
        self.assertTrue(empty["message"].strip())

        for key in ("alice", "farah"):
            with self.subTest(user=key):
                self.assert_error(
                    self.client.get(DRAFTS_URL, headers=self.headers(key)), 403
                )


# ---------- AC3: reopen and continue editing ----------


class ReopenTests(DraftTestCase):
    # TC-29-11 · AC3 — reopening shows everything previously saved.
    def test_reopening_shows_everything_previously_saved(self):
        response = self.open("D2")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        for field in DRAFT_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(body[field], api(COMPLETE[field]))
        self.assertEqual(body["id"], self.drafts["D2"].id)
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["last_saved_at"], api(DRAFTS["D2"]["last_saved_at"]))
        self.assertEqual(body["missing_for_submission"], [])

        self.assertEqual(
            self.open("D1").get_json()["missing_for_submission"],
            ["description", "end_time", "venue_requirements", "registration_required"],
        )

    # TC-29-12 · AC3 — another user's draft cannot be opened, saved or submitted.
    def test_another_users_draft_cannot_be_opened_saved_or_submitted(self):
        saved = self.stored("D1")
        for user in ("evan", "alice"):
            for label, call in (("open", lambda u: self.open("D1", u)),
                                ("save", lambda u: self.save("D1", {"title": "Mine"}, u)),
                                ("submit", lambda u: self.submit("D1", u))):
                with self.subTest(user=user, call=label):
                    response = call(user)
                    self.assert_error(response, 403)
                    text = response.get_data(as_text=True)
                    self.assertNotIn("Harbour Lights Festival", text)
                    self.assertNotIn(DRAFTS["D1"]["purpose"], text)
        self.assertEqual(self.stored("D1"), saved)

    # TC-29-13 · AC3 — unknown draft.
    def test_unknown_draft_returns_not_found(self):
        url = f"{DRAFTS_URL}/{self.missing_id(Event)}"
        for method, path, body in (("GET", url, None), ("PUT", url, {"title": "X"}),
                                   ("POST", f"{url}/submit", None)):
            with self.subTest(method=method, path=path):
                response = self.client.open(path, method=method, json=body,
                                            headers=self.headers())
                self.assert_error(response, 404)

    # TC-29-14 · AC3, AC6 — a submitted request cannot be reopened as a draft.
    def test_submitted_request_cannot_be_reopened_as_a_draft(self):
        saved = self.stored("S1")
        for label, response in (("open", self.open("S1")),
                                ("save", self.save("S1", {"title": "Changed"})),
                                ("submit", self.submit("S1"))):
            with self.subTest(call=label):
                self.assertIn("submitted", self.assert_error(response, 409)["error"])
        self.assertEqual(self.stored("S1"), saved)


# ---------- AC4: saving updates the existing draft ----------


class UpdateExistingDraftTests(DraftTestCase):
    # TC-29-16 · AC4 — saving changes updates the same draft.
    def test_saving_changes_updates_the_same_draft(self):
        before = self.request_count()

        first = self.save("D1", {"description": "Lanterns along the promenade",
                                 "expected_attendance": 300})
        second = self.save("D1", {"description": "Lanterns and live music"})

        for response in (first, second):
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.get_json()["id"], self.drafts["D1"].id)
        self.assertEqual(self.request_count(), before)
        stored = self.stored("D1")
        self.assertEqual(stored["description"], "Lanterns and live music")
        self.assertEqual(stored["expected_attendance"], 300)
        self.assertEqual(stored["status"], "draft")

    # TC-29-17 · AC4 (A6) — only the fields sent change; empty clears a field.
    def test_only_the_fields_sent_change_and_empty_clears(self):
        saved = self.stored("D1")

        self.save("D1", {"description": "Only this"})
        stored = self.stored("D1")
        for field in ("title", "purpose", "start_time", "expected_attendance"):
            with self.subTest(field=field):
                self.assertEqual(stored[field], saved[field])

        for value in (None, "   "):
            with self.subTest(purpose=value):
                self.save("D1", {"purpose": DRAFTS["D1"]["purpose"]})
                response = self.save("D1", {"purpose": value})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(self.stored("D1")["purpose"])

    # TC-29-18 · AC4 (boundary) — text is trimmed.
    def test_text_is_trimmed(self):
        created = self.create({"title": "  Spring Garden Party \n"}).get_json()

        self.assertEqual(self.stored(created["id"])["title"], "Spring Garden Party")


# ---------- AC5: save failures ----------


class SaveFailureTests(DraftTestCase):
    def failing_commit(self):
        return mock.patch.object(
            self.db.session, "commit", side_effect=SQLAlchemyError("simulated outage")
        )

    # TC-29-20 · AC5 — a failed save leaves the saved draft unchanged.
    def test_failed_save_leaves_the_saved_draft_unchanged(self):
        saved = self.stored("D1")

        with self.failing_commit():
            response = self.save("D1", {"description": "Lost?"})

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"not saved")
        self.assertRegex(body["error"].lower(), r"try again")
        self.assertEqual(self.stored("D1"), saved)

    # TC-29-21 · AC5 — a failed first save creates nothing.
    def test_failed_first_save_creates_nothing(self):
        before = self.request_count()

        with self.failing_commit():
            response = self.create({"title": "Spring Garden Party"})

        self.assertIs(self.assert_error(response, 503).get("retryable"), True)
        self.assertEqual(self.request_count(), before)

    # TC-29-22 · AC5 — retry succeeds after recovery.
    def test_retry_succeeds_after_recovery(self):
        with self.failing_commit():
            self.save("D1", {"description": "Lanterns along the promenade"})

        self.assertEqual(self.save("D1", {"description": "Lanterns along the promenade"})
                         .status_code, 200)
        self.assertEqual(self.stored("D1")["description"], "Lanterns along the promenade")

    # TC-29-28 · AC6, AC5 — a failed submission leaves the draft as a draft.
    def test_failed_submission_leaves_the_draft_as_a_draft(self):
        with self.failing_commit():
            response = self.submit("D2")

        self.assertIs(self.assert_error(response, 503).get("retryable"), True)
        stored = self.stored("D2")
        self.assertEqual(stored["status"], "draft")
        self.assertIsNone(stored["submitted_at"])


# ---------- AC6: only submission makes a draft Submitted ----------


class SubmissionTests(DraftTestCase):
    # TC-29-24 · AC6 — saving never submits.
    def test_saving_never_submits(self):
        for _ in range(3):
            body = self.save("D2", {"description": COMPLETE["description"]}).get_json()
            self.assertEqual(body["status"], "draft")
            self.assertIsNone(body["submitted_at"])

        self.assertIsNone(self.stored("D2")["submitted_at"])
        self.assertIn(self.drafts["D2"].id, [d["id"] for d in self.listed()["drafts"]])

    # TC-29-25 · AC6 — submitting a complete draft.
    def test_submitting_a_complete_draft(self):
        saved = self.stored("D2")
        started = datetime.utcnow()

        response = self.submit("D2")

        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["status"], "submitted")
        self.assertGreaterEqual(as_datetime(body["submitted_at"]), started)
        stored = self.stored("D2")
        self.assertEqual(stored["status"], "submitted")
        for field in DRAFT_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(stored[field], saved[field])
        self.assertNotIn(self.drafts["D2"].id, [d["id"] for d in self.listed()["drafts"]])

    # TC-29-26 · AC6 (A7/Q3) — an incomplete draft cannot be submitted.
    def test_an_incomplete_draft_cannot_be_submitted(self):
        saved = self.stored("D1")

        body = self.assert_error(self.submit("D1"), 400)

        self.assertEqual(body["missing"],
                         ["description", "end_time", "venue_requirements",
                          "registration_required"])
        self.assertEqual(self.stored("D1"), saved)

    # TC-29-26 · AC6 (A7) — optional fields are not needed to submit.
    def test_optional_fields_are_not_needed_to_submit(self):
        self.save("D2", {"accessibility_needs": None, "equipment_requirements": None})

        self.assertEqual(self.submit("D2").status_code, 200)

    # TC-29-27 · AC6 (boundary) — the end must be after the start to submit.
    def test_end_must_be_after_start_to_submit(self):
        for end in ("2026-12-03T18:00", "2026-12-03T17:59"):
            with self.subTest(end=end):
                self.assertEqual(self.save("D2", {"end_time": end}).status_code, 200)

                self.assert_error(self.submit("D2"), 400, field="end_time")
                self.assertEqual(self.stored("D2")["status"], "draft")

        with self.subTest(end="2026-12-03T18:01"):
            self.save("D2", {"end_time": "2026-12-03T18:01"})
            self.assertEqual(self.submit("D2").status_code, 200)


if __name__ == "__main__":
    unittest.main()
