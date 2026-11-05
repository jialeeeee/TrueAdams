"""Tests for SCRUM-99 "Coordinator is reminded about incomplete arrangements".

Each test names the case it automates in
docs/test-cases/SCRUM-99-incomplete-arrangement-reminders.md (TC-99-xx).

Background job
    tasks.remind_incomplete_arrangements, every REMINDER_INTERVAL_HOURS (default 24; Celery
    beat "remind-incomplete-arrangements"). For each approved event that hasn't started and
    whose coordinator still holds the role, if confirming it would be refused (SCRUM-93's
    checks), the coordinator gets one in-app notification "arrangements_incomplete" naming
    the event and listing what is missing, then an email.

"Now" is fixed at NOW (Singapore time) for the job.
"""

import unittest
from datetime import datetime
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app import config, tasks
from app.events import reminders
from app.extensions import celery
from app.models import Event, Notification, VenueBooking
from tests.base import AppTestCase

NOW = datetime(2027, 5, 1, 9, 0)
START, END = datetime(2027, 6, 10, 10, 0), datetime(2027, 6, 10, 12, 0)
VENUE, EQUIPMENT, SAFETY = ("Confirmed venue booking", "Reserved equipment",
                            "Approved safety check")
KIND = "arrangements_incomplete"


class ReminderTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.organiser = self.make_user(role="organiser")
        self.alice = self.make_user(role="coordinator")
        self.ben = self.make_user(role="coordinator")
        self.officer = self.make_user(role="safety_officer")
        self.hall = self.make_venue(name="Hall A")
        patcher = mock.patch.object(tasks.send_notification_email, "delay")
        self.email = patcher.start()
        self.addCleanup(patcher.stop)

    def event(self, title="Harbour Talk", status="approved", coordinator="alice",
              start=START, end=END, **fields):
        coordinator = {"alice": self.alice, "ben": self.ben, None: None}[coordinator]
        row = Event(title=title, status=status, organiser_id=self.organiser.id,
                    coordinator_id=coordinator.id if coordinator else None,
                    start_time=start, end_time=end, expected_attendance=80,
                    venue_requirements="Hall for 80",
                    **{"equipment_requirements": "Two microphones", **fields})
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def ready(self, event):
        """Give the event everything confirmation needs (SCRUM-93 AC2)."""
        self.db.session.add(VenueBooking(
            event_id=event.id, venue_id=self.hall.id, status="confirmed",
            start_time=event.start_time, end_time=event.end_time, venue_requirements="x",
            requested_by_id=self.alice.id))
        event.equipment_requirements = "None"
        event.safety_decision = "approved"
        event.safety_decided_by_id = self.officer.id
        self.db.session.commit()

    def run_reminders(self, now=NOW):
        with mock.patch.object(reminders, "singapore_now", return_value=now):
            tasks.remind_incomplete_arrangements()

    def reminders_for(self, user, event=None):
        self.db.session.expire_all()
        query = Notification.query.filter_by(recipient_id=user.id, kind=KIND)
        if event is not None:
            query = query.filter_by(event_id=event.id)
        return query.order_by(Notification.id).all()

    def emailed(self):
        return [call.args for call in self.email.call_args_list]


# ---------- AC1, AC2: one reminder per event, naming it and what is missing ----------


class ReminderContentTests(ReminderTestCase):
    # TC-99-01 · AC1, AC2
    def test_tc_99_01_the_coordinator_is_told_everything_still_missing(self):
        talk = self.event()

        self.run_reminders()

        [note] = self.reminders_for(self.alice)
        self.assertEqual(note.event_id, talk.id)
        self.assertEqual(note.message,
                         'Reminder: "Harbour Talk" (2027-06-10 10:00, Singapore time) is '
                         "approved but can't be confirmed yet. Still missing: "
                         f"{VENUE}, {EQUIPMENT}, {SAFETY}.")
        [(to, subject, body)] = self.emailed()
        self.assertEqual((to, subject), (self.alice.email,
                                         "Arrangements still incomplete: Harbour Talk"))
        self.assertIn(note.message, body)

    # TC-99-02 · AC1, AC2
    def test_tc_99_02_only_what_is_missing_is_listed(self):
        talk = self.event()
        self.ready(talk)
        talk.safety_decision = None
        self.db.session.commit()

        self.run_reminders()

        [note] = self.reminders_for(self.alice)
        self.assertTrue(note.message.endswith(f"Still missing: {SAFETY}."))

    # TC-99-03 · AC2
    def test_tc_99_03_each_run_sends_one_reminder_per_event(self):
        first = self.event(title="First")
        second = self.event(title="Second", coordinator="ben")

        self.run_reminders()
        self.run_reminders()

        self.assertEqual(len(self.reminders_for(self.alice, first)), 2)
        self.assertEqual(len(self.reminders_for(self.ben, second)), 2)
        self.assertEqual(self.reminders_for(self.alice, second), [])

    # TC-99-04 · AC2
    def test_tc_99_04_an_event_without_a_date_is_still_reminded(self):
        self.event(start=None, end=None)

        self.run_reminders()

        [note] = self.reminders_for(self.alice)
        self.assertIn('"Harbour Talk" (date not recorded, Singapore time)', note.message)


