# SCRUM-92 — Safety Officer Rejects an Event or Requests Changes

**User story:** As a Safety Officer, I want to reject an event's safety arrangements or request specific changes, with a comment, so that the coordinator can fix the problems before the event is confirmed.

**Story:** SCRUM-92 · **Related:** [SCRUM-90](SCRUM-90-safety-check-queue.md), [SCRUM-91](SCRUM-91-safety-approval.md), [SCRUM-93](SCRUM-93-confirm-event.md).

**Automated tests:** [Backend](../../backend/tests/test_safety_rejection_changes.py), [frontend](../../frontend/src/pages/SafetyCheckQueuePage.rejection.test.jsx).

This document records the focused scout/RED phase and the subsequently authorized minimum GREEN implementation. Schemas and other stories' documentation are unchanged.

## Acceptance criteria

- **AC1:** The Safety Officer can reject an event in the list or request changes to it. A comment is required and cannot be blank. For a request for changes, the comment says what must change.
- **AC2:** A rejected event, or an event with changes requested, returns to Planning. The coordinator is notified of the decision and the comment, and decides the next action.
- **AC3:** The decision, the officer, the comment and the time are saved and visible to the coordinator.
- **AC4:** After the coordinator has updated the event, it appears in the list again for a new safety check, and it cannot be marked Confirmed until it is approved.
- **AC5:** Only a Safety Officer can reject or request changes. Anyone else is denied and nothing changes.
- **AC6:** If saving fails, the decision is not recorded and an error is shown.

## Focused read-only scout

The scout inspected only relevant source, tests, setup instructions and story documentation. It completed before writing files; it made no database connections.

| Question | Finding and smallest proposed reuse |
|---|---|
| Existing storage sufficient? | `Event.safety_decision` is nullable `varchar(20)` with no model enum; `rejected` and `changes_requested` fit. `safety_decided_by_id`, `safety_comment` and `safety_decided_at` already store the other three facts. Latest outcome storage satisfies the AC; no history table is required. This is a source inspection, not verification of the live schema. |
| Return to Planning? | No `planning` lifecycle status or label exists. The existing arrangement-planning stage uses `approved`. On 29 Oct 2026 the user explicitly selected retaining that stage and recording the negative safety outcome separately. This does not reject the organiser's original event request. |
| Can coordinator edit? | `PATCH /api/events/<id>` permits only the assigned stored coordinator and excludes only cancelled events. It accepts description/accessibility and other normal fields at `approved`; restricted fields still require the existing review flow. Planning GET already includes the safety summary. |
| Queue versus awaiting correction? | SCRUM-90 currently filters out approved safety decisions only, then checks confirmed venue coverage and full active equipment quantities. A ready event with a negative decision would reappear immediately. SCRUM-91 approval also needs the same waiting-for-correction gate to avoid approving via a direct POST before an update. |
| Smallest update evidence? | `Event.last_saved_at` exists but only draft creation/saves write it; planning PATCH writes no timestamp or actor metadata. Draft saves require a draft, so they cannot legitimately modify the approved-stage event. Proposed GREEN: on a successful assigned-coordinator PATCH that actually changes a permitted value after a negative safety decision, set existing `last_saved_at` to naive UTC in the same transaction. Recheck requires it to be later than `safety_decided_at`, plus the existing readiness rules. No new column is necessary for this bounded path. Denied, failed, empty, unchanged or restricted-only attempts must not qualify. These are design boundaries, not extra Jira ACs or an exhaustive test matrix. |
| Resume confirmation? | Keep lifecycle `approved`; after the update, reuse SCRUM-91 approval, then existing `POST /api/events/<id>/confirm`. SCRUM-93 already requires `approved`, confirmed venue coverage, complete equipment reservations and a persisted `approved` safety decision. No parallel confirmation mechanism or change to its prerequisites is needed. |
| Notifications and planning summary? | Reuse existing `Notification`, one decision/notification commit, and `_queue_email` after commit. `_safety_decision_payload` and planning GET already expose arbitrary decision strings, officer, comment and timestamp. Existing planning UI displays these; `changes_requested` needs a small readable label extension. Add actions to the existing safety queue; keep the coordinator in the existing planning view. |
| Failed-save transaction boundary? | Set four safety fields and add the coordinator notification before one commit. On `SQLAlchemyError`, roll back and return a human retryable 503; no queued email. The coordinator-update timestamp likewise belongs in its existing PATCH transaction. A mock session cannot establish real row durability; the guarded local test flushes real SQL then forces commit failure. |

