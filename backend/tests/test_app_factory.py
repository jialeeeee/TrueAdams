from app.config import TestConfig


def test_health_endpoint_reports_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_test_config_never_points_at_the_real_database(app):
    """Guard against a stray DATABASE_URL leaking in from .env."""
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"
    assert app.config["TESTING"] is True


def test_all_blueprints_are_registered_under_api(app):
    assert set(app.blueprints) == {
        "auth",
        "events",
        "venues",
        "resources",
        "registrations",
    }

    prefixes = {rule.rule for rule in app.url_map.iter_rules()}
    assert all(
        path.startswith("/api") for path in prefixes if not path.startswith("/static")
    )


def test_create_app_accepts_an_explicit_config_class(app):
    assert app.config["JWT_SECRET_KEY"] == TestConfig.JWT_SECRET_KEY
