"""Tests for SCRUM-63 "Maintain the Venue Catalogue".

Each test names the case it automates from the "Sprint 3 test cases" sheet
(IS212-US63-TCnn) and docs/test-cases/SCRUM-63-maintain-venue-catalogue.md. TC1-TC16
there are the screen-level cases; the frontend ones (TC8 typing, TC12 kept values)
are covered in frontend/src/pages/VenueFormPage.test.jsx.

Model (db/venue_catalogue.sql)
    VenueChange  venue_id, action ("added" | "edited"), changed_by_id,
                 changed_at (naive UTC), changes {"<field>": {"from", "to"}}

Endpoints (JWT required, else 401; caller not Venue Staff -> 403, checked in the database)
    GET  /api/venues/options       -> {"facilities", "accessibility_features", "room_layouts"}
    POST /api/venues/              -> 201 {"message", "venue": details}
    PUT  /api/venues/<id>          -> 200 {"message", "venue": details}; only the fields sent change
        400 {"error", "fields": {"<field>": "<message>"}}  every invalid field at once
        404 unknown venue   503 {"error", "retryable": true}  nothing saved
    GET  /api/venues/<id>/history  -> {"history": [{"action", "changed_by": {"id", "email"},
                                      "changed_at", "changes"}]}, oldest first
"""

import unittest
from datetime import datetime, timedelta

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Venue, VenueChange
from app.venues import scheduling
from tests.base import AppTestCase

VENUES_URL = "/api/venues/"
FULL = {
    "name": "Orchard Hall",
    "location": "12 Orchard Road, Singapore 238888",
    "capacity": 120,
    "facilities": ["Projector", "Microphone"],
    "accessibility_features": ["Wheelchair ramp"],
    "room_layouts": ["Theatre", "Classroom"],
    "operating_hours": "Mon-Fri 08:00-22:00",
}


class CatalogueTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_user("venue_staff1@test.example", role="venue_staff")
        self.staff2 = self.make_user("venue_staff2@test.example", role="venue_staff")
        self.coordinator = self.make_user("coord_alice@test.example", role="coordinator")
        self.attendee = self.make_user("attendee_dan@test.example", role="attendee")

    def add(self, body, user=None):
        return self.client.post(VENUES_URL, json=body, headers=self.auth_headers(user or self.staff))

    def edit(self, venue_id, body, user=None):
        return self.client.put(
            f"{VENUES_URL}{venue_id}", json=body, headers=self.auth_headers(user or self.staff))

    def get(self, venue_id, user=None):
        return self.client.get(
            f"{VENUES_URL}{venue_id}", headers=self.auth_headers(user or self.staff))

    def history(self, venue_id, user=None):
        return self.client.get(
            f"{VENUES_URL}{venue_id}/history", headers=self.auth_headers(user or self.staff))

    def count(self, name):
        return Venue.query.filter_by(name=name).count()

    def v101(self):
        """V-101 Orchard Hall with capacity 120."""
        response = self.add(FULL)
        self.assertEqual(response.status_code, 201)
        return response.get_json()["venue"]["id"]