### Event-status compatibility

Retaining `approved` for Planning is user-confirmed for this increment. Venue requests, booking/hold approval, equipment reservations, event change requests and SCRUM-93 confirmation already require `approved`; their rules remain intact. Equipment arrangement/edit helpers instead exclude `cancelled` and `rejected`. Setting lifecycle `rejected` would exclude the event from the safety queue and trigger `resources/release.py` to release equipment on flush. A new `planning` lifecycle value would block the approved-only operations and require cross-story changes. Neither transition is proposed.

The safety rejection is `safety_decision == "rejected"`, never lifecycle rejection. Existing reservations are retained; this story adds no automatic corrective action. Publication/registration rules also currently use `approved` and are outside this increment. No such rule is changed or newly tested here.

## Working assumptions and decisions

- **A1 / Q1 — Implemented API, authorized for GREEN:** follow SCRUM-91 with `POST /api/events/<id>/safety-checks/reject` and `POST /api/events/<id>/safety-checks/request-changes`, JSON `{comment: string}`. Store `rejected` / `changes_requested`; return HTTP 200 with the existing `safety_check` and `notification` structure. Missing, empty and whitespace-only comments return 400 with `field: "comment"`. No length limit is introduced. Required changes are supplied by the officer in plain text; semantic or automated assessment of that text is not required.
- **A2 / Q2 — Agreed working assumption, 29 Oct 2026:** Planning means the existing `approved` arrangement stage with a separate negative safety decision. This mapping is an implementation assumption, not a new customer requirement. The coordinator chooses the corrective action; neither existing bookings nor reservations are automatically released.
- **A3 / Q3 — Implemented bounded recheck trigger:** a real, successful permitted update by the assigned stored coordinator qualifies. TC-92-04 uses a changed description of the corrected access route through existing PATCH. Preserve the negative summary until a new safety decision so the coordinator can still see it. Reuse `last_saved_at` as described above, rather than resetting the decision or adding a workflow/history table. A changed requirement or booking made by another role does not itself constitute the coordinator's update. Whether accepting a restricted-field change request should also count is not settled; this test makes no assertion about that path.
- **A4 / Q4 — Existing notification convention:** notify the assigned coordinator through the existing in-app mechanism, with decision and exact comment. Reuse existing post-commit email; no additional channel. The fixture has an assigned coordinator, so there is no new missing-assignee requirement.

## Seed data — SR-SEED

One ready approved-stage event, "Safety corrections workshop", assigned coordinator C1, Safety Officer S1, other coordinator C2, expected attendance 40. One confirmed venue booking fully covers 16 Jan 2030 17:00–19:00 Singapore local time; one recorded microphone requirement is fully covered by an active reservation. Freeze Singapore-local now at 16:00. The old `last_saved_at` precedes any safety decision. Comment: "Keep the emergency exit clear and describe the revised access route."

Unit records are in memory; query fixtures evaluate production predicates rather than returning a precalculated queue. Actual readiness, decision, coordinator update, approval and confirmation logic is never patched. SQLAlchemy connection and socket-connect guards forbid database/network access. Imports suppress `.env` loading. No private helpers are imported from another story's tests.

The single optional local method combines AC3 durability and AC6 rollback, testing both actions with separate events. It uses `AppTestCase` helpers, unique emails and outer rollback, inspecting only its own event/notifications. Before app creation it requires an explicit loopback PostgreSQL `TEST_DATABASE_URL` and refuses the configured development target. It creates no schema and never falls back to `DATABASE_URL`. If no safe prepared target is available, it skips before connecting.

