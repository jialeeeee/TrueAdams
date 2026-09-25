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

They use an in-memory SQLite database and run Celery tasks inline, so no
Postgres, Redis, or SMTP server is needed. Shared setup and the `make_*`
helpers live on `AppTestCase` in `backend/tests/base.py`.

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