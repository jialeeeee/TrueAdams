"""Route-level tests.

`test_route_is_reachable` stays valid as the endpoints get implemented — it only
asserts the URL is wired up. `test_stub_returns_not_implemented` is scaffolding:
remove each route from UNIMPLEMENTED_ROUTES and add real behaviour tests as you
build the feature.
"""

from tests.base import AppTestCase

COLLECTION_ENDPOINTS = [
    # GET /api/events/ is no longer a stub (SCRUM-74): see test_event_details.py.
    "/api/resources/",
    # GET /api/registrations/ is no longer a stub (SCRUM-68): see test_event_withdrawal.py.
]

ALL_ROUTES = [
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("GET", "/api/events/"),
    ("POST", "/api/events/"),
    ("POST", "/api/events/1/change-requests"),
    ("GET", "/api/events/1"),
    ("GET", "/api/events/1/reassignment"),
    ("POST", "/api/events/1/reassignment"),
    ("GET", "/api/events/1/coordinator"),
    ("PUT", "/api/events/1/coordinator"),
    ("GET", "/api/events/1/eligible-coordinators"),
    ("GET", "/api/events/drafts"),
    ("POST", "/api/events/drafts"),
    ("GET", "/api/events/drafts/1"),
    ("PUT", "/api/events/drafts/1"),
    ("POST", "/api/events/drafts/1/submit"),
    ("GET", "/api/events/requests"),
    ("GET", "/api/events/mine"),
    ("GET", "/api/events/managed"),
    ("GET", "/api/events/1/review"),
    ("POST", "/api/events/1/review"),
    ("POST", "/api/events/1/decision"),
    ("GET", "/api/events/1/clarifications"),
    ("POST", "/api/events/1/clarifications"),
    ("GET", "/api/notifications/"),
    ("GET", "/api/venues/"),
    ("POST", "/api/venues/"),
    ("PUT", "/api/venues/1"),
    ("GET", "/api/venues/options"),
    ("GET", "/api/venues/1/history"),
    ("GET", "/api/venues/1"),
    ("GET", "/api/venues/1/availability"),
    ("GET", "/api/venues/bookings"),
    ("POST", "/api/venues/bookings"),
    ("POST", "/api/venues/bookings/1/approve"),
    ("POST", "/api/venues/bookings/1/hold"),
    ("PATCH", "/api/venues/bookings/1/hold"),
    ("GET", "/api/venues/holds"),
    ("GET", "/api/resources/"),
    ("POST", "/api/resources/1/reservations"),
    ("GET", "/api/registrations/"),
    ("POST", "/api/registrations/"),
    ("POST", "/api/registrations/1/withdraw"),
]

UNIMPLEMENTED_ROUTES = [
    ("POST", "/api/auth/register"),
    ("POST", "/api/events/"),
    ("POST", "/api/events/1/change-requests"),
    ("POST", "/api/resources/1/reservations"),
]


class RouteTests(AppTestCase):
    def test_route_is_reachable(self):
        for method, path in ALL_ROUTES:
            with self.subTest(method=method, path=path):
                response = self.client.open(path, method=method)

                self.assertNotEqual(
                    response.status_code, 404, f"{method} {path} is not registered"
                )
                self.assertNotEqual(
                    response.status_code, 405, f"{method} {path} rejects its own method"
                )

    def test_collection_endpoints_return_a_json_list(self):
        for path in COLLECTION_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), [])

    def test_stub_returns_not_implemented(self):
        """Delete each case from UNIMPLEMENTED_ROUTES as the endpoint is built."""
        for method, path in UNIMPLEMENTED_ROUTES:
            with self.subTest(method=method, path=path):
                response = self.client.open(path, method=method)

                self.assertEqual(response.status_code, 501)
