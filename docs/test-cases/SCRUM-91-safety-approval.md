# SCRUM-91 — Safety Officer Approves an Event: Test Cases

**User story:** As a Safety Officer, I want to approve an event's safety arrangements, so that the event can be confirmed.

**Created:** 28 Oct 2026 (Singapore) · **Phase:** bounded GREEN for AC1, AC2, AC4 and AC5 · **Verdict:** READY FOR REVIEW for the safety-approval increment; AC3 remains BLOCKED by SCRUM-93 and PostgreSQL persistence/rollback verification remains pending.
**Requirements source:** Jira wording supplied by the user; no Jira URL supplied.
**Automated tests:** [backend](../../backend/tests/test_safety_approval.py), [frontend](../../frontend/src/pages/SafetyCheckQueuePage.approval.test.jsx).
**Related:** [SCRUM-90 queue](SCRUM-90-safety-check-queue.md), [SCRUM-76 access boundaries](SCRUM-76-authorised-access.md). Those documents are unchanged.

## Acceptance criteria

| ID | Criterion (verbatim) |
|---|---|
| AC1 | The Safety Officer can approve an event in the list and can add a comment. |
| AC2 | The decision, the officer, the comment and the time are saved and visible to the coordinator, who is notified. |
| AC3 | The coordinator cannot mark the event Confirmed until the safety check is Approved |
| AC4 | Only a Safety Officer can approve. Anyone else is denied and nothing changes. |
| AC5 | If saving fails, the decision is not recorded and an error is shown. |

## Original read-only scout findings (before GREEN)

The scout changed no files and accessed no database.

| Need | Existing implementation / reuse |
|---|---|
| Queue and action | `GET /api/events/safety-checks` in `backend/app/events/routes.py`; `SafetyCheckQueuePage.jsx` renders its rows. Add an approval action to each existing row during GREEN. No separate page is needed. |
| Ready event | SCRUM-90 checks confirmed venue periods covering the event and full reserved equipment quantities, or its existing no-equipment interpretation. Reuse those rules without extra eligibility requirements. |
| Officer authorization | SCRUM-90 uses stored role `safety_officer` via `_current_user()`; no admin override or officer assignment exists. Retain JWT plus stored-user checks. |
| Separate decision persistence | `Event.decision_note`, `decided_by_id`, `decided_at` and status belong to the coordinator's request decision (SCRUM-32). They cannot be overwritten with a safety approval. No safety-decision fields/table exist. |
| Coordinator visibility | `GET /api/events/<id>/planning` already authorizes the assigned stored coordinator using `is_current_coordinator`. Its payload currently lacks safety information; an additive safety summary can expose the persisted decision. |
| Notification | Existing `Notification` rows and `GET /api/notifications/` supply in-app delivery. Follow existing decision/reservation patterns: decision plus notification in one commit, email task only after commit. No new channel/system. |
| Confirmation | No event-confirmation route or transition exists. `POST /<id>/decision` approves/rejects the original request, moving only submitted/under-review requests to `approved`/`rejected`. It is not event confirmation. `PATCH /<id>` rejects `status` as non-editable. `confirmed` appears in a supervised-event read allowlist and in venue-booking status, neither supplies a confirmation action. |
| Tests | Isolated Flask/JWT HTTP tests can mock the session while exercising real route/role behavior. `AppTestCase` uses real PostgreSQL with savepoints and outer rollback; local guards must precede its connection setup. |

**Implemented database change:** four nullable `Event` columns: `safety_decision` (text/status), `safety_decided_by_id` (User FK), `safety_comment` (text), `safety_decided_at` (naive UTC). This directly stores AC2's four values without a new table, history framework or reuse of another story's audit fields. They are non-editable through normal planning PATCH. RED changed no model or schema. GREEN adds the fields to `backend/app/models.py` and prepares `backend/db/safety_approval.sql`; the script has not been executed. The project owner must run it in the Supabase SQL editor before merging/deploying GREEN, per AGENTS.md. Until then shared schema validation and normal Event loads can fail. Adding columns to `events` does not require new-table entries in `test_role.sql`.

## Working assumptions (to confirm)

