# SCRUM-75 — Sign in and sign out

**User story:** As a system user, I want to sign in and out securely so that I can use my account and protect it when I leave.

**Created:** 19 Oct 2026. **Related:** [SCRUM-27 authentication and authorization](SCRUM-27-authentication-authorization.md). Execution is recorded below; no manual browser or end-to-end execution is implied.

## Acceptance criteria (exact Jira wording)

- **AC1:** A user with valid details can sign in and is taken to the home page for their role.
- **AC2:** A user with invalid details is refused with the message "Email or password is incorrect", which does not say which was wrong.
- **AC3:** Submitting an empty email or password is refused and the missing fields are named.
- **AC4:** No session or token is created when sign-in fails.
- **AC5:** If the service is unavailable, access is not granted and the user is told they can retry.
- **AC6:** A signed-in user can sign out. Afterwards protected pages and requests are refused until they sign in again.

## Audit before changes

| AC | Existing status | Reuse / smallest required change |
|---|---|---|
| AC1 | Partially satisfied | Hash verification, JWT and form work; all roles land at Events. Return stored role and select an existing page. |
| AC2 | Partially satisfied | Same 401 for unknown email and wrong password; change text to exact Jira message. |
| AC3 | Partially satisfied | Backend/form reject empty fields; identify only the missing fields. |
| AC4 | Already satisfied | JWT issued only after successful verification; failed form does not store a token. Preserve existing sessions on failed re-login. |
| AC5 | Already satisfied | Lookup SQLAlchemyError produces rollback/503/retryable; form handles service/network failures and retry. |
| AC6 | Not implemented | JWT guards and current-token axios interceptor exist; add sign-out and one shared frontend route guard. |

## Working assumptions and open questions

- **A1 / Q1:** Reuse organiser `/events/mine`, coordinator `/events/managed`, Lead `/events/supervised`, Venue Staff `/venues/bookings`. Attendee, admin, Technical Support Staff and Safety Officer have no dedicated home dashboard; use existing `/` Events catalogue. Confirm these preferred landing pages with the customer. `ROLE_HOME_PATHS` in LoginPage.jsx keeps this easy to change. This chooses navigation only, never permissions or new roles.
- **A2 / Q2:** AC6 is implemented for the active browser session: clear its token, guard all application pages except Login, and let existing API JWT guards reject requests without it. A previously copied JWT remains valid until expiry. Confirm whether server-side invalidation is required; revocation/blacklist/refresh infrastructure is outside this increment and requires approval.

## Seed data (SI-SEED)

Reuse `AuthTests.make_login_user`, `make_user`, `make_venue` and `run_email` in the existing rolled-back local PostgreSQL fixtures. Isolated HTTP tests use user 75 with a real generated password hash and mocked lookup. Frontend tests use mocked API responses and per-test sessionStorage cleanup. No persistent accounts or schema changes.

## Test cases and traceability

Automated references below use `AUTH` = `backend/tests/test_auth.py::AuthTests`, `HTTP` = `backend/tests/test_auth_unit.py::AuthHttpUnitTests`, `LOGIN` = `frontend/src/pages/LoginPage.test.jsx`, `APP` = `frontend/src/App.test.jsx`, `CLIENT` = `frontend/src/api/client.test.js`.

### AC1

**TC-75-01 — Valid credentials and role home**
- **Traces to:** AC1. **Type:** HTTP integration/unit and component.
- **Preconditions:** SI-SEED hashed credentials; role-specific API response for components.
- **Steps:** Sign in; inspect token identity/role; follow navigation for each existing landing and fallback role.
- **Expected:** 200 usable string-user-id JWT and stored role; browser saves token and opens existing role home. No password/hash disclosure.
- **Automated:** AUTH `test_valid_credentials_return_usable_access_token`, `test_login_token_preserves_role_restrictions`; HTTP `test_success_returns_token_and_stored_role`; LOGIN `submits entered credentials to POST /auth/login`, `stores the returned token in sessionStorage and navigates to Events`, `takes %s to its existing home page`.
- **Execution:** Pass (local PostgreSQL integration, isolated HTTP and component).

### AC2

**TC-75-02 — Wrong password and unknown email**
- **Traces to:** AC2, AC4. **Type:** HTTP integration/unit and component.
- **Preconditions:** Known user and an unused email.
- **Steps:** Submit wrong password, then unknown email; display returned 401 in form.
- **Expected:** Both receive exactly `Email or password is incorrect`; no new token/cookie or navigation.
- **Automated:** AUTH `test_invalid_credentials_are_rejected`; HTTP `test_invalid_credentials_never_issue_a_token`; LOGIN `displays the backend 401 explanation without authenticating or navigating`.
- **Execution:** Pass (local PostgreSQL integration, isolated HTTP and component).

### AC3

