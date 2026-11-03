"""Tests for the in-app notifications list and marking a notification read.

Every story that saves a Notification is tested in its own file; these tests cover the
notifications endpoints themselves, which frontend/src/pages/NotificationsPage.jsx uses.

API
    GET  /api/notifications/            the caller's own, newest first
        200 {"notifications": [{"id", "kind", "message", "event_id", "created_at", "read_at"}],
             "message": "You have no notifications." | null}
        401 · 503 {"retryable": true}
    POST /api/notifications/<id>/read   the caller's own only
        200 {"notification": {...}}  read_at is set once; marking again keeps it
        401 · 404 unknown or someone else's (the same answer) · 503 and nothing saved
"""

import unittest
from datetime import datetime
from unittest import mock

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import SQLAlchemyError

from app.models import Notification
from tests.base import AppTestCase


class NotificationTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.ivy = self.make_user(role="attendee")
        self.jon = self.make_user(role="coordinator")
        self.older = self.notify(self.ivy, "Older", datetime(2026, 10, 1, 9, 0))
        self.newer = self.notify(self.ivy, "Newer", datetime(2026, 10, 2, 9, 0))
        self.theirs = self.notify(self.jon, "Not Ivy's", datetime(2026, 10, 3, 9, 0))

    def notify(self, user, message, created_at):
        notification = Notification(recipient_id=user.id, kind="test", message=message,
                                    created_at=created_at)
        self.db.session.add(notification)
        self.db.session.commit()
        return notification

    def listed(self, user=None, headers=None):
        return self.client.get("/api/notifications/",
                               headers=headers or self.auth_headers(user or self.ivy))

    def mark(self, notification_id, user=None, headers=None):
        return self.client.post(f"/api/notifications/{notification_id}/read",
                                headers=headers or self.auth_headers(user or self.ivy))

    def read_at(self, notification):
        self.db.session.expire_all()
        return self.db.session.get(Notification, notification.id).read_at

    def bad_identity(self):
        return {"Authorization": f"Bearer {create_access_token(identity='not-an-id')}"}


class ListTests(NotificationTestCase):
    def test_the_callers_own_notifications_newest_first(self):
        response = self.listed()
        self.assertEqual(response.status_code, 200, response.get_json())
        items = response.get_json()["notifications"]
        self.assertEqual([n["message"] for n in items], ["Newer", "Older"])
        self.assertEqual(items[0], {
            "id": self.newer.id, "kind": "test", "message": "Newer", "event_id": None,
            "created_at": "2026-10-02T09:00:00", "read_at": None})
        self.assertIsNone(response.get_json()["message"])

    def test_no_notifications_says_so(self):
        body = self.listed(user=self.make_user()).get_json()
        self.assertEqual(body, {"notifications": [], "message": "You have no notifications."})

    def test_an_unparsable_identity_is_a_401(self):
        self.assertEqual(self.listed(headers=self.bad_identity()).status_code, 401)

    def test_a_load_failure_is_retryable(self):
        with mock.patch.object(self.db.session, "get", side_effect=SQLAlchemyError("down")):
            response = self.listed()
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.get_json()["retryable"], True)
        self.assertNotIn("down", response.get_data(as_text=True))


class MarkReadTests(NotificationTestCase):
    def test_marking_a_notification_read_records_when(self):
        response = self.mark(self.older.id)
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()["notification"]
        self.assertEqual(body["id"], self.older.id)
        self.assertIsNotNone(body["read_at"])
        self.assertIsNotNone(self.read_at(self.older))
        self.assertIsNone(self.read_at(self.newer))

    def test_marking_it_again_keeps_the_first_time(self):
        self.mark(self.older.id)
        first = self.read_at(self.older)
        response = self.mark(self.older.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.read_at(self.older), first)

    def test_someone_elses_notification_looks_unknown(self):
        theirs = self.mark(self.theirs.id)
        unknown = self.mark(self.missing_id(Notification))
        too_large = self.mark(2_147_483_648)
        for response in (theirs, unknown, too_large):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.get_json(), {"error": "Notification not found."})
        self.assertIsNone(self.read_at(self.theirs))

    def test_an_unparsable_identity_is_a_401(self):
        self.assertEqual(self.mark(self.older.id, headers=self.bad_identity()).status_code, 401)
        self.assertIsNone(self.read_at(self.older))

    def test_a_save_failure_is_retryable_and_saves_nothing(self):
        with mock.patch.object(self.db.session, "commit", side_effect=SQLAlchemyError("down")):
            response = self.mark(self.older.id)
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.get_json()["retryable"], True)
        self.assertIsNone(self.read_at(self.older))


if __name__ == "__main__":
    unittest.main()