## AC1 — Actions and required comment

**TC-92-01 · Reject or request changes with a nonblank comment**

- **Traces to:** AC1 · **Type:** Positive/negative HTTP unit and UI.
- **Preconditions:** Ready SR-SEED, Safety Officer JWT.
- **Steps:** For each action, submit omitted, empty and whitespace-only comments, then the supplied comment. In the queue, attempt empty/whitespace input, then supply the comment and select the action.
- **Expected result:** Bad comments are refused before writes; valid action stores the correct decision and exact supplied comment. UI sends no blank-comment POST, sends one valid POST and displays server success feedback.
- **Automated:** `SafetyRejectionChangesUnitTests.test_both_actions_require_a_comment_and_preserve_the_supplied_text`; frontend `requires a comment for both actions, shows success and exposes the coordinator outcome`.

## AC2 — Planning and coordinator notification

**TC-92-02 · Return control to Planning and notify the assigned coordinator**

- **Traces to:** AC2; overlaps AC3 · **Type:** HTTP unit.
- **Preconditions:** Ready SR-SEED; A2's user-confirmed Planning mapping.
- **Steps:** Submit each negative decision; inspect event stage and notification; GET planning as C1.
- **Expected result:** Existing approved planning stage, the chosen safety outcome, one commit with a Notification to C1 containing decision and exact comment. Coordinator can view the outcome and choose their next action. No automated replanning.
- **Automated:** `SafetyRejectionChangesUnitTests.test_planning_outcome_and_comment_notify_the_assigned_coordinator`; existing planning UI exercised within TC-92-01's frontend success scenario.

## AC3 — Stored decision and coordinator visibility

**TC-92-03 · Persist and expose decision, officer, comment and time**

- **Traces to:** AC3 · **Type:** HTTP response/read plus optional PostgreSQL persistence.
- **Preconditions:** SR-SEED; real-storage assertions require a separate prepared loopback test database.
- **Steps:** Submit each action, expire ORM state, reload and GET planning as C1.
- **Expected result:** Exact decision/comment, S1 ID and naive UTC decision timestamp between request start/end. Planning summary exposes all four facts, including S1's identity. Latest-outcome fields suffice; no new history table.
- **Automated:** HTTP summary in `test_planning_outcome_and_comment_notify_the_assigned_coordinator`; real storage in `SafetyRejectionChangesLocalTests.test_flushed_failure_is_atomic_and_retry_persists_coordinator_visible_decision` (successful retry). Frontend reuses the existing summary for each decision.

## AC4 — Correction then a fresh safety check

**TC-92-04 · Wait for the coordinator's update, recheck readiness, then require new approval**

- **Traces to:** AC4 · **Type:** Sequential HTTP unit workflow.
- **Preconditions:** SR-SEED with a stored rejection or changes request; decision submission itself is TC-92-01. Existing SCRUM-91 and SCRUM-93 routes are present.
- **Steps:** GET queue immediately; attempt PATCH as C2; GET again; C1 saves a changed description explaining the corrected access route. GET queue, temporarily release the required reservation and GET, then restore readiness and GET. Attempt existing confirmation; approve through existing safety action; attempt confirmation again.
- **Expected result:** Absent before coordinator correction; another user's denied update changes nothing. Present after C1's successful update only when the established venue/equipment prerequisites hold. Confirmation returns 409 specifically missing `Approved safety check` before approval, then succeeds after the fresh approval. No direct fixture status/safety approval is assigned to bypass the workflow.
- **Automated:** `SafetyRejectionChangesUnitTests.test_recheck_waits_for_coordinator_correction_and_new_approval` (both negative outcomes). Only the initial stored negative outcome is seeded.

## AC5 — Authorization

**TC-92-05 · Deny missing authentication and other stored roles without writes**

