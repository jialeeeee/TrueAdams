"""CF08 "Venue Staff can create, edit and delete venue records": deleting is archiving.

Each test names the case it automates in docs/test-cases/CF08-archive-venue.md (TC-CF08-xx).

Model (db/venue_archive.sql): Venue.archived_at, naive UTC, NULL for a venue in use. Who
archived or restored it is a venue_changes row (action "archived" / "restored").

Endpoints (JWT required, else 401; the User row is loaded on every request)
    POST /api/venues/<id>/archive   Venue Staff. 200 {"message", "venue": details + archived_at}
        409 {"reason": "archived" | "upcoming_bookings", "bookings": [ids]}
    POST /api/venues/<id>/restore   Venue Staff. 200 {"message", "venue"}; 409 "not_archived"
    Checks: 401 -> 404 -> 403 -> 409 -> 503 {"retryable": true}.
    GET  /api/venues/                leaves archived venues out; Venue Staff may add
                                     ?archived=include, which lists them with archived_at
    GET  /api/venues/search          leaves them out
    POST /api/venues/bookings        409 {"reason": "archived"}
    PUT  /api/venues/<id>            409 {"reason": "archived"}
"""

from datetime import datetime, timedelta
from unittest import mock

from sqlalchemy import event as sa_event
from sqlalchemy.exc import OperationalError

from app.models import Event, Venue, VenueBooking, VenueChange
from app.venues import routes as venue_routes
from tests.base import AppTestCase

NOW = datetime(2027, 5, 1, 9, 0)
SESSION_EXPIRED = "Your session is no longer valid. Please log in again."


class ArchiveTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.gus = self.make_user(role="venue_staff")
        self.alice = self.make_user(role="coordinator")
        self.organiser = self.make_user(role="organiser")
        self.hall = self.make_venue(name="Archive Test Hall", capacity=200)
        self.annex = self.make_venue(name="Archive Test Annex", capacity=50)
        self.event = Event(title="Harbour Talk", status="approved",
                           organiser_id=self.organiser.id, coordinator_id=self.alice.id,
                           start_time=datetime(2027, 6, 10, 10, 0),
                           end_time=datetime(2027, 6, 10, 12, 0), expected_attendance=40,
                           venue_requirements="Hall")
        self.db.session.add(self.event)
        self.db.session.commit()
        for module in (venue_routes,):
            clock = mock.patch.object(module, "singapore_now", return_value=NOW)
            clock.start()
            self.addCleanup(clock.stop)

    def book(self, status, start=datetime(2027, 6, 10, 10, 0), end=datetime(2027, 6, 10, 12, 0),
             **extra):
        row = VenueBooking(event_id=self.event.id, venue_id=self.hall.id, status=status,
                           start_time=start, end_time=end, venue_requirements="x",
                           requested_by_id=self.alice.id, **extra)
        self.db.session.add(row)
        self.db.session.commit()
        return row

    def post(self, action, user=None, venue=None, headers=None):
        if headers is None:
            headers = self.auth_headers(user or self.gus)
        return self.client.post(f"/api/venues/{(venue or self.hall).id}/{action}",
                                headers=headers)

    def archived(self, venue=None):
        response = self.post("archive", venue=venue)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def listed_ids(self, user=None, query=""):
        response = self.client.get(f"/api/venues/{query}",
                                   headers=self.auth_headers(user or self.alice))
        self.assertEqual(response.status_code, 200, response.get_json())
        return {venue["id"]: venue for venue in response.get_json()["venues"]}

    def stored(self, venue=None):
        self.db.session.expire_all()
        return self.db.session.get(Venue, (venue or self.hall).id)

    def history(self, venue=None):
        self.db.session.expire_all()
        return [(row.action, row.changed_by_id) for row in VenueChange.query.filter_by(
            venue_id=(venue or self.hall).id).order_by(VenueChange.id)]

    def assert_error(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.get_json())
        body = response.get_json()
        self.assertTrue(body.get("error", "").strip())
        self.assertNotIn("venue", body)
        return body