class AddVenueTests(CatalogueTestCase):
    def test_tc1_add_venue_with_every_detail(self):  # AC1
        response = self.add(FULL)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["message"])
        venue_id = response.get_json()["venue"]["id"]
        reopened = self.get(venue_id).get_json()
        for key, value in FULL.items():
            expected = [v.lower() for v in value] if key == "room_layouts" else value
            self.assertEqual(reopened[key], expected, key)
        self.assertEqual(self.count("Orchard Hall"), 1)

    def test_tc2_name_is_required(self):  # AC2
        for name in (None, "", "   "):
            body = {**FULL, "name": name}
            response = self.add(body)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(response.get_json()["fields"]), ["name"])
        self.assertEqual(Venue.query.count(), 0)

    def test_tc3_location_is_required(self):  # AC2
        response = self.add({"name": "Orchard Hall", "capacity": 120, "location": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.get_json()["fields"]), ["location"])
        self.assertEqual(self.count("Orchard Hall"), 0)

    def test_tc4_capacity_is_required(self):  # AC2
        response = self.add({"name": "Orchard Hall", "location": "12 Orchard Road"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.get_json()["fields"]), ["capacity"])
        self.assertEqual(self.count("Orchard Hall"), 0)

    def test_tc5_capacity_of_one_is_accepted(self):  # AC2
        body = {"name": "Interview Booth", "location": "Level 2, 12 Orchard Road", "capacity": 1}
        response = self.add(body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.get(response.get_json()["venue"]["id"]).get_json()["capacity"], 1)

    def test_tc6_capacity_of_zero_is_rejected(self):  # AC2
        body = {"name": "Interview Booth", "location": "Level 2, 12 Orchard Road", "capacity": 0}
        response = self.add(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["fields"]["capacity"],
            "Capacity must be a whole number of at least 1.")
        self.assertEqual(self.count("Interview Booth"), 0)

    def test_tc6_negative_capacity_is_rejected(self):  # AC2
        body = {"name": "Interview Booth", "location": "Level 2", "capacity": -5}
        self.assertEqual(self.add(body).status_code, 400)

    def test_tc7_capacity_that_is_not_a_whole_number_is_rejected(self):  # AC2
        for capacity in (50.5, "50.5", "fifty", True, [50]):
            body = {"name": "Marina Room", "location": "8 Marina Boulevard", "capacity": capacity}
            response = self.add(body)
            self.assertEqual(response.status_code, 400, capacity)
            self.assertEqual(
                response.get_json()["fields"]["capacity"],
                "Capacity must be a whole number.", capacity)
        self.assertEqual(self.count("Marina Room"), 0)

    def test_whole_number_sent_as_text_or_with_point_zero_is_accepted(self):  # AC2
        for capacity in ("40", 40.0):
            body = {"name": f"Room {capacity}", "location": "Level 3", "capacity": capacity}
            response = self.add(body)
            self.assertEqual(response.status_code, 201, capacity)
            self.assertEqual(response.get_json()["venue"]["capacity"], 40)