- **Traces to:** AC5 · **Type:** Negative HTTP authorization; positive officer access in TC-92-01.
- **Preconditions:** Ready SR-SEED. Authenticated JWT claims Safety Officer while the stored role differs.
- **Steps:** Submit both actions without a token and as stored admin, coordinator, coordinator_lead, organiser, venue_staff, tech_staff and attendee.
- **Expected result:** 401 without authentication; otherwise 403. Event unchanged, no added notification, no commit and no queued email.
- **Automated:** `SafetyRejectionChangesUnitTests.test_other_roles_and_missing_authentication_cannot_write`.

## AC6 — Save failure

**TC-92-06 · Roll back the decision and notification together and show the error**

- **Traces to:** AC6 · **Type:** HTTP failure, optional PostgreSQL transaction and UI.
- **Preconditions:** Ready SR-SEED; commit raises `SQLAlchemyError`. Local test flushes SQL before failure; UI mock returns retryable 503.
- **Steps:** Submit both actions during save failure. For the local test, expire/reload every event field and count its notifications. In the UI, inspect error/input and retry.
- **Expected result:** Human retryable 503, no success summary or private exception text, rollback and no email. Actual reload shows unchanged status and all safety metadata; no partial notification persists. UI displays server error, keeps event/comment, offers the same action for retry and never reports success.
- **Automated:** `SafetyRejectionChangesUnitTests.test_save_failure_returns_retryable_error_without_success_or_email`; failure half of `SafetyRejectionChangesLocalTests.test_flushed_failure_is_atomic_and_retry_persists_coordinator_visible_decision`; frontend `shows a failed save for either action without success or losing the comment`.

## Traceability matrix

| AC | Cases | Backend | Frontend |
|---|---|---|---|
| AC1 | TC-92-01 | Required comment and both actions | Combined success/validation scenario |
| AC2 | TC-92-02 | Planning, notification and coordinator read | Same success scenario, existing planning view |
| AC3 | TC-92-03 | Summary plus optional real persistence | Same existing planning view |
| AC4 | TC-92-04 | Actual queue → coordinator PATCH → approval → confirmation | — |
| AC5 | TC-92-05 | Stored-role and unauthenticated denials | — |
| AC6 | TC-92-06 | HTTP rollback branch plus optional flushed transaction | Combined failure/retained-input scenario |

## Open questions for the customer

| ID | Question or resolved decision | Assumption/cases |
|---|---|---|
| Q1 | GREEN authorization adopts the RED action URLs, stored decision spelling and 400 comment-field contract as implementation choices. | A1; TC-92-01/02/03/05/06 |
| Q2 | Resolved: user selected the existing approved planning stage on 29 Oct 2026. | A2; TC-92-02/04 |
| Q3 | GREEN authorizes the existing coordinator PATCH correction path. Whether acceptance of a restricted change request should also count remains outside this increment. | A3; TC-92-04 |
| Q4 | Reuse assigned-coordinator notification behavior from SCRUM-91, including existing post-commit email. No new missing-assignee behavior is specified. | A4; TC-92-02/06 |

## RED execution — 29 Oct 2026

Only the new focused SCRUM-92 tests were selected. No full suite was run.

