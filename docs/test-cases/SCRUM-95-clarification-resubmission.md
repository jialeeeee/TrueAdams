# SCRUM-95 — Organiser Replies to a Clarification and Resubmits: Test Cases

**User story:** As an Event Organiser, I want to reply to a clarification question and resubmit my request, so that the coordinator can continue the review.

**Created:** 30 Oct 2026 · **Phase:** scoped GREEN authorized and completed on 30 Oct 2026. The scout and RED results below are retained as historical evidence; see GREEN verification for current results.

**Requirements source:** original Jira wording pasted by the user; no Jira URL supplied.
**Related:** [SCRUM-31](SCRUM-31-event-clarification.md), [SCRUM-55](SCRUM-55-review-submitted-event-request.md), [SCRUM-29](SCRUM-29-draft-event-request.md), [SCRUM-53](SCRUM-53-update-event-planning-info.md), [SCRUM-52](SCRUM-52-escalate-restricted-field-changes.md).
**Automation:** [backend](../../backend/tests/test_clarification_resubmission.py), [existing clarification page component](../../frontend/src/pages/ClarificationPage.resubmission.test.jsx).

## Acceptance criteria

The five criteria below preserve the original Jira wording, including grammar and punctuation.

| ID | Criterion |
|---|---|
| AC1 | I see the clarification messages on my own request, and I cannot see them on anyone’s else |
| AC2 | I can reply with a message that is not blank and not over 1,000 words. |
| AC3 | I can edit the request's details before resubmitting. |
| AC4 | Resubmitting returns the request to Submitted and notifies the coordinator. |
| AC5 | If saving fails, my entries are kept and an error is shown. |

## Focused read-only scout

The scout inspected relevant source, tests and test-case documents only. No files were modified and no database was accessed during that phase.

| Investigation | Existing behavior and smallest reuse |
|---|---|
| 1. Where questions are recorded | `EventClarification` in `backend/app/models.py`: `event_id`, `sender_id`, `message` (Text), `created_at`. Coordinator POST `/api/events/<id>/clarifications` adds it with a `Notification` in one commit. |
| 2. Owner-only retrieval | GET the same URL uses `_current_user()` and `can_view_clarifications()` from `events/permissions.py`. It permits the current coordinator or the current organiser, checks ownership before reading messages, and filters by event ID. AC1 backend behavior already exists. |
| 3. Reply persistence | Existing columns can hold an organiser-authored message with the same event ID and their sender ID. No database constraint restricts senders to coordinators. A chronological event thread is sufficient under A1; no reply table, parent-message ID, discriminator or migration is needed. The current POST is intentionally coordinator-only. |
| 4. Organiser editing | `DraftEventPage.jsx` edits request fields only while Draft; `_own_draft()` refuses submitted requests. `PATCH /api/events/<id>` is coordinator-only, despite AGENTS.md's introductory wording about organiser edits. Its `NORMAL_FIELD_VALIDATORS` already validate title, purpose, description, accessibility needs and three venue-characteristic lists. There is no submitted-request organiser editor to call unchanged. A2 proposes reusing these validators and existing form conventions inside the clarification page; the tests exercise description only. |
| 5. Status representation | `SUBMITTED_STATUS = "submitted"`; `UNDER_REVIEW_STATUS = "under_review"`. Jira's Submitted maps to existing `submitted`; no new status is needed. |
| 6. Effect of clarification | Sending a question changes neither status nor assignment. Questions are permitted in `submitted` and `under_review`. A1 uses an assigned request with an existing question, initially under review. SCRUM-31 A16 says a started review cannot be undone; SCRUM-95 AC4 introduces a specific reply/resubmission return to Submitted, requiring a narrow exception later, not a general undo action. SCRUM-31 files remain untouched. |
| 7. Coordinator notification/review | Reuse `Notification(recipient_id=event.coordinator_id, event_id=event.id, ...)`, the existing Celery `send_notification_email.delay` task and post-commit queue convention. SCRUM-55's review queue already includes submitted/under_review, and POST `/api/events/<id>/review` already starts review for the assigned coordinator. Preserve that assignment. |
| 8. Failed-save entries | `ClarificationPage.jsx` already keeps an unsuccessful coordinator question in React state and shows the backend error. `DraftEventPage.jsx` likewise retains failed edits. The organiser reply and edited fields need the same behavior, with no success indication on failure. No retry infrastructure is necessary. |