- **A1 / Q1 — Implemented additive API:** `POST /api/events/<id>/safety-checks/approve`, body `{comment?: string|null}`, HTTP 200 with a `safety_check` summary. Summary: `{decision: "approved", officer: {id, email}, comment: string|null, decided_at: ISO timestamp}`. Planning responses include that summary only when a decision is recorded, preserving the previous payload otherwise. These names are implementation choices, not additional Jira requirements. There is no new comment length limit.
- **A2 / Q2 — Persistence and notification:** store safety approval separately from coordinator request approval; decision time follows the repository's naive UTC audit convention. Notify the assigned coordinator via the existing in-app mechanism and existing post-commit email convention. No additional notification channel or recipient rule is proposed. Tests need only existing in-app delivery and no email on a failed save.
- **A3 / Q3 — Confirmed dependency (user, 28 Oct 2026):** SCRUM-93 owns the coordinator action that marks an event Confirmed. Reuse that action and its prerequisites once provided. Do not reinterpret request approval, make `status` a normal editable field, or invent a `/confirm` endpoint. TC-91-03 is incomplete and skipped with SCRUM-93 named; its existing PATCH refusal alone cannot establish AC3. SCRUM-93 must check persisted `Event.safety_decision == "approved"` before permitting confirmation.

## Seed data — SA-SEED

