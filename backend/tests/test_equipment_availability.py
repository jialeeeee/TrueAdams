"""Tests for SCRUM-43 "Check Equipment Availability for an Event".

Each test names the case it automates in docs/test-cases/SCRUM-43-equipment-availability.md
(TC-43-xx). Seed data AV-SEED: the USERS in tests/seed_data.py, plus G1-G3 and the
equipment below. The equipment catalogue is shared with real data, so every category
and equipment type here ends with this run's suffix.

Model (db/equipment_unavailability.sql): EquipmentUnavailability
    resource_id, start_time, end_time (Singapore time, half-open), reason, created_at

Endpoint (JWT required, else 401; the User row is loaded on every request)
    GET /api/events/<id>/equipment-availability            Technical Support Staff
        200 {"event": {"id", "title", "status", "start_time", "end_time"},
             "checks": [LINE, ...], "summary", "can_all_be_met", "notice", "message"}
        LINE = {"requirement_id", "equipment_type", "requested_quantity",
                "technical_requirements", "technical_note", "available_quantity",
                "result": "enough" | "not_enough" | "none_suitable", "result_label",
                "suitable": [{"id", "name", "category", "quantity_available"}],
                "excluded": [{"id", "name", "reason": "unavailable" | "quantity_not_recorded",
                              "detail"}]}
    Checks, first failure wins: 401 -> 404 -> 403 -> 409 (cancelled or rejected) ->
    422 {"error", "missing": [...]} (times not recorded) -> 503 {"error", "retryable": true}.
    Read-only: nothing is reserved or changed.
"""

import unittest
from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token
from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import EquipmentRequirement, Event, Resource
from tests import seed_data
from tests.base import RUN_ID, AppTestCase

SUFFIX = f" #{RUN_ID}"
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."

# AV-SEED. `organiser` and `coordinator` refer to seed_data USERS keys.
EVENTS = [
    {"key": "G1", "title": "Charity Gala", "status": "approved", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 12, 5, 18, 0),
     "end_time": datetime(2026, 12, 5, 23, 0)},
    {"key": "G2", "title": "Untimed Talk", "status": "submitted", "organiser": "dana",
     "coordinator": "alice", "start_time": None, "end_time": None},
    {"key": "G3", "title": "Spring Fair", "status": "cancelled", "organiser": "dana",
     "coordinator": "alice", "start_time": datetime(2026, 11, 1, 10, 0),
     "end_time": datetime(2026, 11, 1, 16, 0)},
]
# G1's requirements, in the order recorded: (type, quantity, technical requirements).
REQUIREMENTS = [("Wireless microphone", 3, "Lapel"), ("Projector", 1, None),
                ("Hologram projector", 1, None), ("Speaker", 2, None)]
# (name, category, quantity available)
EQUIPMENT = [("Shure SLX-D", "Wireless microphone", 2),
             ("Sennheiser EW-D", "wireless  MICROPHONE", 2),
             ("Epson EB-L", "Projector", 1),
             ("BenQ LU935", "Projector", 2),
             ("JBL EON", "Speaker", None),
             ("Bose S1", "Speaker", 1)]


def _unavailability_model():
    # Imported here so the tests fail on behaviour, not on import, until it exists.
    from app.models import EquipmentUnavailability

    return EquipmentUnavailability


def base(text):
    """The type or category without this run's suffix."""
    return text[:-len(SUFFIX)] if text.endswith(SUFFIX) else text


class AvailabilityTestCase(AppTestCase):
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
        for equipment_type, quantity, technical in REQUIREMENTS:
            row = EquipmentRequirement(event_id=self.events["G1"].id,
                                       equipment_type=equipment_type + SUFFIX, quantity=quantity,
                                       technical_requirements=technical,
                                       recorded_by_id=self.users["alice"].id)
            self.db.session.add(row)
            self.db.session.commit()
            self.requirements[equipment_type] = row
        self.unavailable("Epson EB-L", datetime(2026, 12, 5, 17, 0), datetime(2026, 12, 5, 19, 0),
                         "Lamp replacement")
        self.unavailable("BenQ LU935", datetime(2026, 12, 5, 23, 0), datetime(2026, 12, 6, 9, 0),
                         "Firmware update")

    def unavailable(self, name, start, end, reason):
        self.db.session.add(_unavailability_model()(resource_id=self.items[name].id,
                                                    start_time=start, end_time=end, reason=reason))
        self.db.session.commit()

    def url(self, event="G1"):
        return f"/api/events/{self.events[event].id if isinstance(event, str) else event}/equipment-availability"

    def check(self, event="G1", user="hana", headers=None):
        return self.client.get(self.url(event),
                               headers=self.auth_headers(self.users[user]) if headers is None else headers)

    def result(self, event="G1"):
        response = self.check(event)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def lines(self, result):
        return {base(line["equipment_type"]): line for line in result["checks"]}

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error", "").strip())
        self.assertNotIn("checks", body)
        return body


# ---------- AC1: the check uses the event's requirements and times ----------