Backend command, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_rejection_changes
```

**Final backend execution of the delivered tests:** exit 1, 6 methods run in 0.115 seconds; **0 passed, 5 failed methods (30 failed subtest assertions), 1 skipped, 0 errors**.

| Case | Actual result and limit |
|---|---|
| TC-92-01 | FAIL: all eight action/comment subtests return 404 instead of 400/200 because the two proposed actions are missing. Comment validation and writes are not reached. |
| TC-92-02/03 | FAIL: both decision submissions return 404 instead of 200. Before those POSTs, coordinator GET planning assertions **pass** for each seeded negative outcome, correctly returning the existing four-fact summary. New decision creation/notification assertions are not reached. |
| TC-92-04 | FAIL: both recorded negative outcomes appear immediately in the queue (`[1]` rather than `[]`). Before that assertion, the actual SCRUM-93 confirmation action **passes** its negative safety prerequisite check for both outcomes: 409, only `Approved safety check` missing, no status change or commit. Coordinator correction/reappearance/subsequent approval and confirmation assertions are defined but not reached in this RED run. |
| TC-92-05 | FAIL: all 16 action/authentication subtests return 404 rather than 401/403. No-change assertions are defined but not reached. |
| TC-92-06 | FAIL: both isolated save-failure subtests return 404 instead of 503; route-level rollback/error handling is missing, not executed. |
| TC-92-03/06 local | SKIP before app creation/connection: `No explicit loopback PostgreSQL TEST_DATABASE_URL; .env is not loaded.` Actual storage, flushed rollback and notification durability remain unverified. |

Initial module execution also produced the same expected 30 subtest failures and one skip (0.156 seconds). Adding direct assertions for existing coordinator-summary reuse exposed a test-fixture issue: the new query fixture lacked iteration used by the existing planning route. The intermediate module run had 28 expected assertion failures, two fixture errors and one skip; those two errors are **not** product RED evidence. This diagnostic command isolated the same two fixture errors:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_rejection_changes.SafetyRejectionChangesUnitTests.test_planning_outcome_and_comment_notify_the_assigned_coordinator
```

Adding iteration to the test query fixture corrected it; the subsequent module run reported the expected 30 assertion failures and no errors (0.109 seconds). After adding local-only notification durability assertions, the final module run retained those counts (0.115 seconds). No production helper was changed or replaced to obtain these results. Existing naive UTC calls emit deprecation warnings without affecting outcomes.

Frontend command, from `frontend/`:

```powershell
$env:DEBUG_PRINT_LIMIT='600'
npm.cmd test -- src/pages/SafetyCheckQueuePage.rejection.test.jsx --reporter=dot
```

The sandboxed attempt failed before test collection: esbuild could not read an ancestor directory/resolve the existing Vitest config. This is an **infrastructure failure**, not an expected test failure. The same focused command was retried with expanded sandbox permissions and loaded normally.

**Actual frontend:** Vitest 2.1.9; one file, **0 passed, 2 failed, 0 skipped**, exit 1; test time 1.178 seconds, total duration 29.60 seconds. Both scenarios load the event and existing comment input, then fail to find the Reject button. The failure scenario successfully types the comment first. The loops stop at the first missing action control; request-changes POST, validation, success, coordinator rendering, error display and retry assertions are defined but not reached. Source inspection also confirms that Request Changes is absent. No runtime/import/fixture errors occurred in the executable frontend run.

**Combined expected RED:** 8 defined methods/UI tests; **0 passed, 7 failed, 1 skipped**. The 30 backend subtest failures are within five methods, not 30 separate tests. Existing readiness, negative-outcome planning-summary reads and SCRUM-93 safety refusals passed as assertions within the RED methods; they are not separate passing test cases.

Final static verification confirmed the user story and all six AC sentences match the attached request verbatim, the Python test module parses, and all three files have no trailing whitespace. `git status --short` shows exactly those three new files; tracked production files have no diff. `git diff --check` passed. The frontend file was unchanged after its executable RED run.

**Database impact and safety:** No new fields or schema changes appear necessary for the bounded normal-field correction path; the four safety fields and existing `last_saved_at` can support it with minimal later application changes. No database was accessed, including **Supabase**, remote/shared databases or local development data. No Docker database was provisioned, no `.env` was loaded by the focused backend module, and no DDL, schema script or migration was executed. The local test remains safely skipped until a separate prepared loopback PostgreSQL target is supplied.

**Blockers:** no missing production dependency prevents starting GREEN: SCRUM-90 readiness, SCRUM-91 approval and SCRUM-93 confirmation are present. Actual transaction verification requires a safe prepared local test database. API spelling and what constitutes a sufficient corrective update remain explicit working assumptions for review; neither is presented as a new agreed AC. Restricted change-request acceptance is outside the tested correction path.

