# End-to-end tests

`test_journeys.py` drives the running system as users do: a real browser (Playwright, Chromium) through the React app, against the Flask API, PostgreSQL, Redis, and the Celery worker and beat. Week 9 recommends keeping a few such tests for the critical journeys; these are ours:

- **E2E-01 to E2E-09:** each role's step from a draft to a confirmed event and a registration, checked on the page and in the database.
- **CON-01 to CON-03:** genuinely simultaneous requests, which the backend suite can't send because each of its tests runs inside one rolled-back transaction.
- **CON-04:** a tentative hold expiring on its own through Celery beat and the worker.

CI runs them in the `e2e` job (`.github/workflows/tests.yml`) on every pull request. CON-04 waits up to one beat interval (5 minutes), so CI runs it only after merging to `main` (`E2E_SLOW=1`), as Week 9 suggests for slower checks.

## Running them locally

You need a throwaway local PostgreSQL and Redis. From the repository root:

```sh
# 1. A database with the demo data (never Supabase: these tests change rows)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
(cd backend && OWNER_DATABASE_URL=$DATABASE_URL TEST_ROLE_PASSWORD=local python ci/build_test_database.py \
  && DEMO_PASSWORD=demo-password python seed_demo.py)

# 2. The stack, each in its own terminal (from backend/, then frontend/)
flask --app wsgi run --port 5000
celery -A celery_worker.celery worker --loglevel=info
celery -A celery_worker.celery beat --loglevel=info
npx vite --port 5173 --strictPort

# 3. The tests
pip install -r e2e/requirements.txt && python -m playwright install --with-deps chromium
DEMO_PASSWORD=demo-password python -m unittest discover -s e2e -v
```

Each test starts from the seeded demo data and touches its own events, so rebuild the database (step 1) before running the tests again. Screenshots of where each browser test ended are saved in `e2e/output/`; CI keeps them as the `e2e-screenshots` artifact.
