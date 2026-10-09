"""Tests for SCRUM-59 "See Drafts Separately from Submitted Requests".

Each test names the case it automates from
docs/test-cases/SCRUM-59-drafts-separate-from-submitted.md (TC-59-nn) and the
acceptance criteria it checks. Assumptions A1-A8 and questions Q1-Q3 are there.

Endpoint (JWT required, else 401; organisers only, else 403)
    GET /api/events/mine
        200 {"drafts": [draft], "submitted": [request], "message": str | null}
        503 {"error", "retryable": true} if loading fails
    draft   = {"id", "title", "status", "last_saved_at"}   title is null when blank
    request = {"id", "title", "status", "submitted_at", "decided_at", "decision_note"}

Opening a draft, and refusing to open a submitted request as one, use the SCRUM-29
endpoints GET/PUT /api/events/drafts/<id>.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Event
from tests import seed_data
from tests.base import AppTestCase

# Every field SCRUM-29 needs before a draft can be submitted.
COMPLETE = {
    "purpose": "Celebrate the harbour's reopening",
    "description": "Lanterns along the promenade with live music.",
    "start_time": datetime(2026, 12, 12, 17, 0),
    "end_time": datetime(2026, 12, 12, 22, 0),
    "expected_attendance": 250,
    "venue_requirements": "Open-air waterfront space",
    "registration_required": True,
}

# ML-SEED. Times are naive UTC. `organiser` refers to a seed_data.USERS key.
REQUESTS = {
    "D1": {"title": "Harbour Lights Festival", "organiser": "dana", "status": "draft",
           "last_saved_at": datetime(2026, 9, 25, 10, 0), **COMPLETE},
    "D2": {"title": "Winter Networking Night", "organiser": "dana", "status": "draft",
           "last_saved_at": datetime(2026, 9, 27, 8, 30)},
    "D3": {"title": "", "organiser": "dana", "status": "draft",
           "last_saved_at": datetime(2026, 9, 26, 9, 0)},
    "D4": {"title": "   ", "organiser": "dana", "status": "draft",
           "last_saved_at": datetime(2026, 9, 24, 9, 0)},
    "S1": {"title": "Product Launch", "organiser": "dana", "status": "submitted",
           "submitted_at": datetime(2026, 9, 20, 9, 0)},
    "S2": {"title": "Spring Garden Party", "organiser": "dana", "status": "under_review",
           "submitted_at": datetime(2026, 9, 21, 9, 0)},
    "S3": {"title": "Alumni Mixer", "organiser": "dana", "status": "approved",
           "submitted_at": datetime(2026, 9, 22, 9, 0),
           "decided_at": datetime(2026, 9, 23, 9, 0), "decision_note": "Venue confirmed"},
    "S4": {"title": "Rooftop Cinema", "organiser": "dana", "status": "rejected",
           "submitted_at": datetime(2026, 9, 6, 9, 0),
           "decided_at": datetime(2026, 9, 12, 9, 0),
           "decision_note": "No licensed venue is available"},
    "S5": {"title": "Cancelled Meetup", "organiser": "dana", "status": "cancelled",
           "submitted_at": datetime(2026, 9, 1, 9, 0)},
    "E1": {"title": "Evan's Draft", "organiser": "evan", "status": "draft",
           "last_saved_at": datetime(2026, 9, 28, 9, 0)},
    "E2": {"title": "Evan's Launch", "organiser": "evan", "status": "submitted",
           "submitted_at": datetime(2026, 9, 23, 9, 0)},
}

NON_ORGANISERS = ["admin", "alice", "farah", "gus", "hana"]


class MyRequestsTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.users = self.seed_users(seed_data.USERS)
        self.requests = {
            key: Event(organiser_id=self.users[row["organiser"]].id,
                       **{k: v for k, v in row.items() if k != "organiser"})
            for key, row in REQUESTS.items()
        }
        self._insert(Event, list(self.requests.values()))

    # ---------- Requests ----------

    def load(self, as_user="dana", headers=None):
        if headers is None:
            headers = self.auth_headers(self.users[as_user])
        return self.client.get("/api/events/mine", headers=headers)

    def listed(self, as_user="dana"):
        response = self.load(as_user)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def keys(self, items):
        """The seed keys of the listed items, in order; rows from real data are skipped."""
        by_id = {event.id: key for key, event in self.requests.items()}
        return [by_id[item["id"]] for item in items if item["id"] in by_id]

    # ---------- Assertions ----------

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"].strip())
        self.assertNotIn("drafts", body)
        self.assertNotIn("submitted", body)
        return body


# ---------- AC1: the organiser's own requests ----------


class OwnRequestsTests(MyRequestsTestCase):
    # TC-59-01 · AC1, AC3 — the organiser sees their own requests in two groups.
    def test_organiser_sees_their_own_requests_in_two_groups(self):
        body = self.listed()

        self.assertEqual(set(self.keys(body["drafts"])), {"D1", "D2", "D3", "D4"})
        self.assertEqual(set(self.keys(body["submitted"])), {"S1", "S2", "S3", "S4", "S5"})
        self.assertIsNone(body["message"])

    # TC-59-02 · AC1 — only organisers, with a valid session.
    def test_only_organisers_with_a_valid_session(self):
        for user in NON_ORGANISERS:
            with self.subTest(user=user):
                self.assert_error(self.load(as_user=user), 403)

        ghost = self.make_user(role="organiser")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["dana"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                self.assertEqual(self.load(headers=headers).status_code, 401)

        dana_headers = self.auth_headers(self.users["dana"])
        self.users["dana"].role = "attendee"
        self.db.session.commit()
        self.assert_error(self.load(headers=dana_headers), 403)


# ---------- AC2: labels, saved times and statuses ----------


class LabelsTests(MyRequestsTestCase):
    # TC-59-03 · AC2 — drafts show Draft and their last-saved time, newest first.
    def test_drafts_show_draft_and_last_saved_time_newest_first(self):
        drafts = self.listed()["drafts"]

        self.assertEqual(self.keys(drafts), ["D2", "D3", "D1", "D4"])
        d1 = next(d for d in drafts if d["id"] == self.requests["D1"].id)
        self.assertEqual(d1, {"id": self.requests["D1"].id, "title": "Harbour Lights Festival",
                              "status": "draft", "last_saved_at": "2026-09-25T10:00:00"})
        self.assertTrue(all(d["status"] == "draft" for d in drafts))

    # TC-59-04 · AC2 — submitted requests show their current status, newest first.
    def test_submitted_requests_show_current_status_newest_first(self):
        submitted = self.listed()["submitted"]

        self.assertEqual(self.keys(submitted), ["S3", "S2", "S1", "S4", "S5"])
        by_key = dict(zip(self.keys(submitted), submitted))
        self.assertEqual({key: item["status"] for key, item in by_key.items()}, {
            "S1": "submitted", "S2": "under_review", "S3": "approved",
            "S4": "rejected", "S5": "cancelled",
        })
        self.assertEqual(by_key["S3"], {
            "id": self.requests["S3"].id, "title": "Alumni Mixer", "status": "approved",
            "submitted_at": "2026-09-22T09:00:00", "decided_at": "2026-09-23T09:00:00",
            "decision_note": "Venue confirmed",
        })
        self.assertEqual(by_key["S4"]["decision_note"], "No licensed venue is available")
        self.assertEqual((by_key["S1"]["decided_at"], by_key["S1"]["decision_note"]),
                         (None, None))


# ---------- AC3: drafts are kept apart from submitted requests ----------


class SeparationTests(MyRequestsTestCase):
    # TC-59-05 · AC3 — submitting a draft moves it to the submitted group.
    def test_submitting_a_draft_moves_it_to_the_submitted_group(self):
        response = self.client.post(f"/api/events/drafts/{self.requests['D1'].id}/submit",
                                    headers=self.auth_headers(self.users["dana"]))
        self.assertEqual(response.status_code, 200, response.get_json())

        body = self.listed()

        self.assertNotIn("D1", self.keys(body["drafts"]))
        self.assertEqual(self.keys(body["submitted"])[0], "D1")
        self.assertEqual(body["submitted"][0]["status"], "submitted")
        draft_ids = {d["id"] for d in body["drafts"]}
        self.assertFalse(draft_ids & {r["id"] for r in body["submitted"]})


# ---------- AC4 and AC5: opening from the list ----------


class OpeningTests(MyRequestsTestCase):
    # TC-59-06 · AC4 — a listed draft opens with its saved information.
    def test_a_listed_draft_opens_with_its_saved_information(self):
        d1_id = next(d["id"] for d in self.listed()["drafts"]
                     if d["title"] == "Harbour Lights Festival")

        response = self.client.get(f"/api/events/drafts/{d1_id}",
                                   headers=self.auth_headers(self.users["dana"]))

        self.assertEqual(response.status_code, 200)
        draft = response.get_json()
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["purpose"], "Celebrate the harbour's reopening")
        self.assertEqual(draft["expected_attendance"], 250)

    # TC-59-07 · AC5 — a submitted request cannot be opened or saved as a draft.
    def test_a_submitted_request_cannot_be_opened_or_saved_as_a_draft(self):
        s1_id = next(r["id"] for r in self.listed()["submitted"] if r["title"] == "Product Launch")
        headers = self.auth_headers(self.users["dana"])

        self.assert_error(self.client.get(f"/api/events/drafts/{s1_id}", headers=headers), 409)
        self.assert_error(self.client.put(f"/api/events/drafts/{s1_id}", headers=headers,
                                          json={"title": "Renamed"}), 409)

        self.db.session.expire_all()
        s1 = self.db.session.get(Event, s1_id)
        self.assertEqual((s1.title, s1.status), ("Product Launch", "submitted"))


# ---------- AC6: untitled drafts ----------


class UntitledTests(MyRequestsTestCase):
    # TC-59-08 · AC6 (A6/Q1) — a draft with a blank name is listed with no title.
    def test_a_draft_with_a_blank_name_is_listed_with_no_title(self):
        drafts = self.listed()["drafts"]
        by_key = dict(zip(self.keys(drafts), drafts))

        self.assertIsNone(by_key["D3"]["title"])
        self.assertIsNone(by_key["D4"]["title"])
        self.assertEqual(by_key["D2"]["title"], "Winter Networking Night")


# ---------- AC7: empty state ----------


class EmptyStateTests(MyRequestsTestCase):
    # TC-59-09 · AC7 — no requests at all, or only one kind.
    def test_no_requests_or_only_one_kind(self):
        newcomer = self.make_user(role="organiser")
        empty = self.client.get("/api/events/mine",
                                headers=self.auth_headers(newcomer)).get_json()
        self.assertEqual((empty["drafts"], empty["submitted"]), ([], []))
        self.assertIsInstance(empty["message"], str)
        self.assertTrue(empty["message"].strip())

        for status, group in (("draft", "drafts"), ("submitted", "submitted")):
            with self.subTest(only=group):
                organiser = self.make_user(role="organiser")
                self.make_event(organiser=organiser, title="Only one", status=status,
                                last_saved_at=datetime(2026, 9, 1, 9, 0),
                                submitted_at=datetime(2026, 9, 2, 9, 0)
                                if status == "submitted" else None)

                body = self.client.get("/api/events/mine",
                                       headers=self.auth_headers(organiser)).get_json()

                self.assertIsNone(body["message"])
                self.assertEqual([r["title"] for r in body[group]], ["Only one"])
                other = "submitted" if group == "drafts" else "drafts"
                self.assertEqual(body[other], [])


# ---------- AC8: loading fails ----------


class LoadFailureTests(MyRequestsTestCase):
    # TC-59-10 · AC8 — the organiser is told and can retry.
    def test_load_failure_is_reported_and_retry_works(self):
        headers = self.auth_headers(self.users["dana"])
        session = self.db.session()
        with mock.patch.object(session, "execute",
                               side_effect=SQLAlchemyError("simulated outage")):
            response = self.load(headers=headers)

        body = self.assert_error(response, 503)
        self.assertIs(body.get("retryable"), True)
        self.assertRegex(body["error"].lower(), r"could not be loaded")
        self.assertRegex(body["error"].lower(), r"try again")

        self.assertEqual(set(self.keys(self.listed()["drafts"])), {"D1", "D2", "D3", "D4"})


if __name__ == "__main__":
    unittest.main()