class DefinedListTests(CatalogueTestCase):
    def test_tc8_options_are_the_defined_lists(self):  # AC3
        response = self.client.get("/api/venues/options", headers=self.auth_headers(self.staff))
        self.assertEqual(response.status_code, 200)
        options = response.get_json()
        self.assertEqual(options["facilities"], ["Projector", "Microphone", "Video conferencing"])
        self.assertEqual(options["accessibility_features"], ["Wheelchair ramp", "Hearing loop"])
        self.assertEqual(options["room_layouts"], ["theatre", "classroom", "boardroom", "banquet"])

    def test_tc9_value_outside_a_defined_list_is_rejected(self):  # AC3
        cases = {
            "facilities": ("Jacuzzi", "Facilities"),
            "accessibility_features": ("Moat", "Accessibility features"),
            "room_layouts": ("Mosh pit", "Layouts"),
        }
        for field, (value, label) in cases.items():
            response = self.add({**FULL, field: [value]})
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(label, response.get_json()["error"])
            self.assertIn(field, response.get_json()["fields"])
        self.assertEqual(self.count("Orchard Hall"), 0)

    def test_lists_must_be_lists_of_text(self):  # AC3
        for value in ("Projector", [1], [["Projector"]], {"a": 1}):
            response = self.add({**FULL, "facilities": value})
            self.assertEqual(response.status_code, 400, value)

    def test_layout_names_are_accepted_in_any_case_and_stored_once(self):  # AC3
        response = self.add({**FULL, "room_layouts": ["THEATRE", "theatre", "Classroom"]})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["venue"]["room_layouts"], ["theatre", "classroom"])

    def test_tc10_saved_facility_works_as_a_search_filter(self):  # AC3
        self.add(FULL)
        self.add({"name": "Marina Room", "location": "8 Marina Boulevard", "capacity": 50,
                  "facilities": ["Microphone"]})
        response = self.client.get(
            "/api/venues/search", query_string={"facility": "Projector"},
            headers=self.auth_headers(self.coordinator))
        self.assertEqual(response.status_code, 200)
        names = [venue["name"] for venue in response.get_json()["venues"]]
        self.assertIn("Orchard Hall", names)
        self.assertNotIn("Marina Room", names)

    def test_operating_hours_must_be_usable_when_given(self):  # AC1/AC5
        response = self.add({**FULL, "operating_hours": "whenever"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("operating_hours", response.get_json()["fields"])
        # Left empty, the hours are simply not recorded.
        response = self.add({**FULL, "operating_hours": ""})
        self.assertEqual(response.status_code, 201)
        self.assertIn("operating_hours", response.get_json()["venue"]["not_recorded"])


class EditVenueTests(CatalogueTestCase):
    def test_tc11_edit_shows_when_reopened_and_leaves_the_rest(self):  # AC4
        venue_id = self.v101()
        before = self.get(venue_id).get_json()
        response = self.edit(venue_id, {"capacity": 150})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["message"])
        after = self.get(venue_id).get_json()
        self.assertEqual(after["capacity"], 150)
        self.assertEqual({**after, "capacity": 120}, before)

    def test_edit_can_clear_an_optional_list(self):  # AC4
        venue_id = self.v101()
        self.edit(venue_id, {"facilities": []})
        self.assertEqual(self.get(venue_id).get_json()["facilities"], [])

    def test_edit_is_validated_like_add(self):  # AC2/AC3/AC5
        venue_id = self.v101()
        response = self.edit(venue_id, {"name": "", "capacity": 0, "facilities": ["Jacuzzi"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.get_json()["fields"]), {"name", "capacity", "facilities"})
        self.assertEqual(self.get(venue_id).get_json()["capacity"], 120)

    def test_unknown_venue_is_404(self):
        self.assertEqual(self.edit(self.missing_id(Venue), {"capacity": 5}).status_code, 404)
        self.assertEqual(self.history(self.missing_id(Venue)).status_code, 404)

    def test_unknown_fields_are_rejected(self):  # AC8
        venue_id = self.v101()
        response = self.edit(venue_id, {"is_available": False, "id": 99})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.get_json()["fields"]), {"is_available", "id"})


class ValidationTests(CatalogueTestCase):
    def test_tc12_every_invalid_field_is_named_in_one_reply(self):  # AC5
        body = {**FULL, "name": "", "capacity": 0}
        response = self.add(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.get_json()["fields"]), {"name", "capacity"})
        self.assertEqual(Venue.query.count(), 0)
        self.assertEqual(VenueChange.query.count(), 0)


class SaveFailureTests(CatalogueTestCase):
    def failing(self):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith(("SAVEPOINT", "ROLLBACK", "RELEASE")):
                return
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE")):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        self.addCleanup(lambda: sa_event.contains(self.db.engine, "before_cursor_execute", fail)
                        and sa_event.remove(self.db.engine, "before_cursor_execute", fail))
        return fail

    def test_tc13_failed_edit_changes_nothing_and_can_be_retried(self):  # AC6
        venue_id = self.v101()
        headers = self.auth_headers(self.staff)
        fail = self.failing()
        response = self.client.put(f"{VENUES_URL}{venue_id}", json={"capacity": 150}, headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()["retryable"])
        self.assertIn("could not be saved", response.get_json()["error"])
        sa_event.remove(self.db.engine, "before_cursor_execute", fail)

        self.db.session.expire_all()
        self.assertEqual(self.get(venue_id).get_json()["capacity"], 120)
        self.assertEqual(len(self.history(venue_id).get_json()["history"]), 1)

        retry = self.client.put(f"{VENUES_URL}{venue_id}", json={"capacity": 150}, headers=headers)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(self.get(venue_id).get_json()["capacity"], 150)

    def test_failed_add_creates_no_venue(self):  # AC6
        headers = self.auth_headers(self.staff)
        self.failing()
        response = self.client.post(VENUES_URL, json=FULL, headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.get_json()["retryable"])
        self.db.session.expire_all()
        self.assertEqual(self.count("Orchard Hall"), 0)
        self.assertEqual(VenueChange.query.count(), 0)