One ready event, "Safety review meeting", status `approved`, assigned coordinator, expected attendance 40, event/confirmed venue booking on 16 Jan 2030 17:00–19:00 Singapore time. No equipment requirement or equipment note (SCRUM-90's existing no-equipment assumption). Freeze Singapore-local now at 16:00 that day. The officer has stored role `safety_officer`; the supplied comment is "Exits and access routes checked.".

Unit records are in memory. Authorization changes the stored role while retaining a token claiming `safety_officer`, to ensure the stored role controls access. Local persistence tests use `make_*` helpers and unique test emails, assert only on their own event, and roll all rows back. They preserve an existing coordinator decision note and officer attribution. No shared seed data or schema is modified.

## AC1 — Approval and optional comment

**TC-91-01 · Approve with and without a comment**

- **Traces to:** AC1 · **Type:** Positive · **Preconditions:** SA-SEED, Safety Officer JWT.
- **Steps:** POST approval with the supplied comment, then against a reset fixture with no comment. In the existing queue UI, enter a comment and approve; repeat without entering a comment.
- **Expected result:** HTTP 200, approved safety summary with supplied comment or null, and one commit. UI posts for the selected event and displays successful approval feedback.
- **Automated:** `SafetyApprovalUnitTests.test_officer_can_approve_with_or_without_a_comment`; frontend `approves with or without a comment and shows success feedback`.

## AC2 — Persistence, visibility and notification

**TC-91-02 · Persist the four decision facts and notify the coordinator**

- **Traces to:** AC2 · **Type:** PostgreSQL integration · **Preconditions:** SA-SEED on a configured separate loopback PostgreSQL test database with the application's schema available; email task patched.
- **Steps:** Approve with a comment; expire ORM state and reload; GET planning and notifications as the assigned coordinator.
- **Expected result:** Persisted approval decision, officer ID, exact comment and UTC timestamp bounded by request start/end. Existing coordinator request-decision note/attribution remain intact. Coordinator planning displays all four facts; their notification list contains one approval message for this event.
- **Automated:** `SafetyApprovalLocalTests.test_persisted_decision_is_visible_to_the_notified_coordinator`.
- **Current limitation:** skipped before any connection because the configured test target is remote. The model and SQL update now exist, but actual PostgreSQL persistence/coordinator notification verification requires a separate local test database with the updated schema.

## AC3 — Confirmation restriction

**TC-91-03 · Require safety approval in the existing confirmation action**

- **Traces to:** AC3 · **Type:** Backend negative/positive; dependency blocked.
- **Preconditions:** SA-SEED; assigned coordinator; SCRUM-93's confirmation action with its existing requirements satisfied (not yet available).
- **Steps:** Before safety approval, attempt confirmation and check refusal/unchanged event; approve safety and repeat the same confirmation action.
- **Expected result:** Backend refuses before safety approval and permits confirmation afterward, subject to existing requirements. No parallel confirmation workflow.
- **Automated:** `SafetyApprovalUnitTests.test_confirmation_before_and_after_safety_approval` currently verifies only the existing backend planning PATCH refusal (`422`, status field error, unchanged event, no commit), then explicitly skips. There is no existing confirmation action to invoke for the required before/after check.
- **Blocker:** SCRUM-93 must supply the confirmation action/contract; then complete this same case against it and remove its dependency skip. A refusal that applies even after approval is not a passing AC3 test.

## AC4 — Authorization

**TC-91-04 · Deny other roles and unauthenticated access without changes**

- **Traces to:** AC4 · **Type:** Negative authorization · **Preconditions:** SA-SEED.
- **Steps:** POST without a JWT and as stored admin, coordinator, coordinator_lead, organiser, venue_staff, tech_staff and attendee. Authenticated tokens still claim the privileged role.
- **Expected result:** 401 without authentication; 403 for other stored roles; human error, no safety summary, unchanged event, no added decision/notification rows, no commit or queued email. Officer success is covered by TC-91-01.
- **Automated:** `SafetyApprovalUnitTests.test_other_roles_and_unauthenticated_callers_cannot_change_anything` (eight subtests).

## AC5 — Failed persistence and visible error

**TC-91-05 · Roll back approval and notification together and show the error**

- **Traces to:** AC5 · **Type:** PostgreSQL integration plus frontend error behavior.
- **Preconditions:** SA-SEED on separate loopback PostgreSQL; commit patched to perform a real flush then raise `SQLAlchemyError`; email task patched. Frontend API rejects with 503, a human error and `retryable: true`.
- **Steps:** Attempt approval. Reload the event and count its notifications after rollback. In the existing queue, submit a comment and inspect the failed response.
- **Expected result:** Backend 503 with human error and retryable flag, no successful safety payload or private exception text. Event exactly matches its pre-request stored state; no notification was partially committed; no email queued. UI shows the backend error, retains the event/comment and never displays approval success.
- **Automated:** `SafetyApprovalUnitTests.test_failed_save_returns_an_error_and_rolls_back_without_email` verifies the HTTP error/rollback/no-email branch without a database; `SafetyApprovalLocalTests.test_failed_commit_rolls_back_decision_and_notification_together` verifies real transaction atomicity when local PostgreSQL is available; frontend `shows the save error and keeps the event unapproved with its comment`.
- **Current limitation:** PostgreSQL rollback test skipped before any connection because the configured test target is remote. Mocked unit commit calls alone are not claimed as proof of database atomicity.

## Traceability matrix

| AC | Backend | Frontend | Current coverage limit |
|---|---|---|---|
| AC1 | TC-91-01 | TC-91-01 | GREEN in isolated HTTP and UI tests |
| AC2 | TC-91-02 | TC-91-01/02 combined success scenario | Coordinator UI GREEN; real persistence/notification verification pending local PostgreSQL |
| AC3 | TC-91-03 | — | BLOCKED by SCRUM-93; before/after check incomplete and explicitly skipped |
| AC4 | TC-91-04; positive TC-91-01 | — | GREEN; JWT/stored-role checks and no unauthorized writes |
| AC5 | TC-91-05 | TC-91-05 | HTTP failure/rollback branch and UI GREEN; real row rollback pending local PostgreSQL |

## Open questions for the customer

| ID | Question | Assumption/cases |
|---|---|---|
| Q1 | Confirm the proposed approval route and safety-summary names, reusing the queue and planning view. | A1; TC-91-01/02/04/05 |
| Q2 | Resolved for this increment: user authorized four nullable Event fields and the existing notification mechanism. | A2; TC-91-02/05 |
| Q3 | Resolved ownership: SCRUM-93 supplies event confirmation. Its operation/contract is still missing in this checkout. | A3; TC-91-03 remains BLOCKED |

## RED execution — 28 Oct 2026

Only focused SCRUM-91 tests were selected. No full backend/frontend suite was run.

Backend command, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_approval
```

**Final backend result:** 5 methods run; 0 passed, 2 failed methods (10 failing subtest assertions), 3 skipped, 0 errors; exit 1, 0.077 seconds. An initial fixture setup error from patching model query descriptors before the mock session was corrected; the final run has no setup/import/network-guard errors.

| Case | Actual result and reason |
|---|---|
| TC-91-01 | FAIL: both with-comment and omitted-comment POSTs return 404, expected 200; approval endpoint is missing. |
| TC-91-02 | SKIP: remote configured test database refused before connection; persistent decision/visibility not executed. |
| TC-91-03 | SKIP after existing PATCH refusal assertions pass: no confirmation action exists for the required before/after test. This is partial evidence, not an AC3 pass. |
| TC-91-04 | FAIL: all eight subtests return 404, expected 401/403; endpoint/JWT/role guard is missing. Later no-change assertions are not reached. |
| TC-91-05 | SKIP: remote configured test database refused before connection; real flush/rollback not executed. |

Frontend command, from `frontend/`:

```powershell
$env:DEBUG_PRINT_LIMIT='500'
npm.cmd test -- src/pages/SafetyCheckQueuePage.approval.test.jsx --reporter=dot
```

The sandboxed attempt failed before collection because esbuild could not read an ancestor directory/resolve the existing Vitest config. Retried the same focused command with expanded sandbox permissions; final results recorded below.

**Final frontend result:** Vitest 2.1.9; 1 file, 2 tests failed, 0 passed, 0 skipped; exit 1. Test time 172 ms; total duration 33.28 seconds. Both `approves with or without a comment and shows success feedback` and `shows the save error and keeps the event unapproved with its comment` load the existing queue/event successfully, then fail at the comment textbox lookup (`role="textbox"`, accessible name matching `/comment/i`). The approval controls are absent. POST, success-feedback and save-error assertions are not reached; no import, fixture or runtime-setup error occurred. The optional-comment loop stops at its first missing-control assertion.

**Combined method/test counts:** 7 defined; 0 passed, 4 failed, 3 skipped. Backend unittest reports 10 failed subtest assertions within its two failed methods, not ten separate test methods. No new method unexpectedly passed; the existing PATCH refusal within TC-91-03 did pass before its explicit dependency skip.

**Database safety:** configuration-only preflight reported a configured test URL that is not loopback PostgreSQL; no URL, credentials or remote host were printed. Both integration methods skipped before `AppTestCase.setUp()` could open a connection. Docker CLI inspection found no running Docker engine; no local database was created or accessed. Supabase and all remote/shared databases were **not accessed**. No DDL/schema builder/migration was executed.

**Historical RED scope:** only this document and the two SCRUM-91 test files changed during RED; no production or schema work occurred in that phase. Its verdict was BLOCKED on the then-unidentified confirmation dependency and unavailable local persistence verification. The later user authorization names SCRUM-93 and permits independent GREEN for AC1/2/4/5 below.

## Bounded GREEN implementation and verification — 28 Oct 2026

The user authorized AC1, AC2, AC4 and AC5 independently of SCRUM-93. This increment does not claim full SCRUM-91 acceptance.

- **AC1:** existing queue rows now offer Approve safety check and an optional comment. Success shows feedback; failure retains the event/comment. The backend reuses the queue's existing venue/equipment readiness code through `_safety_check_items`, and rechecks readiness on POST. Saved approvals leave the waiting queue on refresh. An event lock prevents repeat submissions from overwriting a recorded approval or creating duplicate notifications; an already-approved POST returns 409. No event lifecycle status changes.
- **AC2:** the four nullable safety fields are separate from SCRUM-32's request decision. The assigned coordinator's existing planning endpoint/page displays decision, officer, comment and timestamp. Existing `Notification` creation shares the approval commit, and the existing `_queue_email` helper queues email after commit; queue failure is non-fatal. As in equipment reservations, an event without an assigned coordinator has no notification recipient; this adds no coordinator-assignment prerequisite to the existing queue.
- **AC4:** JWT plus stored user/role checks; only `safety_officer` may approve. The endpoint follows 401 → 404 → 403 → invalid input → state refusal ordering. Comments accept text or null without a new length limit; blank text becomes null using the existing text-normalization convention.
- **AC5:** database errors roll back and return a human 503 error with `retryable: true`. The UI displays the backend error without reporting success. The added isolated TC-91-05 method verifies this branch when PostgreSQL is unavailable; it does not substitute for proof of persisted row rollback.
- **AC3:** preserved verbatim above and explicitly skipped. **BLOCKED by SCRUM-93**, which must check the persisted safety approval in its eventual confirmation operation. No confirmation endpoint, button, transition or speculative guard was added here.

Safety fields are audit records and remain non-editable through normal planning PATCH. No normal/restricted edit classification or other story's test-case document was changed. Existing planning payloads without a recorded safety decision retain their previous shape.

### Actual focused results

Backend command, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_approval tests.test_safety_check_queue_unit
```

**Actual:** exit 0; 10 methods run in 0.160 seconds; **7 passed, 0 failed, 3 skipped, 0 errors**. SCRUM-91 defines six methods: 3 pass (optional approval/notification creation, stored-role denials, failed-save error/rollback/no-email), 3 skip (AC3/SCRUM-93 and two local PostgreSQL integration methods). The four existing SCRUM-90 queue regression methods pass. The one additional SCRUM-91 method is justified by the unavailable PostgreSQL infrastructure: it exercises the real HTTP failure branch without claiming transaction durability. Existing naive-UTC `datetime.utcnow()` convention emits a deprecation warning; it does not fail the run.

Frontend command, from `frontend/`:

```powershell
$env:DEBUG_PRINT_LIMIT='600'
npm.cmd test -- src/pages/SafetyCheckQueuePage.approval.test.jsx src/pages/SafetyCheckQueuePage.test.jsx src/pages/EventPlanningPage.test.jsx --reporter=dot
```

Run with expanded sandbox permissions because the earlier RED run established the existing esbuild ancestor-directory access restriction. **Actual:** exit 0; Vitest 2.1.9; **24 passed, 0 failed, 0 skipped**, 3 files, total duration 5.46 seconds. SCRUM-91's two scenarios pass; the success scenario also verifies all four decision facts on the existing coordinator planning page. Existing queue tests: 4 pass. Existing planning-page tests: 18 pass. No existing regression test was changed.

Only directly affected files were tested; no full suite was run. Real persistence and flushed-transaction rollback are **not verified**: Docker engine is unavailable, and the configured test database is remote, so both local guards skipped before connection. No development database fallback or remote access was used. Supabase and all databases were not accessed during this increment.

### Schema rollout and review boundary

`backend/db/safety_approval.sql` adds only `safety_decision varchar(20)`, `safety_decided_by_id integer references users(id)`, `safety_comment text`, and `safety_decided_at timestamp` to `events`, within `begin`/`commit`, using `add column if not exists`. All are nullable with no defaults. No new table or change to `test_role.sql` is necessary.

**Before merge/deployment:** the project owner must run this SQL script in the Supabase SQL editor. It was prepared but not executed by the agent. Until applied, shared schema checks and Event queries can fail due to missing columns. Apply the schema first, then deploy the matching model/application; verify the two persistence tests against a separate loopback PostgreSQL test database with the updated schema before treating AC2/AC5's database behavior as proven.

**Exact files in this increment:**

- `backend/app/models.py`
- `backend/app/events/routes.py`
- `backend/db/safety_approval.sql`
- `backend/tests/test_safety_approval.py`
- `frontend/src/pages/SafetyCheckQueuePage.jsx`
- `frontend/src/pages/SafetyCheckQueuePage.approval.test.jsx`
- `frontend/src/pages/EventPlanningPage.jsx`
- `docs/test-cases/SCRUM-91-safety-approval.md`

**Known limits / risks:** AC3 is outstanding under SCRUM-93; real PostgreSQL verification is pending; schema rollout must be coordinated. No additional correctness problem was found in the focused checks. Existing publication/registration rules still use `approved` and were not changed. No SCRUM-92, SCRUM-93 implementation, new dashboard, queue-management features, dependencies, unrelated refactoring, commits, push, merge or PR.

**Verdict: READY FOR REVIEW for the bounded safety-approval increment**, with the schema and PostgreSQL verification limits above. **SCRUM-91 as a whole remains incomplete: AC3 is BLOCKED by SCRUM-93.** Stop after this authorized GREEN increment.