class ArchiveTests(ArchiveTestCase):
    # TC-CF08-01 · A1
    def test_tc_cf08_01_archiving_removes_the_venue_from_the_catalogue(self):
        before = datetime.utcnow()

        body = self.archived()

        venue = self.stored()
        self.assertTrue(before <= venue.archived_at <= datetime.utcnow())
        self.assertEqual(body["venue"]["archived_at"], venue.archived_at.isoformat())
        self.assertIn("was deleted", body["message"])
        self.assertEqual(self.history(), [("archived", self.gus.id)])
        for user in (self.alice, self.gus):
            listed = self.listed_ids(user)
            self.assertNotIn(self.hall.id, listed)
            self.assertNotIn("archived_at", listed[self.annex.id])

    # TC-CF08-01 · A1
    def test_tc_cf08_01_venue_staff_can_list_archived_venues(self):
        self.archived()

        listed = self.listed_ids(self.gus, "?archived=include")
        self.assertEqual(listed[self.hall.id]["archived_at"], self.stored().archived_at.isoformat())
        self.assertIn(self.annex.id, listed)
        self.assertNotIn(self.hall.id, self.listed_ids(self.alice, "?archived=include"))

    # TC-CF08-02 · A1
    def test_tc_cf08_02_an_archived_venue_is_not_offered_by_search(self):
        def found():
            response = self.client.get("/api/venues/search?min_capacity=1",
                                       headers=self.auth_headers(self.alice))
            self.assertEqual(response.status_code, 200, response.get_json())
            return {result["id"] for result in response.get_json()["venues"]}

        self.assertIn(self.hall.id, found())
        self.archived()
        self.assertNotIn(self.hall.id, found())
        self.assertIn(self.annex.id, found())

    # TC-CF08-03 · A1
    def test_tc_cf08_03_an_archived_venue_cannot_be_requested_or_edited(self):
        self.archived()

        request = self.client.post("/api/venues/bookings", json={
            "event_id": self.event.id, "venue_id": self.hall.id,
            "start_time": "2027-06-10T10:00", "end_time": "2027-06-10T12:00",
            "venue_requirements": "Hall"}, headers=self.auth_headers(self.alice))
        body = self.assert_error(request, 409)
        self.assertEqual(body["reason"], "archived")
        self.assertIn("removed from the catalogue", body["error"])
        self.assertEqual(VenueBooking.query.filter_by(venue_id=self.hall.id).count(), 0)

        edit = self.client.put(f"/api/venues/{self.hall.id}", json={"name": "Renamed"},
                               headers=self.auth_headers(self.gus))
        edited = self.assert_error(edit, 409)
        self.assertEqual(edited["reason"], "archived")
        self.assertEqual(edited["error"],
                         "This venue has been deleted. Restore it before editing it.")
        self.assertEqual(self.stored().name, "Archive Test Hall")

    # TC-CF08-04 · A1
    def test_tc_cf08_04_its_records_are_kept_and_still_readable(self):
        past = self.book("confirmed", start=datetime(2027, 4, 1, 10, 0),
                         end=datetime(2027, 4, 1, 12, 0))
        self.archived()

        details = self.client.get(f"/api/venues/{self.hall.id}",
                                  headers=self.auth_headers(self.alice))
        self.assertEqual(details.status_code, 200)
        self.assertIn("archived_at", details.get_json())
        self.db.session.expire_all()
        self.assertEqual(self.db.session.get(VenueBooking, past.id).status, "confirmed")
        history = self.client.get(f"/api/venues/{self.hall.id}/history",
                                  headers=self.auth_headers(self.gus)).get_json()["history"]
        self.assertEqual([entry["action"] for entry in history], ["archived"])


class UpcomingBookingTests(ArchiveTestCase):
    # TC-CF08-05 · A2
    def test_tc_cf08_05_upcoming_bookings_stop_the_venue_being_archived(self):
        for status, extra in (("confirmed", {}), ("pending", {}),
                              ("tentative", {"hold_expires_at": NOW + timedelta(days=1)})):
            with self.subTest(status=status):
                booking = self.book(status, **extra)
                body = self.assert_error(self.post("archive"), 409)
                self.assertEqual((body["reason"], body["bookings"]),
                                 ("upcoming_bookings", [booking.id]))
                self.assertIn("1 upcoming booking,", body["error"])
                self.assertIn("Record it as unavailable", body["error"])
                # SCRUM-101: the customer's word is "delete" (G4 #15).
                self.assertIn("can't be deleted yet", body["error"])
                self.assertIsNone(self.stored().archived_at)
                self.db.session.delete(booking)
                self.db.session.commit()

    # TC-CF08-05 · A2
    def test_tc_cf08_05_several_upcoming_bookings_are_counted(self):
        self.book("confirmed")
        self.book("pending", start=datetime(2027, 6, 11, 10, 0), end=datetime(2027, 6, 11, 12, 0))

        self.assertIn("2 upcoming bookings,", self.assert_error(self.post("archive"), 409)["error"])

    # TC-CF08-05 · A2
    def test_tc_cf08_05_past_ended_and_dead_bookings_do_not(self):
        self.book("confirmed", start=datetime(2027, 4, 1, 10, 0), end=NOW)
        for status in ("rejected", "cancelled", "replaced", "expired"):
            self.book(status)
        self.book("tentative", hold_expires_at=NOW)
        other = self.book("confirmed")
        other.venue_id = self.annex.id
        self.db.session.commit()

        self.archived()


