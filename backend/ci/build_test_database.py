"""Build a throwaway PostgreSQL database for the backend tests in CI.

CI used to run the whole suite against the team's Supabase project in Tokyo. Every
statement then crossed the network: about 23,500 round trips, so 30-60 minutes a run.
This builds a local stand-in, shaped like Supabase:

- every table from app/models.py, which must match Supabase (the separate
  "supabase-schema" CI job checks that it does);
- Row Level Security on for every table, and no CREATE on the public schema;
- the restricted connectsphere_test role and its policies, from db/test_role.sql.

It runs DDL, so it only ever touches a database on this machine: it refuses any other
host. Never point it at Supabase; schema changes there go through db/*.sql.

Usage (from backend/):
    OWNER_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres \\
    TEST_ROLE_PASSWORD=ci-only python ci/build_test_database.py
"""

import os
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parent.parent
# The only hosts this script will build tables on.
LOCAL_HOSTS = {"localhost", "127.0.0.1"}


def main():
    url = sa.engine.make_url(os.environ["OWNER_DATABASE_URL"])
    if url.host not in LOCAL_HOSTS:
        sys.exit(f"Refusing to build tables on {url.host}: this script is only for a "
                 "local CI database.")
    password = os.environ["TEST_ROLE_PASSWORD"]

    sys.path.insert(0, str(BACKEND))
    from app import models  # noqa: F401  (registers every table on db.metadata)
    from app.extensions import db

    engine = sa.create_engine(url)
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        # As on Supabase: other roles can't create objects, and RLS blocks the API.
        conn.execute(sa.text("revoke create on schema public from public"))
        for table in db.metadata.tables:
            conn.execute(sa.text(f'alter table public."{table}" enable row level security'))

    raw = engine.raw_connection()
    try:
        raw.autocommit = True  # test_role.sql has its own begin and commit
        cursor = raw.cursor()
        cursor.execute((BACKEND / "db" / "test_role.sql").read_text(encoding="utf-8"))
        cursor.execute("alter role connectsphere_test password %s", (password,))
    finally:
        raw.close()

    print(f"Built {len(db.metadata.tables)} tables on {url.host}:{url.port}/{url.database}.")


if __name__ == "__main__":
    main()