class HistoryTests(CatalogueTestCase):
    def test_tc14_add_and_edit_record_who_and_when(self):  # AC7
        body = {"name": "Marina Room", "location": "8 Marina Boulevard", "capacity": 50}
        venue_id = self.add(body, self.staff).get_json()["venue"]["id"]
        self.assertEqual(self.edit(venue_id, {"capacity": 60}, self.staff2).status_code, 200)

        history = self.history(venue_id, self.staff2).get_json()["history"]
        self.assertEqual([h["action"] for h in history], ["added", "edited"])
        self.assertEqual([h["changed_by"]["email"] for h in history],
                         ["venue_staff1@test.example", "venue_staff2@test.example"])
        self.assertEqual(history[1]["changes"], {"capacity": {"from": 50, "to": 60}})
        for entry in history:
            changed = datetime.fromisoformat(entry["changed_at"])
            self.assertLess(abs(datetime.utcnow() - changed), timedelta(minutes=1))

    def test_edit_that_changes_nothing_records_nothing(self):  # AC7
        venue_id = self.v101()
        self.assertEqual(self.edit(venue_id, {"capacity": 120}).status_code, 200)
        self.assertEqual(len(self.history(venue_id).get_json()["history"]), 1)

    def test_rejected_edit_records_nothing(self):  # AC7
        venue_id = self.v101()
        self.edit(venue_id, {"capacity": 0})
        self.assertEqual(len(self.history(venue_id).get_json()["history"]), 1)

    def test_coordinator_can_not_read_history_but_venue_staff_can(self):  # AC8
        venue_id = self.v101()
        self.assertEqual(self.history(venue_id, self.coordinator).status_code, 403)
        self.assertEqual(self.history(venue_id, self.staff).status_code, 200)


class AccessTests(CatalogueTestCase):
    def test_tc15_coordinator_cannot_add_or_edit(self):  # AC8
        venue_id = self.v101()
        self.assertEqual(self.edit(venue_id, {"capacity": 200}, self.coordinator).status_code, 403)
        self.assertEqual(self.add({**FULL, "name": "Other"}, self.coordinator).status_code, 403)
        self.assertEqual(self.get(venue_id).get_json()["capacity"], 120)
        self.assertEqual(self.count("Other"), 0)

    def test_tc16_attendee_cannot_add(self):  # AC8
        body = {"name": "Rogue Room", "location": "1 Test Street", "capacity": 10}
        self.assertEqual(self.add(body, self.attendee).status_code, 403)
        self.assertEqual(self.count("Rogue Room"), 0)
        self.assertEqual(VenueChange.query.count(), 0)

    def test_every_other_role_is_refused(self):  # AC8
        for role in ("organiser", "tech_staff", "coordinator_lead", "admin"):
            user = self.make_user(f"{role}@test.example", role=role)
            self.assertEqual(self.add(FULL, user).status_code, 403, role)
        self.assertEqual(Venue.query.count(), 0)

    def test_role_is_read_from_the_database_not_the_token(self):  # AC8
        token_headers = self.auth_headers(self.staff)
        self.staff.role = "attendee"
        self.db.session.commit()
        response = self.client.post(VENUES_URL, json=FULL, headers=token_headers)
        self.assertEqual(response.status_code, 403)

    def test_login_is_required(self):  # AC8
        self.assertEqual(self.client.post(VENUES_URL, json=FULL).status_code, 401)
        self.assertEqual(self.client.put(f"{VENUES_URL}1", json={}).status_code, 401)
        self.assertEqual(self.client.get(f"{VENUES_URL}options").status_code, 401)

    def test_options_are_for_venue_staff_only(self):  # AC8
        response = self.client.get("/api/venues/options", headers=self.auth_headers(self.attendee))
        self.assertEqual(response.status_code, 403)


