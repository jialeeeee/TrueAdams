from app.config import TestConfig
from tests.base import AppTestCase


class AppFactoryTests(AppTestCase):
    def test_health_endpoint_reports_ok(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_test_config_never_points_at_the_real_database(self):
        """Guard against a stray DATABASE_URL leaking in from .env."""
        self.assertEqual(self.app.config["SQLALCHEMY_DATABASE_URI"], "sqlite:///:memory:")
        self.assertIs(self.app.config["TESTING"], True)

    def test_all_blueprints_are_registered_under_api(self):
        self.assertEqual(
            set(self.app.blueprints),
            {"auth", "events", "venues", "resources", "registrations"},
        )

        prefixes = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertTrue(
            all(
                path.startswith("/api")
                for path in prefixes
                if not path.startswith("/static")
            )
        )

    def test_create_app_accepts_an_explicit_config_class(self):
        self.assertEqual(self.app.config["JWT_SECRET_KEY"], TestConfig.JWT_SECRET_KEY)