### Existing coverage and gaps

- `test_event_clarifications.py` covers owner/coordinator history and unrelated-viewer denial, coordinator questions, validation and notifications. SCRUM-95 adds one isolated owner-specific history check and expects it to pass.
- `test_review_requests_unit.py` checks assigned open requests and event-specific history; `test_event_review_start.py` checks starting a review. SCRUM-95 reuses the actual review action after resubmission rather than inventing another process.
- `test_update_event_planning_info.py` explicitly expects organiser planning PATCH requests to be denied. No change to that endpoint or its tests is proposed.
- `ClarificationPage.test.jsx` covers coordinator questions; `DraftEventPage.test.jsx` covers the draft editor. Neither covers an organiser reply/resubmit form. The new component tests render the existing `ClarificationPage`; no new page or test infrastructure is introduced.

## Working assumptions

These are provisional implementation choices for RED, not agreed customer requirements or additional acceptance criteria.

- **A1 / Q1 — One event-thread reply and resubmission:** send a reply and optional edits together through POST `/api/events/<id>/resubmit`. Reuse `EventClarification` with the organiser as sender; no separate reply-draft save or per-question linking. Use the existing clarification context (assigned request, question already recorded, status submitted/under_review), then return to `submitted` without changing coordinator. GREEN interprets pending as the latest chronological message having a sender other than the organiser; an organiser reply closes the exception until another question. The assigned user's current role must still be coordinator. No general review-undo action is introduced.
- **A2 / Q2 — Minimum editing surface:** reuse the `NORMAL_FIELD_VALIDATORS` field set and its validation rules for optional resubmission edits. Restricted edits are refused in this action; pending requests cannot use SCRUM-46's approved-event change-request flow. Leave coordinator PATCH and draft endpoints unchanged. Add organiser controls to the existing clarification page, with current editable values and a `can_resubmit` capability supplied by the owner-authorized history response. Tests need only description to demonstrate AC3; they do not require an editing redesign or expand editable fields.
- **A3 / Q3 — Reuse message/notification conventions:** trim surrounding whitespace and count words using Python `split()` / JavaScript whitespace splitting, allowing 1–1,000. Save the reply, normal edits, `submitted` status and assigned coordinator's in-app notification in one transaction. Queue the existing email only after commit; no new channel. Reuse the repository's nonfatal email queue-failure convention; no additional queue-outage scenario is introduced.

## Additive contract implemented in GREEN

The original RED proposal is now implemented; coordinator question sending, draft editing and planning PATCH permissions remain unchanged.

- GET `/api/events/<id>/clarifications` keeps its existing thread, ownership rules and SCRUM-31 `event` summary (`id`, `title`, `status`, `organiser`). For the eligible owner, add `can_resubmit: true` and the current permitted values in separate top-level `editable_fields` metadata (empty otherwise). Retain coordinator `can_send` behavior.
- POST `/api/events/<id>/resubmit`, authenticated as the current organiser, body `{"message": "...", "changes": {"description": "..."}}`; `changes` may be empty. Reuse stored-role/ownership checks and field validators. Do not relax the existing coordinator-question POST.
- Success: **200** `{"message": "<confirmation>", "request": {"id", "status": "submitted", "description", ...}, "notification": {"in_app": true, "email_queued": true}}`. The `request` uses the existing request payload conventions. The reply becomes visible through existing history serialization to the owner and assigned coordinator. No new notification kind is prescribed by tests.
- Blank/whitespace-only or over-1,000-word reply: **400** with a nonblank `error`, no writes or email.
- After basic input/ownership checks, an ineligible request returns the existing **409** not-awaiting-clarification error before edit validation. Restricted edits on an eligible request return **422**, explain the permitted fields and ask the organiser to remove the other changes; no `requires_review` link to SCRUM-46 is offered.
- Save failure: **503** `{"error": "<actionable explanation>", "retryable": true}`; roll back the transaction, queue no email and return no successful request/notification receipt. The UI retains both inputs and offers resubmission again.

## Seed data (CR95-SEED)

These are transient ORM objects and mocked API responses, recreated per test. They are never inserted into a database. The backend uses bare Flask/JWT setup rather than `AppTestCase`, whose setup would open Supabase. This follows the repository's existing isolated HTTP unit-test pattern and the user's database-free RED instruction.

