# AGENTS.md — ConnectSphere (TrueAdams)

Instructions for AI coding agents (and teammates) working in this repository. Read this before changing code. It records the conventions and contracts that are not obvious from any single file.

ConnectSphere handles event planning, venue booking, resource allocation and attendee registration. Work is split into Jira stories (`SCRUM-NN`) that teammates build in parallel, so shared code is a contract: if a change would affect another story's behaviour, stop and tell the user rather than changing it.

**Source of truth, in order:** the story's acceptance criteria and its test-case document in [docs/test-cases/](docs/test-cases/) (what to build) → this file (how to build it here) → [README.md](README.md) (setup) → [C4 diagrams/c2.txt](C4%20diagrams/c2.txt) (architecture). [Slides + Docs/](Slides%20+%20Docs/) is course material: read it for process expectations, never edit it.

## Commands

```sh
# Backend (from backend/)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt           # app + test dependencies
cp .env.example .env                          # first time only; fill in DATABASE_URL, TEST_DATABASE_URL, SMTP
flask --app wsgi run                          # API on http://localhost:5000
python -m unittest discover -v                # whole suite (what CI runs)
python -m unittest -v tests.test_event_drafts # one file
coverage run -m unittest discover && coverage report   # fails below 100% (.coveragerc)
DEMO_PASSWORD=... python seed_demo.py         # demo accounts and events (see the script; --allow-remote for Supabase)

# Celery worker (needs Redis: docker compose up redis)
celery -A celery_worker.celery worker --loglevel=info
celery -A celery_worker.celery beat --loglevel=info   # timed tasks (hold expiry check)

# Frontend (from frontend/)
npm install
cp .env.example .env                          # first time only
npm run dev                                   # http://localhost:5173, proxies /api to :5000
npm test                                      # Vitest, run once
npm run coverage                              # Vitest with coverage; fails below 100% (vitest.config.js)

# Everything except the frontend
docker compose up --build                     # backend (gunicorn) + worker + beat + Redis
```

- CI ([.github/workflows/tests.yml](.github/workflows/tests.yml)) runs on pushes and PRs to `main`, in three jobs:
  - `unittest` runs the whole backend suite on Python 3.12 against a throwaway PostgreSQL 17 inside the runner, built from the models by [backend/ci/build_test_database.py](backend/ci/build_test_database.py), then the backend coverage gate. It takes about a minute; against Supabase in Tokyo the same suite took 30–60.
  - `vitest` runs the frontend suite with coverage (`npm run coverage`) on Node 20.
  - `supabase-schema` runs `tests.test_app_factory` against Supabase, so a model that Supabase doesn't match (for example, a `db/*.sql` script that hasn't been run) still fails CI.
- **Backend coverage must stay at 100%** ([backend/.coveragerc](backend/.coveragerc) makes `coverage report` fail below it): give every new line a test, or mark it `# pragma: no cover` with the reason it can't have one. **Frontend coverage must stay at 100% too** ([frontend/vitest.config.js](frontend/vitest.config.js) makes `npm run coverage` fail below it): test every branch, including fallbacks for data the server didn't record and failures with no server message, or mark code that can't be reached `/* v8 ignore next */` with a comment saying why. CI runs both and fails the PR if either does.
- Locally, both the app and the tests use the team's Supabase Postgres; the backend tests need `TEST_DATABASE_URL` in `backend/.env` and fail at start-up without it. A full run against Supabase takes about 30 minutes. For a quick run, build a local PostgreSQL with `ci/build_test_database.py` (it refuses any host but localhost) and point `TEST_DATABASE_URL` at its `connectsphere_test` role, as CI does.
- `SQLAlchemy` is pinned to 2.0.x on purpose (2.1 switches `postgresql://` to psycopg 3; we use psycopg2). Do not upgrade it casually.

## Architecture: where code goes

React SPA → Flask monolith → Supabase Postgres, with Celery + Redis for background email. See the C4 container diagram.

