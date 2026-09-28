from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.config import Config, TestConfig
from app.extensions import db
from tests.base import AppTestCase


class AppFactoryTests(AppTestCase):
    def test_health_endpoint_reports_ok(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_tests_never_use_the_apps_own_database_login(self):
        """Tests share the app's tables, so they must use the restricted role."""
        uri = self.app.config["SQLALCHEMY_DATABASE_URI"]

        self.assertNotEqual(uri, Config.SQLALCHEMY_DATABASE_URI)
        self.assertTrue(make_url(uri).username.startswith("connectsphere_test"))
        self.assertIs(self.app.config["TESTING"], True)

    def test_tests_run_as_the_restricted_role(self):
        role, schema = db.session.execute(
            text("select current_user, current_schema()")
        ).one()

        self.assertEqual((role, schema), ("connectsphere_test", "public"))

    def test_restricted_role_cannot_change_the_schema(self):
        can_create, owns_tables = db.session.execute(
            text(
                "select has_schema_privilege('public', 'CREATE'),"
                " exists (select 1 from pg_tables where schemaname = 'public'"
                " and tableowner = current_user)"
            )
        ).one()

        self.assertFalse(can_create)
        self.assertFalse(owns_tables)

    def test_database_tables_match_the_models(self):
        """Fails when a model changes but the Supabase tables were not updated."""
        inspector = inspect(db.session.connection())

        for table in db.metadata.sorted_tables:
            with self.subTest(table=table.name):
                columns = {c["name"] for c in inspector.get_columns(table.name, schema="public")}
                self.assertEqual(columns, set(table.columns.keys()))

    def test_all_blueprints_are_registered_under_api(self):
        self.assertEqual(
            set(self.app.blueprints),
            {"auth", "events", "venues", "resources", "registrations", "notifications"},
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