| ID | Fixture |
|---|---|
| O1 / O3 | Organisers 1 and 3, distinct `@test.invalid` addresses. |
| C2 | Coordinator 2, currently assigned to both fixture requests. |
| E7 | O1's Charity Gala, under_review, coordinator C2, original description, recorded review start. |
| E8 | O3's private request, under_review, coordinator C2. |
| M20 / M21 | Distinct coordinator questions for E7 / E8. |
| Reply / edit | A nonblank accessible-entrance reply and updated description. Boundary reply contains exactly 1,000 whitespace-separated words and exceeds 1,000 characters. |

## Test cases

### TC-95-01 — Clarification visibility

**Traces to:** AC1 · **Type:** isolated HTTP unit and component.

**Preconditions:** CR95-SEED; owner O1 signed in.

**Steps:** GET E7's clarification history; then GET E8's history with the same owner token. Open E7's existing clarification page in the component flow.

**Expected result:** E7 returns only its question. E8 returns 403 with an error and no question, private event title or other organiser email. The history query is filtered by event ID. The component displays E7's question. Existing backend behavior may pass during RED.

**Automated:** `ClarificationResubmissionTests.test_owner_reads_only_own_questions_and_foreign_access_exposes_nothing`; component `shows the question and resubmits a reply with a permitted description edit` (shared with TC-95-03/04).

### TC-95-02 — Reply validation and persistence

**Traces to:** AC2 · **Type:** isolated HTTP unit and component.

**Preconditions:** E7 has a question; O1 is its organiser.

**Steps:** Try empty, whitespace-only and 1,001-word replies. Then submit exactly 1,000 words, separated by spaces/newlines and surrounded by whitespace. In the component, enter the corresponding invalid values, then a valid boundary reply.

**Expected result:** Invalid replies cannot be saved; backend returns 400 and adds/commits nothing. A valid boundary reply is accepted and added as `EventClarification(event_id=7, sender_id=1, message=<trimmed reply>)` with one commit. The UI blocks blank/over-limit submissions and enables the valid boundary reply. The limit is words, not characters.

**Automated:** `ClarificationResubmissionTests.test_reply_refuses_blank_and_over_limit_but_saves_exactly_1000_words`; component `blocks blank and over-limit replies and retains both entries after a save error` (shared with TC-95-05).

### TC-95-03 — Edit before resubmission

**Traces to:** AC3 · **Type:** isolated HTTP unit and component; shares TC-95-04's success flow.

**Preconditions:** E7's existing description is loaded into the clarification form under A2.

**Steps:** Change Description to the fixture edit, enter the reply and resubmit.

**Expected result:** The UI sends the changed description with the reply; the backend saves it using the existing normal-field rules. The returned request contains the updated description. No separate organiser planning PATCH permission is assumed or granted.

**Automated:** `ClarificationResubmissionTests.test_resubmit_keeps_reply_and_permitted_edit_notifies_and_review_can_continue`; component `shows the question and resubmits a reply with a permitted description edit`.

### TC-95-04 — Resubmit and notify the existing coordinator

**Traces to:** AC4 · **Type:** isolated HTTP unit and component; shares TC-95-03's success flow.

**Preconditions:** E7 is under_review and assigned to C2; O1 has a valid reply and permitted edit.

**Steps:** Resubmit; inspect added ORM rows and the single commit boundary; read history as C2; use the existing POST `/api/events/7/review` action.

**Expected result:** The request becomes `submitted`; description and reply are retained; the notification is addressed to C2 for E7 in the same attempted transaction. Coordinator ID stays 2. The existing email task is invoked for C2 after commit. History includes the organiser's reply; the existing review action accepts the resubmitted request and returns `under_review`. The component shows the successful resubmission and Submitted status.

**Automated:** `ClarificationResubmissionTests.test_resubmit_keeps_reply_and_permitted_edit_notifies_and_review_can_continue`; component `shows the question and resubmits a reply with a permitted description edit`.

### TC-95-05 — Failed save retains entries

**Traces to:** AC5 · **Type:** isolated HTTP unit and component.

**Preconditions:** E7; nonblank reply and changed description. Backend commit raises `SQLAlchemyError`; component API mock rejects with a retryable 503.

**Steps:** Attempt resubmission; inspect failure handling and the form after rejection.

**Expected result:** Backend returns 503 with a nonblank actionable error and `retryable: true`, no success receipt or private exception detail, one commit attempt followed by rollback, and no email. Reply and notification were staged for the same transaction. The component displays the backend explanation, retains reply and description, keeps the original status, shows no success notice, and allows retry. Unit mocks verify transaction boundaries/rollback intent; they do not prove actual database atomicity or persisted row recovery.