| Area | Location | Rules |
|---|---|---|
| App factory | [backend/app/\_\_init\_\_.py](backend/app/__init__.py) | `create_app(config_class)`. Registers one blueprint per domain module, all under `/api/...`. `test_all_blueprints_are_registered_under_api` fails if a route lives outside `/api` or a blueprint is added without updating it. |
| Domain modules | `backend/app/<module>/routes.py` | `auth`, `events`, `venues`, `resources`, `registrations`, `notifications`. Each is a `Blueprint`; helpers and constants live in the same module unless shared. |
| Shared domain logic | e.g. [backend/app/venues/scheduling.py](backend/app/venues/scheduling.py) | Pull logic out of `routes.py` when two stories need it (availability and search both use `scheduling`). |
| Models | [backend/app/models.py](backend/app/models.py) | All SQLAlchemy models in one file. Must match the Supabase tables exactly (see Schema). |
| Config | [backend/app/config.py](backend/app/config.py) | `Config` reads `backend/.env`; `TestConfig` is the test suite's. Never hardcode secrets or URLs. |
| Background jobs | [backend/app/tasks.py](backend/app/tasks.py) | Celery tasks: `send_notification_email`, and `check_hold_expiries` (SCRUM-86), which Celery beat runs every 5 minutes from `beat_schedule` in `create_app`. Registered via `celery_worker.py`. A timed task does its work in a module of its own (e.g. `venues/hold_expiry.py`) and is tested by calling the task with "now" patched. |
| Schema changes | `backend/db/*.sql` | Hand-run SQL scripts, one per story. No migration tool. |
| Frontend pages | `frontend/src/pages/<Name>Page.jsx` + `<Name>Page.test.jsx` | One page per screen, route added in [App.jsx](frontend/src/App.jsx). If users reach it directly, add it to `NAV_LINKS` there with the roles whose endpoint it loads (the nav shows each role its own links; it is not a permission check). |
| API calls | [frontend/src/api/client.js](frontend/src/api/client.js) | Always use this axios client. It adds the bearer token from `sessionStorage["access_token"]`. |
| Shared UI helpers | `frontend/src/utils/` | e.g. `statusLabel`, `formatSavedAt`. |