class UsesTheEventTests(AvailabilityTestCase):
    # TC-43-01 · AC1, AC2
    def test_tc_43_01_one_line_per_requirement_for_the_events_period(self):
        result = self.result()

        self.assertEqual(result["event"]["title"], "Charity Gala")
        self.assertEqual((result["event"]["start_time"], result["event"]["end_time"]),
                         ("2026-12-05T18:00:00", "2026-12-05T23:00:00"))
        self.assertEqual(
            [(base(l["equipment_type"]), l["requested_quantity"], l["technical_requirements"])
             for l in result["checks"]],
            [("Wireless microphone", 3, "Lapel"), ("Projector", 1, None),
             ("Hologram projector", 1, None), ("Speaker", 2, None)])
        self.assertEqual([l["requirement_id"] for l in result["checks"]],
                         [self.requirements[t].id for t, _, _ in REQUIREMENTS])

    # TC-43-02 · AC1
    def test_tc_43_02_uses_the_latest_saved_requirements_and_times(self):
        self.assertEqual(self.lines(self.result())["Projector"]["available_quantity"], 2)
        self.requirements["Wireless microphone"].quantity = 5
        self.events["G1"].start_time = datetime(2026, 12, 5, 20, 0)
        self.db.session.commit()

        lines = self.lines(self.result())

        self.assertEqual((lines["Wireless microphone"]["requested_quantity"],
                          lines["Wireless microphone"]["result"]), (5, "not_enough"))
        # The Epson is unavailable until 19:00, before the new start.
        self.assertEqual(lines["Projector"]["available_quantity"], 3)

    # TC-43-03 · AC1, AC2
    def test_tc_43_03_types_match_categories_ignoring_case_and_spacing(self):
        lines = self.lines(self.result())

        self.assertEqual({s["name"] for s in lines["Wireless microphone"]["suitable"]},
                         {"Shure SLX-D", "Sennheiser EW-D"})
        self.assertEqual({s["name"] for s in lines["Projector"]["suitable"]}, {"BenQ LU935"})
        self.assertEqual({s["name"] for s in lines["Speaker"]["suitable"]}, {"Bose S1"})
        self.assertEqual(lines["Hologram projector"]["suitable"], [])

    # TC-43-04 · AC1
    def test_tc_43_04_technical_requirements_are_shown_for_technical_support_to_confirm(self):
        lines = self.lines(self.result())

        self.assertIn("Lapel", lines["Wireless microphone"]["technical_note"])
        self.assertIn("confirm", lines["Wireless microphone"]["technical_note"])
        self.assertIsNone(lines["Projector"]["technical_note"])


# ---------- AC2: requested and available suitable quantity per requirement ----------


class QuantityTests(AvailabilityTestCase):
    # TC-43-05 · AC2
    def test_tc_43_05_requested_and_available_quantity_for_each_requirement(self):
        result = self.result()

        self.assertEqual(
            {t: (l["requested_quantity"], l["available_quantity"], l["result"])
             for t, l in self.lines(result).items()},
            {"Wireless microphone": (3, 4, "enough"), "Projector": (1, 2, "enough"),
             "Hologram projector": (1, 0, "none_suitable"), "Speaker": (2, 1, "not_enough")})
        self.assertEqual(result["summary"],
                         "2 of 4 equipment requirements can be met from available equipment.")
        self.assertIs(result["can_all_be_met"], False)
        self.assertIsNone(result["message"])

    # TC-43-06 · AC2
    def test_tc_43_06_exactly_enough_is_enough(self):
        self.requirements["Wireless microphone"].quantity = 4
        self.db.session.commit()

        line = self.lines(self.result())["Wireless microphone"]

        self.assertEqual((line["requested_quantity"], line["available_quantity"], line["result"]),
                         (4, 4, "enough"))
        self.assertEqual(line["result_label"], "Enough available")

    # TC-43-07 · AC2
    def test_tc_43_07_equipment_with_no_quantity_recorded_is_not_counted(self):
        line = self.lines(self.result())["Speaker"]

        self.assertEqual(line["available_quantity"], 1)
        self.assertEqual([(e["name"], e["reason"]) for e in line["excluded"]],
                         [("JBL EON", "quantity_not_recorded")])

    # TC-43-08 · AC2
    def test_tc_43_08_an_event_with_no_requirements_says_so(self):
        quiet = self.make_event(self.users["dana"], title="Quiet Lunch", status="approved",
                                coordinator_id=self.users["alice"].id)

        result = self.result(quiet.id)

        self.assertEqual(result["checks"], [])
        self.assertEqual(result["message"], "No equipment requirements have been recorded for this event.")
        self.assertIsNone(result["summary"])


# ---------- AC3: equipment unavailable for the period is excluded ----------