**Automated:** `ClarificationResubmissionTests.test_save_failure_rolls_back_reply_edits_status_and_notification_without_email`; component `blocks blank and over-limit replies and retains both entries after a save error`.

## Traceability matrix

| Criterion | Test cases | Backend methods | Component scenarios |
|---|---|---|---|
| AC1 | TC-95-01 | Owner history and foreign denial | Successful flow: question visible |
| AC2 | TC-95-02 | Reply validation, exact boundary and ORM message | Validation and failed-save flow |
| AC3 | TC-95-03 | Combined edit/resubmit/notification/review | Successful flow: description edit |
| AC4 | TC-95-04 | Same combined success method | Successful flow: submitted receipt/status |
| AC5 | TC-95-05 | Failed commit/rollback/no email | Validation and failed-save flow: inputs retained |

RED used four backend methods and two component scenarios for five cases. GREEN retains them, adds one focused guard method for the owner/pending-only editing exception and one loopback-only persistence method for the transaction gap. The persistence test was skipped during initial GREEN verification for local schema incompatibility; it subsequently ran and passed on the fresh local database during the focused regression verification recorded below. The existing request-list link expectation was updated only because SCRUM-95 adds clarification navigation; its no-draft-editor assertion remains intact.

## RED execution evidence

Executed on 30 Oct 2026 using the existing backend Python 3.12 virtual environment and Vitest 2.1.9. Only the new SCRUM-95 test files were selected; no full suite was run.

Exact commands, each from the indicated working directory:

```powershell
# backend/
.\.venv\Scripts\python.exe -m unittest -v tests.test_clarification_resubmission

# frontend/
npm.cmd test -- src/pages/ClarificationPage.resubmission.test.jsx
```

| Focused run | Passed | Failed methods/scenarios | Skipped | Errors | Observed reason |
|---|---:|---:|---:|---:|---|
| Backend, corrected test file | 1 | 3 | 0 | 0 | Owner history passes. The proposed resubmit URL returns 404 for reply validation, edit/resubmit and failed-save cases. |
| Frontend, elevated retry after sandbox startup failure | 0 | 2 | 0 | 0 | Questions load, but the existing page has only Your question / Send question; both scenarios fail at the missing Your reply textbox. |

Backend runner output: `Ran 4 tests in 0.080s`, `FAILED (failures=6)`. This is **three failing methods**, with six failure records: empty reply, whitespace-only reply, 1,001 words, accepted 1,000-word boundary, combined success flow, and failed-save flow. The first three are subtests; the valid-boundary assertion is in their parent method. They all fail on the absent endpoint, not imports or persistence mocks. The successful owner-history test exercises real ownership/filtering behavior.

Frontend runner output: `Test Files 1 failed (1)`, `Tests 2 failed (2)`. The first completed execution took 26.46s, component execution 115ms. After allowing the status assertion to accept both `under_review` and the existing human-readable `Under review` format, the same exact command was rerun: **0 passed, 2 expected failures, 0 skipped**, duration 1.04s, component execution 124ms. Both executions reach visible question history before failing on missing SCRUM-95 controls. Validation, resubmission, notification and retention assertions after the first missing-functionality assertion are authored but **not reached** during RED. Likewise, backend write/rollback assertions are not reached beyond the missing endpoint. A failed test does not demonstrate that those later behaviors already work.

### Initial attempts and infrastructure, recorded separately

- The first backend execution used the same exact command and reported seven assertion failures across four methods (0 passed). One was a test-authoring defect: identity comparison between SQLAlchemy's annotated query column and its underlying table column. It was corrected to `shares_lineage()`; the rerun above confirms AC1 passes. The other six were the expected absent-endpoint failures. This initial assertion defect is not counted as a SCRUM-95 production gap or infrastructure error.
- The first frontend execution used the same exact command inside the sandbox and exited before test collection. esbuild reported ancestor-directory access denied and could not resolve `vitest.config.js`. That is **one infrastructure startup failure, zero tests executed**, not an expected RED failure. An approved elevated retry of the unchanged command loaded the existing config and produced the two behavioral failures above. No dependency or configuration change was made.
- No tests were skipped. No infrastructure failures remain in the completed focused runs. No engine/socket guard was triggered, and no database URL was used or printed.

