# SCRUM-80 — Lead sees events waiting for a coordinator

**User Story** : As an Event Coordinator Lead, I want to see submitted event requests that have no coordinator, so that I know which events need one.

**Executed:** 20 Oct 2026; frontend race correction rechecked 21 Oct 2026 · **Final status:** Pass · **Related:** [SCRUM-81 queue cases](SCRUM-81-unassigned-queue.md), [SCRUM-81 assignment cases](SCRUM-81-lead-assigns-coordinator.md).

**Implementation reused:** `GET /api/events/queue`, `list_queue`, `_waiting_for_assignment`, `_queue_event_payload` and the stored-user Lead check in [routes.py](../../backend/app/events/routes.py) / [permissions.py](../../backend/app/events/permissions.py); [UnassignedQueuePage.jsx](../../frontend/src/pages/UnassignedQueuePage.jsx), its existing API client/error/date helpers, and the `/events/queue` route/navigation in [App.jsx](../../frontend/src/App.jsx).

## Acceptance criteria

Original Jira wording, in the supplied order:

| ID | Criterion |
|----|-----------|
| AC1 | The Lead sees a queue of submitted requests with no assigned coordinator, oldest first, showing event name, organiser, proposed date and submission time. |
| AC2 | When no request is waiting, the page says so instead of showing an empty list. |
| AC3 | Only the Lead can open the queue. Anyone else is denied and sees no event data. |
| AC4 | If the queue cannot be loaded, the user is told and no partial list is shown. |
| AC5 | More than one Lead can use the queue, and every Lead sees all unassigned requests. |

## Acceptance criteria audit

| AC | Before correction | Evidence and outcome | Final |
|----|-------------------|----------------------|-------|
| AC1 | Satisfied | Shared query selects `submitted` with `coordinator_id IS NULL`; sorts by submission ascending, unknown times last, then event ID. Payload and page display all four required details. | Satisfied |
| AC2 | Satisfied | API returns an empty array with a sentence; page displays the sentence without a list. | Satisfied |
| AC3 | Partial | API already returns 401/403 without event data and reloads the stored role. The latest request's denial clears queue data; stale successful responses cannot override it. | Satisfied |
| AC4 | Partial | Initial failure/retry already worked with `explain` and `canRetry`. A request counter now ignores stale successes and failures; latest success clears errors, and latest failure clears queue data. | Satisfied |
| AC5 | Satisfied | Query has no Lead ownership filter. Existing TC-81-25 loads the same fixture queue for both lena and liam. | Satisfied |

## Working assumptions

No new business assumptions were introduced. The authoritative SCRUM-80 ACs settle SCRUM-81's Q6 (submitted and unassigned), Q7 (one shared queue), Q8 (required details) and Q9 (oldest submission first) for this story. Existing display conventions remain: organiser email identifies the organiser; proposed dates remain Singapore time as recorded; UTC submission times display in local time; unknown values show "Not recorded", with unknown submission times last.

## Seed data (UQ-SEED, reused)

