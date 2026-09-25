"""Route-level tests.

`test_route_is_reachable` stays valid as the endpoints get implemented — it only
asserts the URL is wired up. `test_stub_returns_not_implemented` is scaffolding:
remove each route from UNIMPLEMENTED_ROUTES and add real behaviour tests as you
build the feature.
"""

from tests.base import AppTestCase

COLLECTION_ENDPOINTS = [
    "/api/events/",
    "/api/venues/",
    "/api/resources/",
    "/api/registrations/",
]

ALL_ROUTES = [
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("GET", "/api/events/"),
    ("POST", "/api/events/"),
    ("POST", "/api/events/1/change-requests"),
    ("GET", "/api/venues/"),
    ("POST", "/api/venues/"),
    ("GET", "/api/venues/1/availability"),
    ("GET", "/api/resources/"),
    ("POST", "/api/resources/1/reservations"),
    ("GET", "/api/registrations/"),
    ("POST", "/api/registrations/"),
]

UNIMPLEMENTED_ROUTES = [
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/events/"),
    ("POST", "/api/events/1/change-requests"),
    ("POST", "/api/venues/"),
    ("GET", "/api/venues/1/availability"),
    ("POST", "/api/resources/1/reservations"),
    ("POST", "/api/registrations/"),
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