Stubs (they return **501** or an empty list) that are free to be built by their story: `POST /api/events/`, `POST /api/auth/register` and everything under `/api/resources` (signed-in users only). `GET /api/events/` (SCRUM-74), `POST /api/venues/` (SCRUM-63) and `GET /api/registrations/` (SCRUM-68) are built. In-app notifications are listed at `GET /api/notifications/` and marked read at `POST /api/notifications/<id>/read`, shown on the Notifications page. Keep the URL when implementing one. `POST /api/events/<id>/change-requests` is built (SCRUM-46, the event's organiser only); `SCRUM-52`'s `requires_review.next_step` points at it via `url_for`, so keep its function name `submit_change_request`. The event's coordinator reviews and decides a request at `GET /api/events/<id>/change-requests/<request id>` and `POST …/decision` (SCRUM-70); accepting one applies its values to the event.

## Backend conventions — follow the existing pattern

### Who is calling
- Login (`POST /api/auth/login`) issues a JWT whose identity is `str(user.id)`. Protected routes use `@jwt_required()`.
- **Load the `User` row on every request** (`_current_user()` in events, `_require_viewer()` in venues) and check its roles from the database, not from token claims, so role changes apply without re-issuing tokens. A missing or unparsable identity is a 401: `"Your session is no longer valid. Please log in again."`
- **A user may hold more than one role** (CF01, G4 clarification #22): `User.role` is the main one (it picks the home page) and `User.additional_roles` lists the others. Check roles only through [backend/app/roles.py](backend/app/roles.py): `has_role(user, ROLE)`, `has_any_role(user, ROLES)`, and `holding(ROLES)` to filter `User` queries. Never compare `user.role` directly: it misses the other roles. Holding a role never grants a relationship to an event.
- Roles in use: `admin`, `coordinator`, `coordinator_lead` (Event Coordinator Lead, SCRUM-83), `organiser`, `venue_staff`, `tech_staff`, `safety_officer` (SCRUM-90/91/92), `attendee` (default). Define who may do what as a module-level set (`ASSIGNER_ROLES`, `VENUE_VIEWER_ROLES`, …) with a comment, not inline string checks.
- "The event's coordinator" means `has_role(user, "coordinator") and event.coordinator_id == user.id` (`_is_current_coordinator`). An organiser owns an event through `event.organiser_id`.

### Order of checks and status codes
Check in this order and return the first failure: **401** (no valid user) → **404** (record missing) → **403** (not allowed) → **400/422** (bad input) → **409** (state forbids it, e.g. a non-draft, a cancelled event). Several test-case documents depend on this order (e.g. SCRUM-29 `_own_draft`: 401, 404, 403, 409). A refusal must never leak details of a record the caller may not see; `test_authorization.py` checks this.

### Responses
- Errors are `{"error": "<plain sentence>", ...extra}` via the module's `_error(message, status, **extra)`. Field problems add `field` or `fields`; missing submission fields add `missing`.
- Messages are shown to users verbatim: plain, specific sentences that say what to do next. No stack traces, no other users' private data.
- Empty lists come back with a human `message` (`"You have no draft event requests."`) and `message: None` when there are results.
- Return explicit payload dicts built by `_..._payload()` helpers. Never return a model object or `__dict__`.
- `_Rejected(message, status_code, **extra)` is the local pattern for bailing out of nested helpers; catch it in the route and turn it into `_error(...)`.

### Database access
- Wrap every read and write a route depends on in `try: ... except SQLAlchemyError: db.session.rollback(); return _error(..., 503, retryable=True)`. A failed load must be reported as a failure, never as "not recorded" or "available".
- Validate the whole request before changing anything, so a refused save changes nothing.
- When a change and its in-app `Notification` belong together, add both and `commit()` once. Queue the email (`tasks.send_notification_email.delay(...)`) **after** the commit and treat a queue failure as non-fatal: log it and report `"notification": {"in_app": True, "email_queued": False}` (see `_queue_decision_email`).

### Data meaning
- **NULL means "not recorded".** For venue characteristics an empty list, `False` or `0` is a recorded fact, so those columns have no defaults and the API distinguishes them (`not_recorded` lists, `_recorded()` helper).
- **Times:** event, booking and block times are Singapore local time stored as naive `timestamp`s; audit timestamps (`created_at`, `last_saved_at`, `submitted_at`, `decided_at`, `coordinator_assigned_at`) are naive UTC from `datetime.utcnow()`. Periods are half-open `[start, end)`, so touching periods do not overlap. Use `scheduling.overlapping()` rather than writing your own comparison.
- Event statuses in use: `draft`, `submitted`, `under_review`, `approved`, `confirmed` (SCRUM-93), `rejected`, `cancelled`. Approved and confirmed events are published and take registrations (`REGISTRABLE_STATUSES`; SCRUM-93 A4, still an open question). Venue, equipment and change-request workflows need `approved`; SCRUM-88 sends a confirmed event back to `approved` when one of its venues becomes unavailable.
- Venues are never deleted: CF08's delete is archiving (`venues.archived_at`, `POST /api/venues/<id>/archive` and `/restore`). Any new list or search of venues to choose from must leave out archived ones (`Venue.archived_at.is_(None)`).
- Venue booking statuses: `pending`, `tentative` (a hold, SCRUM-87), `expired` (SCRUM-86), `confirmed`, `rejected`, `cancelled`, `replaced` (SCRUM-89: a flagged booking whose replacement was approved, or whose held replacement was confirmed). Confirmed bookings block a venue, and so do tentative holds until their expiry. A hold is expired from its expiry even before the expiry check records it, so read a booking's status through `scheduling.current_status()`.

### Editing an event's planning information (SCRUM-53 / SCRUM-52)
`PATCH /api/events/<id>` saves "normal" fields (`NORMAL_FIELD_VALIDATORS`) directly and refuses "restricted" fields (`RESTRICTED_FIELD_LABELS`: venue, times, expected attendance, venue requirements, registration requirement), returning `requires_review` instead. **When you add a field to `Event`, decide which list it belongs to** (or leave it non-editable) and update the SCRUM-53/52 test cases; past merges did this explicitly.

## Schema changes

There is no migration tool and no `db.create_all()` against Supabase. The live database and local test runs use the same Supabase project; CI's throwaway database is built from the models by `ci/build_test_database.py`.

1. Change the model in `models.py`.
2. Add `backend/db/<story_or_topic>.sql`: wrapped in `begin; … commit;`, idempotent (`if not exists` / `add column if not exists`), with a header comment naming the story, the model it must match, and whether `test_role.sql` must be re-run. New tables `enable row level security`.
3. For a new table, add it to **both** lists in [backend/db/test_role.sql](backend/db/test_role.sql) (the `grant` and the policy loop).
4. **Tell the user** the script must be run in the Supabase SQL editor as the project owner (then `test_role.sql` for new tables) before merging. Agents cannot run it. Until it is run, `test_database_tables_match_the_models` fails for everyone, including CI's `supabase-schema` job.
5. Never edit a script that has already been run on Supabase; add a new one. Never drop or rename a column another story reads without agreeing it with the team.

## Testing

Stories are built test-first. The commit history shows the expected sequence: a written test-case document plus failing automated tests ("TDD, red"), then the implementation.

### Test-case documents (`docs/test-cases/SCRUM-NN-short-name.md`)
Follow the existing documents: user story and links at the top, **Acceptance criteria** (AC1…), **Working assumptions** each tied to an **open question** (Q1…), **Seed data** with a short ID (e.g. `ER-SEED`), test cases `TC-NN-xx` grouped by AC (Traces to · Type · Preconditions · Steps · Expected result · **Automated:** test name), a **Traceability matrix** and **Open questions for the customer**. When behaviour rests on an unanswered question, implement the stated assumption, keep it easy to change (a named constant with a comment, e.g. `MAX_RANGE_DAYS`), and do not present it as agreed.

### Backend tests (`backend/tests/`, `unittest`)
- Subclass `AppTestCase` ([tests/base.py](backend/tests/base.py)). Each test runs in a transaction that is rolled back, against the **real** Supabase `public` tables via the restricted `connectsphere_test` role (rows only, no DDL). Routes may `commit()` normally; they run inside a savepoint.
- **Real data may be present.** Assert only about rows your test created; use `missing_id(Model)` for a non-existent ID and `run_email()` (applied automatically by `make_user`/`seed_users`) so parallel runs don't collide on unique emails.
- Use the `make_*` helpers for one-off rows and `seed_*` with [tests/seed_data.py](backend/tests/seed_data.py) for a story's named seed set. Mint tokens with `auth_headers(user)`.
- Celery runs eagerly in tests (`task_always_eager`); patch `tasks.send_notification_email.delay` (`mock.patch.object`) to assert on emails rather than sending them.
- Name files `test_<feature>.py` (only `test*.py` is collected); shared fixtures without tests go in non-`test` modules (e.g. `tests/scheduling.py`). Group test classes by acceptance criterion and reference the `TC-NN-xx` IDs so the traceability matrix stays accurate.
- A test must be able to fail: if deleting the code under test leaves it passing, fix the test.

### Frontend tests (Vitest + Testing Library)
- Co-locate `<Name>Page.test.jsx` next to the page. Mock the API client (`vi.mock("../api/client.js", ...)`) with responses that mirror the backend contract, and say in a header comment which test-case document and backend test file they correspond to.
- Render inside `MemoryRouter` and drive the page with `userEvent`. Query by role and visible text, as a user would.
- Values duplicated between frontend and backend (e.g. `MAX_WORDS` ↔ `MAX_DECISION_WORDS`) carry a `// Must match ...` comment; change both together.

## Frontend conventions

- React 18 function components with hooks, `react-router-dom` v6, plain JSX (no TypeScript, no CSS framework, no state library).
- Show the backend's `error` message when present and a sensible fallback otherwise (see `explain()` in `ReviewRequestPage.jsx`). A `retryable: true` error should let the user try again without losing their input.
- Show Singapore-time values as recorded (`value.slice(0, 16).replace("T", " ")`); do not convert them through the browser's time zone.

## Code style

- Python: 4-space indentation, module-level `UPPER_CASE` constants with a comment explaining the rule, private helpers prefixed `_`, docstrings on non-obvious helpers. Comments explain *why* and cite the story or assumption (`# SCRUM-29 A7`, `# open question Q2`).
- JavaScript: 2-space indentation, double quotes, semicolons, ES modules with explicit `.jsx`/`.js` extensions in imports.
- Match the surrounding file. Don't reformat or reorganise other stories' code inside a feature PR.

## Git workflow

- Branch per story from `main`: `feature/SCRUM-NN-short-description`. Commit messages start with the story: `SCRUM-NN: <what changed>`.
- Merge `main` into your branch (or the branch you depend on) to pick up others' work; when you merge in a story that adds `Event` fields, re-check the normal/restricted classification and the planning view.
- PRs target `main`; CI must pass. Update the C4 diagram when you add a container, an external system or a major stored entity.
- Commit only files related to the change. Never commit `.env` (both `backend/.env` and `frontend/.env` exist locally and are gitignored), `.venv/`, `node_modules/`, `.coverage`, `__pycache__/`, `.pytest_cache/` or `.DS_Store`.

## Never

- Commit secrets or real connection strings, or point tests at `DATABASE_URL`.
- Use `db.create_all()`, drop tables, or run DDL from app or test code. (`ci/build_test_database.py` is the one exception: it builds CI's throwaway database and refuses any host but localhost.)
- Assume a table is empty in a test, or leave test rows committed outside the rolled-back transaction.
- Trust the JWT's role claim instead of the user's stored roles.
- Report a database failure as an empty result, "not recorded" or "available".
- Save a restricted event field through the normal edit flow.
- Invent an answer to an open customer question and present it as agreed.