Reuse [SCRUM-81 UQ-SEED](SCRUM-81-unassigned-queue.md#seed-data-uq-seed), `backend/tests/test_unassigned_queue.py` and `backend/tests/seed_data.py`. W2, W1, W3, W4 wait in that order; H1 has a coordinator; U1/D1/C1/R1 have other statuses. Organisers dana/evan and Leads lena/liam demonstrate cross-organiser, shared visibility. Other seeded roles demonstrate denial. Existing backend fixtures use unique emails and rollback each test's transaction. Frontend tests mock the existing API contract; no live frontend API calls occur.

## Test cases

Backend references below are in [test_unassigned_queue.py](../../backend/tests/test_unassigned_queue.py); frontend references are in [UnassignedQueuePage.test.jsx](../../frontend/src/pages/UnassignedQueuePage.test.jsx). Except TC-80-06, all automation is reused from SCRUM-81 without modification.

### AC1 — Waiting requests and details

**TC-80-01 · Filter, order and display the waiting queue**
- **Traces to:** AC1 · **Type:** Happy path / boundary · **Status:** Pass
- **Preconditions:** UQ-SEED, authenticated lena.
- **Steps:** GET the queue; inspect fixture membership, order and payload; render the page with that contract.
- **Expected result:** W2, W1, W3, W4 only among fixture rows; required details displayed, proposed date unchanged by time zone, missing values labelled "Not recorded". Existing assignment links remain intact.
- **Automated (reused):** `QueueListTests.test_lead_sees_each_waiting_event_with_basic_information`, `test_only_events_waiting_for_a_coordinator_are_listed`, `test_oldest_submission_is_listed_first`, `test_missing_values_are_null` (TC-81-25–28); frontend `lists each waiting event with its basic information`, `keeps the order received and links each name to its assignment page`, `shows missing values as Not recorded` (TC-81-35/36).

### AC2 — Empty state

**TC-80-02 · Explain that no requests are waiting**
- **Traces to:** AC2 · **Type:** Empty state · **Status:** Pass
- **Preconditions:** No waiting requests within the backend test transaction; frontend receives `events: []` with a message.
- **Steps:** Load the API and render the empty response.
- **Expected result:** HTTP 200, empty events and a meaningful message; page shows the message without a list.
- **Automated (reused):** `EmptyAndFailureTests.test_empty_queue_gets_a_message` (TC-81-32); frontend `shows the server's message when the queue is empty` (TC-81-37).

### AC3 — Access protection

**TC-80-03 · Deny non-Leads without event data**
- **Traces to:** AC3 · **Type:** Negative / authorisation · **Status:** Pass
- **Preconditions:** UQ-SEED; non-Lead roles; absent/expired/deleted-user sessions; a Lead whose stored role changes after token issuance.
- **Steps:** GET the queue directly for each session/role; render a 403 response.
- **Expected result:** Invalid sessions receive 401; non-Leads receive 403 with no events or titles. UI shows the denial, no list and no Retry. The existing sign-in route wrapper protects signed-out navigation.
- **Automated (reused):** `AccessTests.test_only_leads_can_view_the_queue`, `test_a_valid_session_and_the_lead_role_are_required` (TC-81-30/31); frontend `denies anyone else without showing events or a retry` (TC-81-37). [App.test.jsx](../../frontend/src/App.test.jsx) provides existing sign-in/navigation regression coverage; queue route protection was also inspected in App.jsx.
- **Additional overlap coverage:** TC-80-06, 403 variant.

### AC4 — Failed loading

**TC-80-04 · Report load failures without a partial list and allow retry**
- **Traces to:** AC4 · **Type:** Negative / recovery · **Status:** Pass
- **Preconditions:** Backend query raises `SQLAlchemyError`; frontend receives 503 with `retryable: true`, or a network failure.
- **Steps:** Load during failure; restore service and retry.
- **Expected result:** Backend rolls back and returns 503 with a useful error, no events or titles. UI shows the backend error or network fallback, no list and a Retry button; retry can load the queue.
- **Automated (reused):** `EmptyAndFailureTests.test_load_failure_is_reported_without_a_list_and_retry_works` (TC-81-33); frontend `tells the Lead when the queue cannot be loaded, and retries`, `shows a fallback message when the server cannot be reached` (TC-81-37).

**TC-80-06 · Only the latest overlapping load may update the queue or error**
- **Traces to:** AC3, AC4 · **Type:** Negative / regression · **Status:** Pass (21 Oct 2026)
- **Preconditions:** Render under React Strict Mode, as main.jsx does; two initial queue requests overlap.
- **Steps:** Pair one successful response with one failure (503 or 403). Make the latest request succeed or fail, and complete the requests in both orders (older first / newer first). Check intermediate state and state after both complete.
- **Expected result:** An older response never changes state, even while the latest request is pending. Latest success displays the queue without an error or Retry; latest failure displays only its error, with no event list or organiser details. Retry is offered for retryable 503 only. These outcomes hold for both success-then-failure and failure-then-success completion sequences.
- **Automated (updated, eight parameter variants):** frontend `keeps the latest $latest with $status when overlapping loads finish $order` in `UnassignedQueuePage.test.jsx`. Matrix: 503/403 × latest success/failure × older/newer first.
- **Correction:** A minimal `useRef` request counter guards both success and failure handlers. Only the latest success stores results and clears errors; only the latest failure clears results and stores its error. Existing loading and retry behavior is retained. The prior two overlap variants were replaced because they expected an older request to populate the queue before the latest request completed; that expectation contradicts the latest-request rule. Existing SCRUM-81 cases remain unchanged.

### AC5 — Shared visibility

**TC-80-05 · Both Leads see all waiting fixture requests**
- **Traces to:** AC5 · **Type:** Happy path / multiple users · **Status:** Pass
- **Preconditions:** UQ-SEED; lena and liam are distinct Leads; waiting events belong to dana and evan.
- **Steps:** GET the queue with each Lead's token.
- **Expected result:** Both receive HTTP 200 and all W1–W4 requests, independent of Lead ownership. Query inspection confirms no per-Lead filter.
- **Automated (reused):** `QueueListTests.test_lead_sees_each_waiting_event_with_basic_information` (TC-81-25 already asserts both Leads; no duplicate test added).

## Traceability matrix

| AC | SCRUM-80 cases | Reused SCRUM-81 cases | Final execution |
|----|----------------|----------------------|-----------------|
| AC1 | TC-80-01 | TC-81-25–28, 35/36 | Pass |
| AC2 | TC-80-02 | TC-81-32, 37 | Pass |
| AC3 | TC-80-03, 06 | TC-81-30/31, 37 | Pass |
| AC4 | TC-80-04, 06 | TC-81-33, 37 | Pass |
| AC5 | TC-80-05 | TC-81-25 | Pass |

## Execution commands and actual results

### 21 Oct 2026 — Focused frontend race correction

From `frontend/`:

```powershell
npm.cmd test -- src/pages/UnassignedQueuePage.test.jsx src/App.test.jsx
```

**Actual:** 2 files passed; **24 passed, 0 failed, 0 skipped**, exit 0. Queue: 15 tests (eight updated overlap variants plus seven existing loading/detail/order/empty/denial/retry/network cases). App: nine existing sign-in/navigation regression tests. All API responses are mocked. No separate RED → GREEN phase was run for this correction. No backend tests, database commands or Supabase access occurred in this follow-up.

### 20 Oct 2026 — Original audit and correction (historical results)

Executed on Windows PowerShell on 20 Oct 2026. `npm.cmd` avoids this machine's disabled PowerShell script execution policy. Vitest required execution outside the filesystem sandbox because esbuild could not resolve the project path inside it. Neither startup failure executed tests.

**Local database preparation:** `docker ps` showed no running containers; `docker ps -a` identified the existing stopped `trueadams-test-pg` (`postgres:17`). `docker inspect trueadams-test-pg --format '{{json .HostConfig.PortBindings}}'` confirmed PostgreSQL is exposed only on `127.0.0.1:5433`. `docker start trueadams-test-pg` reused it without schema changes, rebuild or reset. The configured `.env` test target was identified as remote without connecting; it was overridden only in the Python process. Neither environment files nor CI were changed.

**Backend**, from `backend/` (the local-only credential below is the existing public CI test credential):

```powershell
@'
import os
import unittest
os.environ['DOTENV_DISABLED'] = '1'
os.environ['TEST_DATABASE_URL'] = 'postgresql://connectsphere_test:ci-only@127.0.0.1:5433/postgres'
os.environ['DATABASE_URL'] = os.environ['TEST_DATABASE_URL']
from app.config import Config, TestConfig
from sqlalchemy.engine import make_url
for config in (Config, TestConfig):
    url = make_url(config.SQLALCHEMY_DATABASE_URI)
    assert url.drivername == 'postgresql' and url.host == '127.0.0.1' and url.port == 5433
    assert url.database == 'postgres' and url.username == 'connectsphere_test' and not url.query
print('Verified local-only Config and TestConfig: connectsphere_test@127.0.0.1:5433/postgres', flush=True)
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_unassigned_queue')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | .venv/Scripts/python.exe -
```

**Actual:** 11 passed, 0 failed, 0 skipped, exit 0. All 11 are existing SCRUM-81 tests, including submission/assignment queue integration. Before tests, a separate read-only connection check also confirmed effective TestConfig at `127.0.0.1:5433/postgres`, database `postgres` and role `connectsphere_test`. No remote database connections or Supabase access occurred. Existing short JWT test-key warnings appeared; tests passed.

**Frontend red**, from `frontend/`, after adding the regression and before the production correction:

```powershell
npm.cmd test -- src/pages/UnassignedQueuePage.test.jsx
```

**Actual:** 7 passed, 2 failed, 0 skipped, exit 1. Both new 503/403 cases failed because the event list remained visible. This confirms the added test detects the defect.

**Frontend final**, from `frontend/`:

```powershell
npm.cmd test -- src/pages/UnassignedQueuePage.test.jsx src/App.test.jsx src/pages/AssignCoordinatorPage.test.jsx
```

**Actual:** 3 files passed; 29 passed, 0 failed, 0 skipped, exit 0. Queue: 9 (7 existing, 2 new); App sign-in/navigation: 9 existing; SCRUM-81 assignment page: 11 existing. No existing tests were adjusted; only the focused overlapping-load regression was added. No full backend suite was run.

## Scope and outstanding issues

Only the queue's request handling, its regression test and this Markdown document changed. The existing endpoint, filtering, authorization, page, shared utilities and assignment links are reused. Assignment/reassignment, submission, supervision, event decisions, notifications, authentication infrastructure, schema, dependencies, SCRUM-81 documentation and CI are unchanged. No commit, push or PR was created. No unmet acceptance criteria or execution blockers remain; no optional enhancements were implemented.

## Open questions for the customer

None blocking these five supplied Jira criteria. Existing SCRUM-81 questions outside queue viewing remain with that story; this work does not resolve assignment policy.