**TC-75-03 — Missing email, password, or both**
- **Traces to:** AC3, AC4. **Type:** HTTP integration/unit and component.
- **Preconditions:** Login form/API; no active browser token.
- **Steps:** Omit/empty each credential and both; submit form/API.
- **Expected:** API 400 with `missing` field names and named fields in message; form names missing fields before requesting API. No token/cookie or navigation.
- **Automated:** AUTH `test_missing_or_empty_credentials_are_rejected`; HTTP `test_empty_credentials_name_only_missing_fields_without_issuing_token`; LOGIN `gives visible feedback for an empty %s`, `displays a backend 400 validation error`.
- **Execution:** Pass (local PostgreSQL integration, isolated HTTP and component).

### AC4

**TC-75-04 — Failed sign-in creates no session**
- **Traces to:** AC4. **Type:** HTTP integration/unit and component.
- **Preconditions:** Invalid, empty or unavailable sign-in; repeat with a pre-existing browser session.
- **Steps:** Execute TC-75-02/03/05; inspect response and storage. Retry failed login while already signed in.
- **Expected:** No access token or session cookie returned; token issuer not called on failures. Empty browser remains unauthenticated. Existing SCRUM-27 token is preserved on failed re-login.
- **Automated:** Reuses refusal assertions from TC-75-02/03/05; LOGIN `preserves an existing session after a failed %s login`.
- **Execution:** Pass (local PostgreSQL integration, isolated HTTP refusal assertions and component).

### AC5

**TC-75-05 — Service/network failure and retry**
- **Traces to:** AC5, AC4. **Type:** HTTP integration/unit and component.
- **Preconditions:** Simulated lookup outage or rejected network request.
- **Steps:** Submit; observe refusal; restore service and retry unchanged form.
- **Expected:** API 503/retryable and rollback; browser shows retry message without authenticating, keeps input and permits successful retry. No private error details.
- **Automated:** AUTH `test_authentication_service_failure_is_retryable`; HTTP `test_outage_is_retryable_without_issuing_token`; LOGIN `displays retry guidance for an authentication service outage`, `displays retry guidance for a network failure without an HTTP response`, `allows retry after failure and clears the error on successful navigation`.
- **Execution:** Pass (local PostgreSQL integration, isolated HTTP and component).

### AC6

**TC-75-06 — Sign out and sign in again**
- **Traces to:** AC6. **Type:** App component, client adapter and isolated HTTP.
- **Preconditions:** Active browser token and protected managed-events page.
- **Steps:** Sign out; navigate directly/back to protected pages; issue another request through the initialized axios client; sign in again.
- **Expected:** Active token cleared, Login shown, protected pages do not mount/fetch; subsequent client requests omit Authorization; existing protected backend route returns 401 without token; fresh sign-in works. Unrelated browser preferences stay intact. Copied JWT caveat A2 applies.
- **Automated:** APP `signs out, refuses navigation and browser back, then allows sign-in again`, `refuses signed-out direct navigation to %s before loading protected data`; CLIENT `stops authenticating subsequent requests after the session token is removed`, existing `omits Authorization when there is no session token`; HTTP `test_protected_request_without_browser_token_is_refused`.
- **Execution:** Pass (isolated HTTP, component including protected browser-history revisit, and client adapter); copied JWT caveat A2 remains.

**TC-75-07 — Pending overlapping responses after sign-out**
- **Traces to:** AC6. **Type:** App component regression.
- **Preconditions:** Existing browser session; open `/login`, where Sign out remains available. Two deferred login requests allow deterministic response timing.
- **Steps:** Submit twice; sign out before either completes; complete both successfully; inspect storage, page and protected API calls; deliberately submit a new login.
- **Expected:** Both pre-logout responses are ignored, including the latest pending request. No token is restored, Login remains visible and protected data is not fetched. A deliberate post-logout login still establishes a fresh session and opens the unchanged role home.
- **Automated:** APP `ignores overlapping login responses after sign-out and allows deliberate sign-in again`.
- **Execution:** Pass (20 Oct 2026 focused frontend run).

**TC-75-08 — Superseded responses cannot overwrite current authentication**
- **Traces to:** AC6. **Type:** App component regression, both response orders.
- **Preconditions:** Signed out at `/login`; two deferred successful login requests with distinct tokens and destinations.
- **Steps:** Submit twice; resolve the older request before or after the latest request; inspect token and destination; sign out normally.
- **Expected:** Only the latest submitted request may authenticate. An earlier response cannot authenticate while the latest is pending or overwrite its token/destination afterwards. Normal sign-out still clears authentication. This also closes the audited sequence (two submissions, successful authentication, sign-out, delayed response): the first submission is superseded immediately, and logout invalidates any outstanding response.
- **Automated:** APP `ignores a superseded login response arriving %s the latest response` (`before`, `after`). Existing TC-75-06 retains normal sign-out/Back/re-login coverage.
- **Execution:** Pass, both response orders (20 Oct 2026 focused frontend run).