Final read-only checks confirmed that the original story and all five AC strings match the pasted request verbatim, all three new files have clean whitespace, and `git status --short` lists only these three new files. `git diff --check` passed; there are no tracked-file modifications.

## Database impact and limits

Existing `Event`, `EventClarification` and `Notification` models are sufficient under A1. No schema change, SQL script, migration or dependency installation is required for SCRUM-95. RED used no database. GREEN accessed only the verified loopback Docker test database, using the restricted test role and existing `AppTestCase` rollback conventions. The isolated unit tests retain engine/socket guards; component API calls remain mocked. No Supabase access occurred.

Initial GREEN's persistence check could not run against the outdated default local schema. The later regression verification below passed the persistence check on the existing fresh SCRUM-95 test database, including actual committed rows and rollback after flushed writes. Live email delivery remains outside the evidence. No schema repair or migration was attempted.

## Open questions for the customer

- **Q1 (A1):** Is one chronological organiser reply saved on resubmission sufficient, without separate reply saving or per-question links? Confirm the narrow SCRUM-95 exception to SCRUM-31 A16 for returning an under-review request to Submitted; the existing coordinator start-review behavior remains unchanged.
- **Q2 (A2):** Should clarification resubmission edits use the existing normal-field set? The current organiser editor supports drafts only, and coordinator PATCH expressly denies organisers. The minimum proposal reuses validation on the additive resubmit action and retains restricted-field review.
- **Q3 (A3):** Confirm reuse of SCRUM-31 whitespace word counting/trimming and the existing in-app plus queued-email notification convention for coordinator recipients.

## Scope and handoff

The RED handoff was READY FOR GREEN under A1–A3. The subsequent user request authorized the narrow owner-only clarification editing/resubmission exception and reuse of existing messages, validators and notification conventions. Q1's chronological pending interpretation and Q2's exact editable subset remain recorded working assumptions rather than new acceptance criteria.

## GREEN verification — 30 Oct 2026

### Minimal implementation and SCRUM-31 dependency

- The existing history GET retains its authorization and query. It adds eligible-owner field values and `can_resubmit`. POST `/api/events/<id>/resubmit` independently rechecks stored-role ownership, an open status, an unanswered message and the current coordinator. An already answered request cannot be resubmitted again until another coordinator question is recorded.
- Resubmission reuses `NORMAL_FIELD_VALIDATORS` through `_validate_planning_edits()`. Following the focused PR correction below, restricted changes return 422 with permitted-field guidance rather than the unusable `requires_review` link; refused edits save nothing. The form exposes only the existing title, purpose, description and accessibility-needs text fields; the API also retains the existing normal-field list validators. No draft/coordinator editing permission is broadened.
- Reply, permitted edits, `submitted` status, last-saved timestamp and the coordinator's in-app notification share one commit. Following the focused PR correction below, the original `submitted_at` is preserved. Email is queued afterward via `_queue_email()` and the existing Celery task. The response captures plain values before commit expires ORM rows. Coordinator assignment is unchanged, and the existing review action continues to work.
- SCRUM-31 A16 has only the explicitly authorized SCRUM-95 exception: the rightful organiser can return a clarification-pending submitted/under_review request to Submitted by sending a valid reply. No general undo action, new lifecycle state or change to coordinator question/review actions was introduced. SCRUM-31 documentation is untouched.
- The existing clarification page provides reply/edit/resubmit controls, word-count feedback and success/error messages. Failed validation/saves keep both inputs and permit retry. A successful response appends the saved reply to history and closes the resubmission form. My Event Requests links open requests to this existing page.

### Exact files changed during GREEN

| Kind | File | Change |
|---|---|---|
| Production | `backend/app/events/routes.py` | Eligibility helper, additive history metadata, owner-only resubmit endpoint. |
| Production | `frontend/src/pages/ClarificationPage.jsx` | Existing page's reply/edit/resubmit controls and retained input. |
| Production | `frontend/src/pages/MyEventRequestsPage.jsx` | Clarification-history link for open requests. |
| Tests | `backend/tests/test_clarification_resubmission.py` | Pending-question query fixture; one guard method; one guarded local persistence method. Original RED assertions retained. |
| Tests | `frontend/src/pages/MyEventRequestsPage.test.jsx` | Exact link expectation includes the new clarification links; draft-editor prohibition retained. This directly affected regression initially failed on the additive links. |
| Documentation | `docs/test-cases/SCRUM-95-clarification-resubmission.md` | Current contract, implementation, results and database limitation. |