class UnavailableTests(AvailabilityTestCase):
    # TC-43-09 · AC3
    def test_tc_43_09_equipment_unavailable_during_the_event_is_excluded(self):
        line = self.lines(self.result())["Projector"]

        self.assertNotIn("Epson EB-L", {s["name"] for s in line["suitable"]})
        [excluded] = line["excluded"]
        self.assertEqual((excluded["name"], excluded["reason"]), ("Epson EB-L", "unavailable"))
        self.assertIn("Lamp replacement", excluded["detail"])
        self.assertIn("2026-12-05 17:00", excluded["detail"])

    # TC-43-10 · AC3
    def test_tc_43_10_a_period_that_only_touches_the_event_does_not_exclude(self):
        line = self.lines(self.result())["Projector"]

        self.assertIn("BenQ LU935", {s["name"] for s in line["suitable"]})
        self.assertEqual(line["available_quantity"], 2)

    # TC-43-11 · AC3
    def test_tc_43_11_unavailability_on_another_day_does_not_exclude(self):
        self.unavailable("Shure SLX-D", datetime(2026, 12, 4, 9, 0), datetime(2026, 12, 4, 18, 0),
                         "Battery check")

        line = self.lines(self.result())["Wireless microphone"]

        self.assertEqual(line["available_quantity"], 4)
        self.assertEqual(line["excluded"], [])


# ---------- AC4: checking does not reserve ----------


class NoReservationTests(AvailabilityTestCase):
    def snapshot(self):
        self.db.session.expire_all()
        items = {i.name: i.quantity_available for i in
                 Resource.query.filter(Resource.id.in_([i.id for i in self.items.values()]))}
        requirements = {r.id: (r.quantity, r.status) for r in
                        EquipmentRequirement.query.filter_by(event_id=self.events["G1"].id)}
        event = self.db.session.get(Event, self.events["G1"].id)
        return items, requirements, (event.status, event.start_time, event.end_time)

    # TC-43-12 · AC4
    def test_tc_43_12_checking_changes_nothing_and_reserves_nothing(self):
        before = self.snapshot()

        first, second = self.result(), self.result()

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(first, second)
        self.assertEqual(first["notice"], "Checking availability does not reserve any equipment.")
        text = str({k: v for k, v in first.items() if k != "notice"}).lower()
        for word in ("reserved", "booked", "confirmed"):
            self.assertNotIn(word, text)


# ---------- AC5: missing times and failed checks give an error with details ----------


class ErrorTests(AvailabilityTestCase):
    # TC-43-13 · AC5
    def test_tc_43_13_missing_times_are_an_error_naming_them(self):
        body = self.assert_error(self.check("G2"), 422)
        self.assertEqual(body["missing"], ["start_time", "end_time"])
        self.assertIn("start time and end time", body["error"])

        self.events["G2"].start_time = datetime(2026, 11, 20, 9, 0)
        self.db.session.commit()

        body = self.assert_error(self.check("G2"), 422)
        self.assertEqual(body["missing"], ["end_time"])
        self.assertIn("end time", body["error"])

    # TC-43-14 · AC5
    def test_tc_43_14_a_failed_check_is_an_error_not_a_result(self):
        url, headers = self.url(), self.auth_headers(self.users["hana"])
        for table in ("resources", "equipment_unavailability"):
            def fail(conn, cursor, statement, parameters, context, executemany):
                if f"FROM {table}" in statement:
                    raise OperationalError(statement, parameters, Exception("simulated outage"))

            self.db.session.expire_all()
            sa_event.listen(self.db.engine, "before_cursor_execute", fail)
            try:
                response = self.client.get(url, headers=headers)
            finally:
                sa_event.remove(self.db.engine, "before_cursor_execute", fail)

            with self.subTest(table=table):
                body = self.assert_error(response, 503)
                self.assertIs(body.get("retryable"), True)
                self.assertIn("could not be completed", body["error"])
                self.assertNotIn("simulated outage", body["error"])
                self.assertNotIn("summary", body)

    # TC-43-15 · AC5
    def test_tc_43_15_who_may_check_and_in_what_order(self):
        ghost = self.make_user(role="tech_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        expired = create_access_token(identity=str(self.users["hana"].id),
                                      expires_delta=timedelta(seconds=-1))
        for label, headers in {"no token": {}, "expired": {"Authorization": f"Bearer {expired}"},
                               "deleted user": ghost_headers}.items():
            with self.subTest(session=label):
                response = self.check(headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("Charity Gala", response.get_data(as_text=True))
        self.assertEqual(self.check(headers=ghost_headers).get_json()["error"], SESSION_EXPIRED)

        self.assertEqual(self.assert_error(self.check(self.missing_id(Event)), 404)["error"],
                         "Event not found.")
        for user in ("alice", "dana", "gus", "admin", "farah"):
            with self.subTest(user=user):
                response = self.check(user=user)
                self.assert_error(response, 403)
                self.assertNotIn("Charity Gala", response.get_data(as_text=True))
        self.assertIn("cancelled", self.assert_error(self.check("G3"), 409)["error"])
        # Permission is checked before the missing times.
        self.assert_error(self.check("G2", user="alice"), 403)


if __name__ == "__main__":
    unittest.main()