| AC | Cases |
|---|---|
| AC1 | TC-75-01 |
| AC2 | TC-75-02 |
| AC3 | TC-75-03 |
| AC4 | TC-75-02,03,04,05 |
| AC5 | TC-75-05 |
| AC6 | TC-75-06,07,08 |

## Execution record

Executed 19 Oct 2026 (Singapore). Commands below run from the indicated directory; `git diff --check` runs from the repository root.

| Directory | Exact command | Actual result |
|---|---|---|
| backend | `./.venv/Scripts/python.exe -B -m unittest -v tests.test_auth_unit` | First attempt: 5 setup errors from mocking the SQLAlchemy descriptor without an app context; corrected test fixture. Red run: 5 methods, 2 passed; credential-message, missing-fields and role tests failed as expected (2 failed subtests, 4 error subtests). |
| frontend | `npm test -- src/pages/LoginPage.test.jsx src/App.test.jsx src/api/client.test.js` | Not Run: PowerShell blocked npm.ps1. Used npm.cmd. |
| frontend | `npm.cmd test -- src/pages/LoginPage.test.jsx src/App.test.jsx src/api/client.test.js` | First attempt: startup failed because sandbox prevented esbuild from resolving the project path. Outside sandbox, red run exposed role-landing, missing-field, route-guard and sign-out gaps; no passing-suite claim. After implementation: **32 passed, 0 failed, 0 skipped**, 3 files, 22.45 seconds. |
| backend | `./.venv/Scripts/python.exe -B -m unittest -v tests.test_auth_unit tests.test_authorization_unit tests.test_authorization_http_unit` | **29 passed, 0 failed, 0 skipped**, 0.524 seconds. Includes 5 focused auth tests and 24 unchanged SCRUM-27 authorization regressions; no database/network access. Existing datetime.utcnow deprecation warnings only. |
| frontend | `npm.cmd test` | First full regression: **320 passed, 6 failed, 0 skipped**, 27 files, 94.70 seconds. All failures were SCRUM-55 App fixtures lacking a browser token after the shared guard was added; fixture corrected without changing assertions. Final rerun: **326 passed, 0 failed, 0 skipped**, all 27 files, 90.69 seconds. |
| frontend | `npm.cmd test -- src/pages/ReviewRequestsPage.test.jsx src/App.test.jsx` | After fixture correction: **12 passed, 0 failed, 0 skipped**, 2 files, 3.53 seconds. Includes strengthened protected-history Back case. |
| frontend | `npm.cmd run build` | **Pass**, 123 modules transformed, production bundle built in 1.08 seconds. |
| repository | `git diff --check` | **Pass**, no whitespace errors. |

**Local PostgreSQL integration: Pass.** Initially no local listener was available; the user then started the existing Docker container. Read-only verification found `trueadams-test-pg`, bound only at `127.0.0.1:5433` (container port 5432), existing database `postgres`, ten existing application tables and login role `connectsphere_test`. Its existing credential from the repository CI configuration authenticated successfully; `rolsuper` was false. No rebuild, reset, schema changes or credential changes were needed.

For each integration run, `TEST_DATABASE_URL` was overridden only in the command process with this verified local target and existing restricted-role credential. Neither `.env` nor any remote configuration was changed. The exact command bodies below additionally assert the effective TestConfig target before loading tests; the preceding environment assignment's credential is omitted from this document.

Focused SCRUM-75 integration command (from `backend/`):

```powershell
@'
import unittest
from sqlalchemy.engine import make_url
from app.config import TestConfig
url=make_url(TestConfig.SQLALCHEMY_DATABASE_URI)
assert (url.host,url.port,url.database,url.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'Refusing non-local test configuration'
print('Effective TestConfig verified: 127.0.0.1:5433/postgres as connectsphere_test',flush=True)
unittest.main(module=None, argv=['unittest','-v','tests.test_auth'])
'@ | ./.venv/Scripts/python.exe -B -
```

**Actual result:** 5 passed, 0 failed, 0 skipped; 0.689 seconds. This executes all AUTH references in TC-75-01..05, including usable JWT/role restrictions, exact invalid-credential message, missing-field names, no failure token/cookie and retryable lookup failure.

Reasonable SCRUM-27 authorization regression command (from `backend/`):

```powershell
@'
import unittest
from sqlalchemy.engine import make_url
from app.config import TestConfig
url=make_url(TestConfig.SQLALCHEMY_DATABASE_URI)
assert (url.host,url.port,url.database,url.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'Refusing non-local test configuration'
print('Effective TestConfig verified: 127.0.0.1:5433/postgres as connectsphere_test',flush=True)
unittest.main(module=None, argv=['unittest','-v','tests.test_authorization'])
'@ | ./.venv/Scripts/python.exe -B -
```