class SetupTurnaroundTests(CatalogueTestCase):
    """SCRUM-63 AC9 (reopened): setup and turnaround time per venue, whole minutes 0-1440.

    Sheet cases IS212-US63-TC17 to TC27 (the "Sprint 4 test cases" tab).
    """

    def v101_with(self, setup=30, turnaround=45):
        venue_id = self.v101()
        response = self.edit(venue_id, {"setup_minutes": setup, "turnaround_minutes": turnaround})
        self.assertEqual(response.status_code, 200)
        return venue_id

    def stored(self, venue_id):
        self.db.session.expire_all()
        details = self.get(venue_id).get_json()
        return details["setup_minutes"], details["turnaround_minutes"]

    def test_tc17_set_setup_and_turnaround_and_see_them_on_reopen(self):  # AC9
        venue_id = self.v101()
        response = self.edit(venue_id, {"setup_minutes": 30, "turnaround_minutes": 45})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["venue"]["setup_minutes"], 30)
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_tc18_zero_is_accepted_and_kept_as_zero_not_blank(self):  # AC9 lower boundary
        venue_id = self.v101_with()
        self.assertEqual(
            self.edit(venue_id, {"setup_minutes": 0, "turnaround_minutes": 0}).status_code, 200)
        self.assertEqual(self.stored(venue_id), (0, 0))
        details = self.get(venue_id).get_json()
        # 0 is a recorded value, not "not recorded".
        self.assertNotIn("setup_minutes", details["not_recorded"])
        self.assertNotIn("turnaround_minutes", details["not_recorded"])

    def test_tc19_1440_is_accepted(self):  # AC9 upper boundary
        venue_id = self.v101()
        response = self.edit(venue_id, {"setup_minutes": 1440, "turnaround_minutes": 1440})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored(venue_id), (1440, 1440))

    def test_tc20_setup_of_1441_is_rejected(self):  # AC9 just above the limit
        venue_id = self.v101_with()
        response = self.edit(venue_id, {"setup_minutes": 1441, "turnaround_minutes": 45})
        self.assertEqual(response.status_code, 400)
        fields = response.get_json()["fields"]
        self.assertEqual(list(fields), ["setup_minutes"])
        self.assertIn("whole number", fields["setup_minutes"])
        self.assertIn("0 to 1440", fields["setup_minutes"])
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_tc21_turnaround_of_1441_is_rejected(self):  # AC9 just above the limit
        venue_id = self.v101_with()
        response = self.edit(venue_id, {"setup_minutes": 30, "turnaround_minutes": 1441})
        self.assertEqual(response.status_code, 400)
        fields = response.get_json()["fields"]
        self.assertEqual(list(fields), ["turnaround_minutes"])
        self.assertIn("0 to 1440", fields["turnaround_minutes"])
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_tc22_negative_minutes_are_rejected(self):  # AC9 just below the limit
        venue_id = self.v101_with()
        first = self.edit(venue_id, {"setup_minutes": -1, "turnaround_minutes": 45})
        second = self.edit(venue_id, {"setup_minutes": 30, "turnaround_minutes": -1})
        self.assertEqual(first.status_code, 400)
        self.assertEqual(list(first.get_json()["fields"]), ["setup_minutes"])
        self.assertEqual(second.status_code, 400)
        self.assertEqual(list(second.get_json()["fields"]), ["turnaround_minutes"])
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_tc23_values_that_are_not_whole_numbers_are_rejected(self):  # AC9
        venue_id = self.v101_with()
        for body, field in (
            ({"setup_minutes": 30.5, "turnaround_minutes": 45}, "setup_minutes"),
            ({"setup_minutes": 30, "turnaround_minutes": "abc"}, "turnaround_minutes"),
            ({"setup_minutes": True}, "setup_minutes"),
            ({"turnaround_minutes": [45]}, "turnaround_minutes"),
        ):
            response = self.edit(venue_id, body)
            self.assertEqual(response.status_code, 400, body)
            self.assertIn("whole number", response.get_json()["fields"][field], body)
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_tc24_a_venue_with_none_set_uses_zero(self):  # AC9
        venue_id = self.v101()
        details = self.get(venue_id).get_json()
        self.assertIsNone(details["setup_minutes"])
        self.assertIsNone(details["turnaround_minutes"])
        self.assertIn("setup_minutes", details["not_recorded"])
        venue = self.db.session.get(Venue, venue_id)
        # The value every scheduling check uses (SCRUM-84 reads it from here).
        self.assertEqual(scheduling.buffers(venue), (0, 0))

    def test_tc24_a_venue_with_values_set_reports_them(self):  # AC9
        venue = self.db.session.get(Venue, self.v101_with(30, 45))
        self.assertEqual(scheduling.buffers(venue), (30, 45))

    def test_tc25_out_of_range_value_sent_directly_is_rejected(self):  # AC9
        venue_id = self.v101_with()
        response = self.client.put(
            f"{VENUES_URL}{venue_id}", headers=self.auth_headers(self.staff),
            json={"setup_minutes": 1441, "turnaround_minutes": 45})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Setup time", response.get_json()["error"])
        self.assertEqual(self.stored(venue_id), (30, 45))
        self.assertEqual(len(self.history(venue_id).get_json()["history"]), 2)  # add + the 30/45 edit

    def test_tc26_coordinator_cannot_set_setup_or_turnaround(self):  # AC9 + AC8
        venue_id = self.v101_with()
        response = self.edit(venue_id, {"setup_minutes": 10}, self.coordinator)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.edit(venue_id, {"setup_minutes": 10}, self.attendee).status_code, 403)
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_tc26_coordinator_can_still_read_the_values(self):  # AC9: read-only
        venue_id = self.v101_with()
        response = self.get(venue_id, self.coordinator)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["setup_minutes"], 30)

    def test_tc27_changing_the_turnaround_records_who_and_when(self):  # AC9 + AC7
        venue_id = self.v101_with()
        self.assertEqual(
            self.edit(venue_id, {"turnaround_minutes": 60}, self.staff2).status_code, 200)
        entry = self.history(venue_id).get_json()["history"][-1]
        self.assertEqual(entry["action"], "edited")
        self.assertEqual(entry["changed_by"]["email"], "venue_staff2@test.example")
        self.assertEqual(entry["changes"], {"turnaround_minutes": {"from": 45, "to": 60}})
        changed = datetime.fromisoformat(entry["changed_at"])
        self.assertLess(abs(datetime.utcnow() - changed), timedelta(minutes=1))

    def test_a_venue_can_be_added_with_setup_and_turnaround(self):  # AC9
        response = self.add({**FULL, "setup_minutes": 15, "turnaround_minutes": 20})
        self.assertEqual(response.status_code, 201)
        venue = response.get_json()["venue"]
        self.assertEqual((venue["setup_minutes"], venue["turnaround_minutes"]), (15, 20))

    def test_values_sent_as_numeric_text_are_accepted(self):  # AC9
        venue_id = self.v101_with()
        self.assertEqual(
            self.edit(venue_id, {"setup_minutes": "15", "turnaround_minutes": "20"}).status_code, 200)
        self.assertEqual(self.stored(venue_id), (15, 20))

    def test_clearing_a_value_goes_back_to_none_set(self):  # AC9
        venue_id = self.v101_with()
        self.assertEqual(
            self.edit(venue_id, {"setup_minutes": None, "turnaround_minutes": ""}).status_code, 200)
        self.assertEqual(self.stored(venue_id), (None, None))

    def test_editing_other_fields_leaves_the_values_alone(self):  # AC9
        venue_id = self.v101_with()
        self.assertEqual(self.edit(venue_id, {"capacity": 130}).status_code, 200)
        self.assertEqual(self.stored(venue_id), (30, 45))

    def test_a_bad_setup_time_is_named_with_other_invalid_fields(self):  # AC5 + AC9
        venue_id = self.v101()
        response = self.edit(venue_id, {"capacity": 0, "setup_minutes": 1441})
        self.assertEqual(sorted(response.get_json()["fields"]), ["capacity", "setup_minutes"])


if __name__ == "__main__":
    unittest.main()