**Scope:** exactly three new files: the linked backend test module, frontend test file and this document. No production files, SQL scripts, dependencies, other story tests/documents, attendee registration/publication rules, booking/equipment release rules or shared workflow rules changed. No SCRUM-91 or SCRUM-93 reimplementation, commit, push, merge or PR.

**Historical RED verdict: READY FOR GREEN**, using the user-confirmed approved-stage mapping and the documented bounded-update assumption. The later authorization and results follow.

## GREEN execution — 29 Oct 2026 (Singapore)

All six original AC sentences, the user story, TC-92-01 through TC-92-06 and their traceability remain intact. The six backend methods and two frontend scenarios are retained; no extra cases or exhaustive matrix were added. Two genuine fixture corrections were necessary: reset the email mock between AC4 workflow subtests, and use a separate venue for the second local event to respect the existing confirmed-booking exclusion constraint. Existing assertions were not weakened. Small assertions within TC-92-01/04 also verify that decision saves leave `last_saved_at` unchanged, no-op coordinator PATCHes do not reopen the queue, and direct approval cannot bypass the correction gate.

### Implementation and AC coverage

| AC | Implemented behavior |
|---|---|
| AC1 | Existing safety queue offers Reject and Request Changes using the shared comment input. Both require nonblank text in UI and API; help text asks the officer to explain what must change. Approval comments remain optional, with no new comment length limit or dialog. |
| AC2 | Both actions keep/return lifecycle status to `approved` under A2 and store the negative outcome separately. Existing coordinator Notification includes decision and comment; existing email queues after commit. No automatic booking/equipment changes. |
| AC3 | Existing four Event fields store decision, officer, exact normalized comment and naive UTC timestamp. Existing planning endpoint/page exposes the summary; the only display extension is the readable `Changes requested` label. Real PostgreSQL reload verified both outcomes. |
| AC4 | A negative outcome is excluded until existing `last_saved_at` is strictly later than `safety_decided_at`. Only an actual permitted value change in an authenticated assigned-coordinator PATCH advances that timestamp, in its save transaction. No-op, invalid, denied and restricted-only saves cannot qualify. Existing draft saves cannot operate on the approved event; other system writes do not advance this Event field. Existing venue/equipment readiness still governs reappearance. The same small pending-correction check protects direct safety approval; all other SCRUM-91 approval behavior is retained. Negative metadata remains visible until the new decision. SCRUM-93 confirmation is unchanged and refuses until the new approval. Refresh clears old queue feedback so a corrected event can receive a fresh decision. |
| AC5 | Existing JWT/current-user lookup and stored Safety Officer role set protect both actions; no admin override. Denials leave event/notifications unchanged. |
| AC6 | Decision and coordinator Notification share one commit. Database errors roll back and return retryable 503 without success or email. Real flush/failure/reload verified unchanged event fields and no partial notification for both actions; successful retries persist the complete outcome. UI displays the server error, retains comment/event and permits retry. |

### Actual focused results

The first isolated backend run had four passing methods, one failed workflow method and one safe local-database skip. The failure was the prior subtest's successful approval-email mock call, corrected by resetting the mock. The first real PostgreSQL run executed 59 methods with 58 passing and one method reporting two errors: its second event fixture reused an overlapping confirmed booking on the same venue, followed by the resulting pending-rollback error. A separate venue fixed the fixture. These were test-fixture issues, not reasons to change production behavior.

**Local database preflight:** the existing `trueadams-test-pg` PostgreSQL 17 container publishes only `127.0.0.1:5433`. Its existing `trueadams_s93_fresh` test database already had the required safety, save-time and confirmation fields. A read-only preflight verified loopback, PostgreSQL, the target database and effective role `connectsphere_test`. Its role password was not configured in the shell; a transient Python launcher read the existing container owner credential in memory and supplied PostgreSQL startup option `-c role=connectsphere_test` for every test connection. No credential was printed, hardcoded in repository files or changed. No role/policy changes occurred. The launcher cleared `DATABASE_URL` from the child environment, passed only the verified local `TEST_DATABASE_URL`, and the first test module suppressed `.env` loading. Existing `AppTestCase` savepoints and outer rollback isolated all row writes.