# ---------- AC3, AC4: who gets no reminder ----------


class NoReminderTests(ReminderTestCase):
    # TC-99-05 · AC3
    def test_tc_99_05_an_event_with_nothing_missing_gets_no_reminder(self):
        self.ready(self.event())

        self.run_reminders()

        self.assertEqual(self.reminders_for(self.alice), [])
        self.email.assert_not_called()

    # TC-99-06 · AC4
    def test_tc_99_06_confirmed_cancelled_rejected_and_unapproved_events_get_none(self):
        for status in ("confirmed", "cancelled", "rejected", "draft", "submitted",
                       "under_review"):
            self.event(title=status, status=status)

        self.run_reminders()

        self.assertEqual(self.reminders_for(self.alice), [])

    # TC-99-07 · A2
    def test_tc_99_07_an_event_that_has_started_gets_none(self):
        self.event(title="Started", start=NOW, end=END)
        upcoming = self.event(title="Upcoming", start=datetime(2027, 5, 1, 9, 1))

        self.run_reminders()

        self.assertEqual([n.event_id for n in self.reminders_for(self.alice)], [upcoming.id])


# ---------- AC6: only the event's coordinator ----------


class RecipientTests(ReminderTestCase):
    # TC-99-08 · AC6
    def test_tc_99_08_only_the_events_coordinator_is_reminded(self):
        self.event()

        self.run_reminders()

        self.assertEqual(len(self.reminders_for(self.alice)), 1)
        for user in (self.ben, self.organiser, self.officer):
            self.assertEqual(self.reminders_for(user), [])
        self.assertEqual([args[0] for args in self.emailed()], [self.alice.email])

    # TC-99-09 · AC6, A3
    def test_tc_99_09_no_coordinator_or_one_without_the_role_gets_none(self):
        self.event(coordinator=None)
        self.event(title="Former")
        self.alice.role = "organiser"
        self.db.session.commit()

        self.run_reminders()

        self.assertEqual(self.reminders_for(self.alice), [])
        self.email.assert_not_called()

    # TC-99-09 · AC6 (CF01)
    def test_tc_99_09_a_coordinator_as_an_additional_role_is_reminded(self):
        self.event()
        self.alice.role = "organiser"
        self.alice.additional_roles = ["coordinator"]
        self.db.session.commit()

        self.run_reminders()

        self.assertEqual(len(self.reminders_for(self.alice)), 1)


# ---------- AC7: failures ----------


class FailureTests(ReminderTestCase):
    # TC-99-10 · AC7
    def test_tc_99_10_a_queue_outage_keeps_the_reminders_and_is_logged(self):
        self.event(title="First")
        self.event(title="Second", coordinator="ben")
        self.email.side_effect = ConnectionError("broker down")

        with self.assertLogs(self.app.logger, level="ERROR") as logs:
            self.run_reminders()

        self.assertEqual(len(self.reminders_for(self.alice)), 1)
        self.assertEqual(len(self.reminders_for(self.ben)), 1)
        # Each email is tried, and each failure logged.
        self.assertEqual(self.email.call_count, 2)
        self.assertEqual(sum("Could not queue the reminder email" in line
                             for line in logs.output), 2)

    # TC-99-11 · AC7
    def test_tc_99_11_a_failed_run_saves_nothing_and_is_logged(self):
        self.event()

        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO notifications"):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            with self.assertLogs(self.app.logger, level="ERROR") as logs:
                self.run_reminders()
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.assertEqual(self.reminders_for(self.alice), [])
        self.email.assert_not_called()
        self.assertIn("reminder run failed", logs.output[0])
        # The next run tries again.
        self.run_reminders()
        self.assertEqual(len(self.reminders_for(self.alice)), 1)


# ---------- AC5: how often it runs ----------


class ScheduleTests(unittest.TestCase):
    # TC-99-12 · AC5
    def test_tc_99_12_the_job_runs_every_24_hours_by_default(self):
        entry = celery.conf.beat_schedule.get("remind-incomplete-arrangements")

        self.assertEqual(entry, {"task": "tasks.remind_incomplete_arrangements",
                                 "schedule": 24 * 3600})
        self.assertIn("tasks.remind_incomplete_arrangements", celery.tasks)

    # TC-99-13 · AC5
    def test_tc_99_13_the_frequency_is_a_setting(self):
        self.assertEqual(config.reminder_interval_hours(None), 24)
        self.assertEqual(config.reminder_interval_hours("  "), 24)
        self.assertEqual(config.reminder_interval_hours("12"), 12)
        self.assertEqual(config.reminder_interval_hours("0.5"), 0.5)
        for value in ("0", "-3", "daily", "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "positive number of hours"):
                    config.reminder_interval_hours(value)

    # TC-99-13 · AC5
    def test_tc_99_13_the_schedule_follows_the_setting(self):
        from app import create_app
        from app.config import TestConfig

        class EveryHour(TestConfig):
            REMINDER_INTERVAL_HOURS = 1

        try:
            create_app(EveryHour)
            self.assertEqual(
                celery.conf.beat_schedule["remind-incomplete-arrangements"]["schedule"], 3600)
        finally:
            create_app(TestConfig)