`frontend/src/pages/ClarificationPage.resubmission.test.jsx` was retained unchanged from RED during initial GREEN implementation. Its fixture was subsequently updated for the corrected `editable_fields` response during the focused regression correction recorded below; all meaningful assertions were retained. No models, schema scripts, dependencies, other stories' documentation or unrelated functionality changed.

### Results and exact commands

| Final focused selection | Passed | Failed | Skipped |
|---|---:|---:|---:|
| SCRUM-95 backend unit methods | 5 | 0 | 0 |
| SCRUM-95 local PostgreSQL persistence class | 0 | 0 | 1 |
| Direct backend regressions: review requests and HTTP authorization | 25 | 0 | 0 |
| SCRUM-95 frontend scenarios | 2 | 0 | 0 |
| Direct frontend regressions: clarification page and request list | 27 | 0 | 0 |

Initial database-free backend verification, from `backend/`, before adding the persistence class:

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_clarification_resubmission tests.test_review_requests_unit tests.test_authorization_http_unit
```

Result: **30 passed, 0 failed, 0 skipped**, 0.609s. The final backend run below reports `Ran 30 tests in 0.646s`, `OK (skipped=1)` because the persistence class skips in `setUpClass`. The original four RED methods all pass, including the previously unreached write, notification, review-continuation and rollback assertions.

Frontend command from `frontend/`, using the previously required elevated Vitest execution:

```powershell
npm.cmd test -- src/pages/ClarificationPage.resubmission.test.jsx src/pages/ClarificationPage.test.jsx src/pages/MyEventRequestsPage.test.jsx
```

First result: 28 passed, 1 failed on the request-list test's exact inventory of links. After the necessary expectation update, **29 passed, 0 failed, 0 skipped**, three files, 6.39s. The two unchanged SCRUM-95 scenarios now execute their full assertions. No full backend/frontend suite was run.

The existing local container was discovered with `docker ps --format '{{.Names}} {{.Ports}}'` after a sandbox permission denial. Its mapping is `127.0.0.1:5433`. The normal configured test URL was inspected without connecting and was not loopback, so it was never used. Local verification used this exact PowerShell/Python invocation from `backend/`, deriving existing local settings without printing credentials or hardcoding database names/passwords:

```powershell
@'
import json
import os
import subprocess
import unittest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

container = json.loads(subprocess.run(
    ['docker', 'inspect', 'trueadams-test-pg'], check=True, capture_output=True, text=True
).stdout)[0]
settings = dict(value.split('=', 1) for value in container['Config']['Env'] if '=' in value)
port = container['NetworkSettings']['Ports']['5432/tcp'][0]
assert port['HostIp'] == '127.0.0.1'
local_url = URL.create('postgresql+psycopg2',
    username=settings.get('POSTGRES_USER', 'postgres'), password=settings['POSTGRES_PASSWORD'],
    host=port['HostIp'], port=int(port['HostPort']),
    database=settings.get('POSTGRES_DB', settings.get('POSTGRES_USER', 'postgres')),
    query={'options': '-c role=connectsphere_test', 'connect_timeout': '5'})
assert make_url(local_url).host in {'127.0.0.1', 'localhost', '::1'}
os.environ['TEST_DATABASE_URL'] = local_url.render_as_string(hide_password=False)
engine = create_engine(local_url)
with engine.connect() as connection:
    assert connection.execute(text('select current_user')).scalar() == 'connectsphere_test'
