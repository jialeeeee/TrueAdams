# TrueAdams

ConnectSphere — event planning, venue booking, resource allocation, and attendee registration. Architecture is documented as C4 DSL in [C4 diagrams/c2.txt](C4%20diagrams/c2.txt).

## Structure

- `frontend/` — React SPA (Vite), talks to the backend via `/api`
- `backend/` — Flask monolith exposing REST routes for Auth, Events, Venues, Resources, Registrations, backed by a Supabase Postgres database
- `backend/celery_worker.py` — Celery worker consuming background jobs (e.g. notification emails) off Redis

## Tests

Backend tests use Python's built-in `unittest`, run from `backend/`:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m unittest                          # whole suite
python -m unittest -v tests.test_models     # one file
coverage run -m unittest && coverage report # with coverage
```

They run against the app's own `public` tables in Supabase, connecting as the
restricted `connectsphere_test` role (set `TEST_DATABASE_URL` in `backend/.env`;
CI reads it from the `TEST_DATABASE_URL` repository secret). That role can read
and write rows but cannot create, alter or drop tables.

- **Each test inserts its own data and rolls it back.** Every test runs in a
  transaction that is rolled back afterwards, so test rows are never saved and
  are never visible to the live app, even if a test crashes. Test data is in
  `backend/tests/seed_data.py`.
- **Real data may be present**, so tests only make assertions about their own
  rows (or hide real rows inside their transaction, e.g. for empty states).
- **Role setup** is in `backend/db/test_role.sql`. Re-run it in the Supabase SQL
  editor after adding a table, so the role gets access to it.
  `test_database_tables_match_the_models` fails if a model and its table differ.
- Celery tasks run inline, so no Redis or SMTP server is needed. Shared setup and
  the `make_*` / `seed_*` helpers live on `AppTestCase` in
  `backend/tests/base.py`.

## Local development

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in DATABASE_URL, SMTP credentials, etc.
flask --app wsgi run
```

Celery worker (needs Redis running, e.g. via `docker compose up redis`):

```bash
cd backend
celery -A celery_worker.celery worker --loglevel=info
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Or bring up backend + worker + Redis together:

```bash
docker compose up --build
```