class AccessTests(ArchiveTestCase):
    # TC-CF08-06 · A4
    def test_tc_cf08_06_who_may_archive_and_restore_and_in_what_order(self):
        ghost = self.make_user(role="venue_staff")
        ghost_headers = self.auth_headers(ghost)
        self.db.session.delete(ghost)
        self.db.session.commit()
        missing = self.make_venue(name="Gone")
        missing_id = missing.id
        self.db.session.delete(missing)
        self.db.session.commit()

        for action in ("archive", "restore"):
            with self.subTest(action=action):
                self.assertEqual(self.post(action, headers={}).status_code, 401)
                self.assertEqual(self.assert_error(self.post(action, headers=ghost_headers),
                                                   401)["error"], SESSION_EXPIRED)
                gone = self.client.post(f"/api/venues/{missing_id}/{action}",
                                        headers=self.auth_headers(self.gus))
                self.assert_error(gone, 404)
                for user in (self.alice, self.organiser, self.make_user(role="tech_staff")):
                    self.assert_error(self.post(action, user=user), 403)
        self.assertIsNone(self.stored().archived_at)
        self.assertEqual(self.history(), [])

    # TC-CF08-06 · A4
    def test_tc_cf08_06_an_additional_venue_staff_role_is_enough(self):
        staff = self.make_user(role="coordinator", additional_roles=["venue_staff"])

        self.assertEqual(self.post("archive", user=staff).status_code, 200)


class RestoreTests(ArchiveTestCase):
    # TC-CF08-07 · A3
    def test_tc_cf08_07_restoring_puts_the_venue_back(self):
        self.archived()

        response = self.post("restore")

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn("back in the catalogue", response.get_json()["message"])
        self.assertNotIn("archived_at", response.get_json()["venue"])
        self.assertIsNone(self.stored().archived_at)
        self.assertIn(self.hall.id, self.listed_ids())
        self.assertEqual(self.history(), [("archived", self.gus.id), ("restored", self.gus.id)])
        edit = self.client.put(f"/api/venues/{self.hall.id}", json={"name": "Renamed Hall",
                                                                    "location": "Level 1",
                                                                    "capacity": 200},
                               headers=self.auth_headers(self.gus))
        self.assertEqual(edit.status_code, 200, edit.get_json())

    # TC-CF08-07 · A3
    def test_tc_cf08_07_archiving_twice_or_restoring_a_venue_in_use_is_refused(self):
        self.assertEqual(self.assert_error(self.post("restore"), 409)["reason"], "not_archived")
        self.archived()
        self.assertEqual(self.assert_error(self.post("archive"), 409)["reason"], "archived")
        self.assertEqual(self.history(), [("archived", self.gus.id)])


class FailureTests(ArchiveTestCase):
    def while_failing(self, action):
        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO venue_changes"):
                raise OperationalError(statement, parameters, Exception("simulated outage"))

        self.db.session.expire_all()
        sa_event.listen(self.db.engine, "before_cursor_execute", fail)
        try:
            return self.post(action)
        finally:
            sa_event.remove(self.db.engine, "before_cursor_execute", fail)

    # TC-CF08-08 · A5
    def test_tc_cf08_08_a_failed_archive_or_restore_changes_nothing(self):
        body = self.assert_error(self.while_failing("archive"), 503)
        self.assertEqual((body["error"], body["retryable"]),
                         ("The venue was not deleted. Please try again.", True))
        self.assertIsNone(self.stored().archived_at)

        self.archived()
        archived_at = self.stored().archived_at
        body = self.assert_error(self.while_failing("restore"), 503)
        self.assertEqual(body["error"], "The venue was not restored. Please try again.")
        self.assertEqual(self.stored().archived_at, archived_at)
        self.assertEqual(self.history(), [("archived", self.gus.id)])