The launcher ran this exact backend selection from `backend/` (the URL was supplied only in the child process environment):

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_rejection_changes tests.test_safety_check_queue_unit tests.test_safety_approval.SafetyApprovalUnitTests.test_officer_can_approve_with_or_without_a_comment tests.test_safety_approval.SafetyApprovalUnitTests.test_failed_save_returns_an_error_and_rolls_back_without_email tests.test_safety_approval.SafetyApprovalUnitTests.test_other_roles_and_unauthenticated_callers_cannot_change_anything tests.test_event_confirmation tests.test_safety_approval.SafetyApprovalLocalTests tests.test_event_planning_info.PlanningFieldsTests.test_every_planning_field_is_always_present tests.test_event_planning_info.ViewPlanningInformationTests.test_assigned_coordinator_sees_the_events_planning_information tests.test_update_event_planning_info
```

**Final backend result: 59 passed, 0 failed, 0 skipped, 0 errors; exit 0; 2.008 seconds.** SCRUM-92's six methods all passed, including real transaction rollback and successful persistent retries for both negative outcomes. The other 53 methods cover existing safety queue, approval, confirmation and directly affected coordinator planning reads/updates. The obsolete SCRUM-91 dependency-skipped method was not selected; actual confirmation-gate coverage comes from SCRUM-92/93. Existing naive-UTC deprecation and test JWT key-length warnings did not fail tests.

After a final notification wording correction, the same verified-local launcher reran `.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_rejection_changes`: **6 passed, 0 failed, 0 skipped, 0 errors; exit 0; 0.295 seconds**. These repeat the same six methods and do not increase the unique test count.

Frontend command, from `frontend/`, with expanded sandbox access for the previously established esbuild config restriction:

```powershell
$env:DEBUG_PRINT_LIMIT='600'
npm.cmd test -- src/pages/SafetyCheckQueuePage.rejection.test.jsx src/pages/SafetyCheckQueuePage.approval.test.jsx src/pages/SafetyCheckQueuePage.test.jsx src/pages/EventPlanningPage.test.jsx src/pages/EventPlanningPage.confirmation.test.jsx --reporter=dot
```

**Frontend result: 30 passed, 0 failed, 0 skipped; 5 files; exit 0; 13.22 seconds.** Both SCRUM-92 scenarios passed for both actions, including required comments, success, coordinator outcome display, error retention and retry. The other 28 existing queue/approval/planning/confirmation tests passed. Frontend production/tests were unchanged after this run. No full backend or frontend suite was run.

### Exact scope and remaining limits

- **Production:** `backend/app/events/routes.py`, `frontend/src/pages/SafetyCheckQueuePage.jsx`, `frontend/src/utils/statusLabel.js`.
- **Tests:** `backend/tests/test_safety_rejection_changes.py` received only the fixture corrections, focused safeguards and stale RED-comment updates described above. `frontend/src/pages/SafetyCheckQueuePage.rejection.test.jsx` remains unchanged from RED and passed as written. No other story's tests were edited.
- **Documentation:** only this SCRUM-92 document was updated.
- **Database:** no models, fields, tables, dependencies, DDL, schema scripts or migrations changed. No schema setup was needed. The existing container/database remains in place; test rows use rollback isolation. **Supabase and remote/shared databases were not accessed.** Normal development data was not modified.
- **Limits:** normal permitted coordinator edits are the implemented correction trigger under A3; accepting restricted-field change requests is not newly wired as a trigger. Planning-to-approved remains the agreed working assumption. No other implementation blocker was found. No publication/registration, booking/equipment cancellation, reassignment or unrelated lifecycle behavior changed. No commit, push or PR.

Final static checks confirmed the original user story and all six AC sentences match the GREEN request verbatim, Python files parse, the six scoped files have no trailing whitespace, and `git diff --check` passes.

**Verdict: READY FOR REVIEW.** Scoped GREEN and focused verification are complete; stop here.