engine.dispose()
print('Verified loopback PostgreSQL and restricted test role; no schema changes.')
suite = unittest.defaultTestLoader.loadTestsFromNames([
    'tests.test_clarification_resubmission', 'tests.test_review_requests_unit',
    'tests.test_authorization_http_unit'])
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | & .\.venv\Scripts\python.exe -
```

The initial local run executed 30 passing unit/regression methods but the persistence method produced two infrastructure error records: fixture insertion failed on the absent `events.safety_decision` column, followed by a pending-rollback error in its second subtest. `AppTestCase` cleanup rolled back the test transaction. This was not a resubmission behavior failure. No migrations were run. A read-only schema preflight now explicitly skips the local class before fixture writes if model columns are missing. The final rerun passed 30 methods and skipped that class once.

**Persistence/rollback verification limitation:** the existing local `events` table lacks `confirmed_at`, `confirmed_by_id`, `review_started_at`, `review_started_by_id`, `safety_comment`, `safety_decided_at`, `safety_decided_by_id`, and `safety_decision`. These are pre-existing model fields from other stories. Thus actual SCRUM-95 PostgreSQL commit/rollback remains **unverified**; the unit tests verify rollback handling and a shared commit boundary. The guarded local check remains available for a compatible test database. No schema changes are needed by this story, and none were made here.

**Initial GREEN verdict: READY FOR REVIEW**, with the local persistence limitation recorded above. That limitation is resolved by the subsequent focused verification below. Original Jira story and all five ACs remain verbatim; TC-95 IDs and traceability are retained. No Supabase/remote database access, commit, push or PR occurred.

## Focused SCRUM-31 payload regression correction — 30 Oct 2026

**Cause and minimum fix:** SCRUM-95 merged normal editable fields into the eligible owner's existing clarification `event` summary. This broke SCRUM-31's exact summary assertion for organiser Dana. Restore that four-key summary and put SCRUM-95 values in sibling `editable_fields` metadata; the existing clarification page initializes and compares its form against that metadata. The existing event-detail endpoint exposes title/description but not purpose/accessibility needs, so another fetch cannot replace all four fields without further contract changes. No additional request or endpoint was introduced. Reply, validation, ownership, status, notification and save-failure behavior remain unchanged.

**Files changed for this correction only:** `backend/app/events/routes.py`, `frontend/src/pages/ClarificationPage.jsx`, `frontend/src/pages/ClarificationPage.resubmission.test.jsx` (fixture shape only; all assertions retained), and this document. SCRUM-31's tests and other stories' documentation are unchanged; no tests were added.

The existing container's default `postgres` database was still outdated. Read-only metadata inspection also located `trueadams_s95_fresh`; its Event columns matched the model. Tests used only that existing database on `127.0.0.1:5433`, verified `current_user = connectsphere_test`, and set `TEST_DATABASE_URL` only in child-process environments. Credentials came from the existing local container configuration and were not printed. No database/schema creation or migration occurred.

Commands executed from `backend/` using the existing virtual-environment Python and the verified loopback test environment:

```powershell
python -m unittest -v tests.test_event_clarifications
python -m unittest -v tests.test_clarification_resubmission
```

Frontend command from `frontend/`:

```powershell
npm.cmd test -- src/pages/ClarificationPage.resubmission.test.jsx src/pages/ClarificationPage.test.jsx
```

| Focused module | Passed | Failed | Skipped |
|---|---:|---:|---:|
| `tests.test_event_clarifications` | 24 | 0 | 0 |
| `tests.test_clarification_resubmission` | 6 | 0 | 0 |
| SCRUM-95 frontend scenarios | 2 | 0 | 0 |
| Existing clarification-page frontend scenarios | 14 | 0 | 0 |

The original failing organiser subtest now passes without modifying its assertion. `ClarificationResubmissionLocalTests.test_local_postgresql_commits_together_and_rolls_back_a_failed_resubmission` **ran and passed**, including both success and injected commit-failure subtests, so SCRUM-95 persistence/rollback is verified on this fresh local database. The user's prior full-suite aggregate (1,169 tests, eight skips) does not identify individual skips; no detailed log was present, so membership of those eight cannot be confirmed retrospectively. The earlier agent-run skip was specifically caused by missing model columns in the default local database, not the fresh database used here.

**Verdict: READY FOR REVIEW.** All five SCRUM-95 ACs and their meaningful assertions remain satisfied in focused verification. Original Jira story/AC wording remains verbatim. No full suite, Supabase/remote access, schema changes, unrelated changes, commits or pushes occurred. Stopped after this specific regression correction.

## Focused PR #70 review corrections — 30 Oct 2026

Only the authorized correctness corrections were applied. Existing TC-95 IDs and AC mappings are retained.

- **Finding 1 / TC-95-03:** resubmission eligibility is checked after ownership/basic reply/body validation and before evaluating edits. The existing guard test now sends restricted edits to a closed request and verifies the ordinary not-awaiting-clarification 409. Eligible restricted edits receive 422 listing the existing permitted fields and asking for the other edits to be removed. No SCRUM-46 link is returned, and the refusal/no-write assertions remain. The previous `requires_review` expectation was corrected because it encoded the misleading behavior being fixed; SCRUM-31/46 tests and implementations are untouched.
- **Finding 2 / TC-95-04:** SCRUM-29 records `submitted_at` when a draft is originally submitted; request lists and the Lead queue order by it. No inspected contract defines it as the latest resubmission time. Resubmission now preserves it and updates only `last_saved_at`. The existing success test checks the original timestamp in the object/response, update metadata and unchanged review-start fields. The local persistence test also asserts original submission-time preservation and last-saved behavior on success/rollback; its new assertions could not be executed against PostgreSQL in this review run.
- **Finding 3 retained:** SCRUM-31 A11 records who started the review and when. It does not define these fields as current-cycle-only data. Retain the earlier `review_started_at` and `review_started_by_id` on resubmission; the existing start-review action records the next start normally. No review-history subsystem or metadata reset was introduced.
- **Finding 4 / TC-95-03, TC-95-05:** an organiser resubmission 409 stops the action and refreshes the existing clarification GET without reinitializing reply/edits. If no longer eligible, the updated status is shown and the entered values remain visible in disabled controls. If eligibility cannot be confirmed, the action stays stopped and entries remain. Existing validation/503 failures still allow ordinary retry. One new frontend scenario simulates a coordinator approval after the initial load, then verifies refresh, Approved status, retained reply/description and no second POST through the disabled action.
- **Other suggestions left out of scope:** no rewrite of mocked tests, helper refactoring, dictionary extraction, stylistic notification changes, expanded emails, word-limit redesign, SCRUM-46/52 changes, additional editable fields, dependencies or schema changes. Existing `Must match` comments already cover the duplicated limits/field list; no comment-only change was needed.

**Exact files changed:** `backend/app/events/routes.py`, `backend/tests/test_clarification_resubmission.py`, `frontend/src/pages/ClarificationPage.jsx`, `frontend/src/pages/ClarificationPage.resubmission.test.jsx`, and this document. No other tests or documents changed.

### Execution evidence

Before production corrections, `python -m unittest -v tests.test_clarification_resubmission.ClarificationResubmissionTests` produced **3 passed, 2 failed, 0 skipped**: the restricted-edit response took precedence over eligibility and `submitted_at` changed. The frontend SCRUM-95 file produced **2 passed, 1 failed, 0 skipped**: the stale-409 scenario never refreshed to Approved. After implementation, all five unit methods passed in 0.118s.

Final backend selection used `unittest.defaultTestLoader.loadTestsFromNames` with these exact targets, under a preflight that confirmed the configured URL was not loopback so the local-only class would skip before connecting:

```text
tests.test_clarification_resubmission
tests.test_review_requests_unit.ReviewRequestsUnitTests.test_clarification_history_contains_only_the_selected_requests_messages
```

Final frontend command from `frontend/` (existing elevated Vitest workaround):

```powershell
npm.cmd test -- src/pages/ClarificationPage.resubmission.test.jsx src/pages/ClarificationPage.test.jsx
```

| Final focused selection | Passed | Failed | Skipped |
|---|---:|---:|---:|
| SCRUM-95 backend unit methods | 5 | 0 | 0 |
| Existing backend clarification-history regression | 1 | 0 | 0 |
| SCRUM-95 local PostgreSQL persistence class | 0 | 0 | 1 |
| SCRUM-95 frontend scenarios | 3 | 0 | 0 |
| Existing clarification-page frontend scenarios | 14 | 0 | 0 |

Backend output: `Ran 6 tests in 0.129s`, `OK (skipped=1)`. Frontend: **17 passed**, two files, 6.67s. Ownership, word-boundary, notification, review-continuation, rollback-handling and retained-input assertions remain intact.

**Current database limitation:** `docker ps --format '{{.Names}} {{.Ports}}'` could not connect because the Docker Desktop Linux daemon pipe was absent. No container/database was started or changed. The configured test URL was non-loopback, so the persistence class skipped via its existing guard; no Supabase/remote database was accessed. The full database-backed SCRUM-31 module was not run without local PostgreSQL. The earlier successful fresh-local commit/rollback verification remains historical evidence; it was **not repeated for these corrections**. No claim is made that the newly added persisted timestamp assertions ran today.

**Verdict: READY FOR REVIEW**, with that explicit database-verification limitation. SCRUM-31 response/question/review contracts and SCRUM-46/52 behavior are preserved. The original Jira user story and all five ACs remain verbatim. No full suite, remote access, schema changes, commits, pushes or additional PR occurred. Stopped after the scoped corrections and focused checks.