**Actual result:** 11 passed, 0 failed, 0 skipped; 0.543 seconds. Existing role changes, event ownership boundaries, reassignment and private-data refusals remain passing. These database-dependent tests used only the existing local PostgreSQL and AppTestCase's rolled-back transactions. Existing datetime.utcnow deprecation and short test JWT-key warnings were reported; no test failed.

Supabase and other remote databases were **not accessed**. The remote `.env` values were inspected locally with credentials redacted, then overridden for integration runs before TestConfig import. No test app/engine connected to them. Earlier isolated HTTP tests block Engine connection methods and socket connections. No database/schema, CI, infrastructure, stored configuration or credential changes were made. The full backend suite was not run because focused authentication and existing authorization suites supply the relevant regression evidence. No manual browser/end-to-end test was run; automated passes refer to the specified test levels.

### Focused AC6 race correction — 20 Oct 2026

The audit reproduced overlapping successful login responses restoring a token after logout or replacing a newer session. `LoginPage` previously applied every successful response unconditionally. The correction adds one request counter in the existing App: each submission and sign-out advances it. Login success/error handlers ignore responses whose captured counter is no longer current. Logout invalidates pending requests synchronously, including when the user signs out while already on `/login`; deliberate later login gets a fresh counter. Role destinations, API client, token storage key, backend authentication and JWT behavior are unchanged. TC-75-07/08 cover the race; TC-75-06 and existing login/client tests retain ordinary-flow coverage.

| Directory | Exact command | Actual result |
|---|---|---|
| frontend | `npm.cmd test -- src/App.test.jsx` | Before correction: **6 passed, 3 failed, 0 skipped**, 4.23 seconds. New regressions exposed post-logout token restoration and superseded responses authenticating/overwriting the current token. |
| frontend | `npm.cmd test -- src/pages/LoginPage.test.jsx src/App.test.jsx src/api/client.test.js src/pages/ReviewRequestsPage.test.jsx` | After correction: **41 passed, 0 failed, 0 skipped**, all 4 files, 23.74 seconds. Includes all three race cases, deliberate re-login, normal login/logout/Back, role landing, retry/failure behavior, bearer-header handling and unchanged SCRUM-55 assertions. |
| frontend | `npm.cmd run build` | **Pass**, 123 modules transformed, 837 milliseconds. |
| repository | `git diff --check` | **Pass**, no whitespace errors. |

All API responses in these tests were mocked. No database-dependent backend tests or database connections were needed or performed for this frontend-only correction. The earlier 19 Oct integration evidence above is historical and was not rerun. The copied-JWT limitation A2/Q2 is unchanged; this correction addresses stale browser callbacks without adding server revocation, dependencies, pages or session infrastructure. No unrelated SCRUM logic was changed.

## Regression impact

SCRUM-27 `test_auth.py` adds response-role, exact-message, missing-field and no-cookie assertions. LoginPage tests use the required text and strengthen empty-field feedback; existing failure-session preservation remains. Credential verification, token identity, authorization and other stories' business logic are unchanged. Shared App routes gain a sign-in guard and sign-out control; existing pages and navigation destinations remain. No schema, CI, dependency or infrastructure changes.


### Implementation status

| AC | Status | Evidence / limitation |
|---|---|---|
| AC1 | Pass | TC-75-01; persisted local login and usable JWT pass; existing role homes plus Q1 fallback pass in components. |
| AC2 | Pass | TC-75-02; exact shared error and real hash verification pass against local PostgreSQL and mocked lookup. |
| AC3 | Pass | TC-75-03; named missing fields in API/form. |
| AC4 | Pass | TC-75-02/03/04/05; no issuer calls/cookies or new browser token on failure. |
| AC5 | Pass | TC-75-05; existing 503/rollback/retry reused. |
| AC6 | Partial pending interpretation Q2 | TC-75-06/07/08 pass for the active browser session, including the corrected delayed-response race; copied-token server invalidation is not implemented. |

### Cross-story test adjustment

`frontend/src/pages/ReviewRequestsPage.test.jsx` (SCRUM-55 TC-55-06/07/08/15) now supplies a session token in `renderPage` before mounting App. Affected tests: `displays the summary fields and opens the selected request for review`, `shows the empty review-list message`, `shows a %s refusal without exposing request data` (401/403), and `explains a %s failure and recovers after Retry` (server/network). All six retain their original assertions. The 401 case now represents a stored stale token rejected by the API; signed-out direct navigation is separately covered by TC-75-06. Underlying review and authorization behavior is unchanged. This fixture update is necessary because SCRUM-75 adds the shared frontend sign-in prerequisite.
