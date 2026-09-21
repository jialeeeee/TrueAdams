"""Route-level tests.

`test_route_is_reachable` stays valid as the endpoints get implemented — it only
asserts the URL is wired up. The `test_*_is_not_yet_implemented` tests below are
scaffolding: replace each one with real behaviour tests as you build the feature.
"""

import pytest

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


@pytest.mark.parametrize("method,path", ALL_ROUTES)
def test_route_is_reachable(client, method, path):
    response = client.open(path, method=method)

    assert response.status_code != 404, f"{method} {path} is not registered"
    assert response.status_code != 405, f"{method} {path} rejects its own method"


@pytest.mark.parametrize("path", COLLECTION_ENDPOINTS)
def test_collection_endpoints_return_a_json_list(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.get_json() == []


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


@pytest.mark.parametrize("method,path", UNIMPLEMENTED_ROUTES)
def test_stub_returns_not_implemented(client, method, path):
    """Delete each case here as the corresponding endpoint is built."""
    response = client.open(path, method=method)

    assert response.status_code == 501
