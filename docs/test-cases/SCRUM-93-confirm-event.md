# SCRUM-93 — Coordinator Marks an Event Confirmed: Test Cases

**User story (verbatim):** As an Event Coordinator, I want to mark an event Confirmed once its arrangements are approved, so that the event can proceed to preparation

**Created:** 29 Oct 2026 (Singapore) · **Branch:** `feature/SCRUM-93-coordinator-confirm-event` · **Phase:** scoped GREEN and final frontend blocker fix complete · **Verdict:** READY FOR PR; focused tests, including local PostgreSQL persistence/rollback and the stale-confirmation regression, pass. Shared schema application remains a project-owner coordination step.
**Requirements source:** Jira wording in the user's SCRUM-93 brief; no Jira URL supplied.
**Automated tests:** [backend](../../backend/tests/test_event_confirmation.py), [frontend](../../frontend/src/pages/EventPlanningPage.confirmation.test.jsx).
**Related:** [SCRUM-85 multiple venues](SCRUM-85-several-venues-for-one-event.md), [SCRUM-44 equipment reservations](SCRUM-44-reserve-equipment.md), [SCRUM-90 safety queue](SCRUM-90-safety-check-queue.md), [SCRUM-91 safety approval](SCRUM-91-safety-approval.md). These documents are unchanged.

## Acceptance criteria

| ID | Criterion (verbatim) |
|---|---|
| AC1 | Only the event's coordinator can mark it Confirmed. Anyone else is denied and nothing changes. |
| AC2 | The event can be marked Confirmed only when its venue booking is Confirmed, its equipment is reserved (or none is required) and its safety check is Approved. Otherwise it is refused and the message lists what is missing. |
| AC3 | On success the status becomes Confirmed and who and when are recorded. |
| AC4 | If saving fails, the status is unchanged and an error is shown. |

## Original focused read-only scout findings (before GREEN)

Scouting inspected relevant code/tests/documentation only; it changed no files and accessed no database.

| Need | Existing implementation / smallest necessary addition |
|---|---|
| Authentication and assignment | JWT identities are string user IDs. `_current_user()` reloads the stored User; `events/permissions.py:is_current_coordinator` checks both stored role `coordinator` and current `event.coordinator_id`. Reuse these, without a role-claim or admin override. Follow 401 → 404 → 403 → validation → state refusal. |
| Current event status | `Event.status` is a string. Request approval (`POST /events/<id>/decision`) moves submitted/under-review requests to `approved`, and owns `decided_by_id`, `decided_at`, `decision_note`. There is no event-confirmation route. `confirmed` already appears in the supervised-events read allowlist. Normal planning PATCH rejects `status`. |
| Venue arrangements | SCRUM-85 permits multiple bookings; `Event.venue_id` is only the main venue, not readiness evidence. `_safety_check_items()` loads confirmed bookings and `_safety_schedule_covered()` checks continuous coverage of the current event's activity period. Different venues may cover touching phases. Setup/turnaround do not fill activity gaps; tentative holds do not count as confirmed. Reuse this interpretation without demanding identical periods or exactly one venue. |
| Equipment completeness | SCRUM-44's `resources/reservations.py` distinguishes `reserved` from `released`; the reservation page totals active quantities per requirement. `_safety_check_items()` already aggregates active quantities per event/requirement and checks every requirement, even if its arrangement status is still `requested`. An unprocessed organiser equipment note is not evidence that none is required. Do not substitute catalogue availability or an arrangement label for actual reservations. |
| Safety decision | SCRUM-91 persists `Event.safety_decision`, `safety_decided_by_id`, `safety_comment`, `safety_decided_at`. Confirmation must read `safety_decision == "approved"` on the backend. The safety queue excludes already approved safety checks, so queue membership cannot be used as the confirmation gate. |
| Missing prerequisites | `_safety_check_items()` returns a ready list, not separate reasons. GREEN needs a small way to expose venue/equipment shortfalls using the same rules, then add the independent persisted safety requirement. Reuse the schedule helper and active-quantity calculation; do not create a second, incompatible eligibility policy or change SCRUM-90/91 behavior. |
| Confirmation audit | No existing fields belong to event confirmation. Request decision, review start, assignment and safety timestamps each record a different action. Minimum GREEN schema addition: nullable `Event.confirmed_by_id` (User FK) and `Event.confirmed_at` (naive UTC). No history table or audit framework. |
| Existing coordinator UI | `GET /api/events/<id>/planning` and `EventPlanningPage.jsx` already restrict access to the current coordinator and display venue bookings and persisted safety approval. Add an action and success/error feedback there; no new page, navigation route or dashboard. |
| Transactions and tests | Existing routes catch `SQLAlchemyError`, roll back and return 503 with `retryable: true`. Isolated Flask/JWT tests can exercise real routes/helpers with mocked storage. `AppTestCase` supplies savepoint-backed transactions for a genuinely local PostgreSQL durability check. |

**Implemented GREEN scope:** one additive confirmation action, the three Jira prerequisites with missing-only feedback, two audit fields saved atomically with `status`, and an action on the existing planning page. `_safety_schedule_covered()` is reused directly; the existing equipment completeness check is extracted into `_equipment_fully_reserved()` and reused by the safety queue and confirmation with the same behavior. The safety approval operation, venue booking/reservation workflows and registration/publication rules are unchanged. Registration/publication currently use `approved`; reconciling any resulting visibility changes after confirmation remains outside this story's authorized scope and must be discussed with the team before altering those contracts.

## Working assumptions (to confirm)

Each assumption is linked to an open question; proposed API/field names are implementation choices, not additional Jira criteria.

- **A1 / Q1 — Implemented action/response:** `POST /api/events/<id>/confirm` with `{}`. HTTP 200 returns `{status: "confirmed", message: "Event confirmed.", confirmation: {coordinator: {id, email}, confirmed_at: ISO timestamp}}`. Missing prerequisites return 409 with a plain `error` and `missing`, an unordered list containing only applicable labels: `Confirmed venue booking`, `Reserved equipment`, `Approved safety check`. The error sentence includes those missing labels. Failed saves return 503 with `retryable: true` and no success summary. UI offers “Mark event Confirmed”, displays the backend error, keeps the previous event status and permits another attempt. There is no readiness payload requirement on the existing planning GET.
- **A2 / Q2 — Existing prerequisite meaning:** reuse SCRUM-90/44's current schedule coverage, active quantities and no-equipment interpretation. No structured requirements plus a blank/null organiser note means none required; a nonblank unprocessed note remains missing equipment. Required venue identities are not separately modeled, so do not invent a requirement that every historical/pending booking be confirmed. Confirmation starts from `approved`, the existing booking/reservation planning stage (`CONFIRMABLE_EVENT_STATUS`); other states, including repeat confirmation, return 409 rather than creating unrelated transitions or overwriting audit values. This source-state choice is an implementation assumption, not an additional agreed Jira AC; no lifecycle test matrix was added.
- **A3 / Q3 — Separate audit record:** the GREEN brief explicitly authorized nullable `confirmed_by_id` and `confirmed_at`, following existing naive UTC conventions. They remain non-editable through normal planning PATCH. Preserve the earlier request decision and safety audit fields. Save status and these two fields in one transaction; record no new notifications or audit history.

## Seed data — CF-SEED

Isolated records are defined in the new backend module; no unrelated story test helpers or shared seed data are imported or changed.

- **C1:** currently assigned coordinator (ID 2); **C2:** unrelated coordinator (ID 3); **O1:** event organiser (ID 4). Tokens claim `coordinator`; a changed stored role on C1 must still deny access.
- **E1:** “Confirmation workshop”, `approved`, assigned to C1, 16 Jan 2030 17:00–19:00 Singapore time. Earlier request-decision note/attribution are populated. Persisted safety decision is `approved`, with separate officer/time. Confirmation audit values start null.
- **B1/B2:** confirmed venue 10 at 17:00–18:00 and venue 11 at 18:00–19:00. Main venue remains 10. Together the different venues cover the event continuously.
- **R1/R2:** two microphones and one projector required; arrangement labels remain `requested`. Two active one-unit microphone reservations and one active projector reservation fully satisfy them.
- **Variants:** no equipment/note; one-minute booking gap; one microphone reservation released (projector still fully reserved); missing persisted safety decision; all three prerequisites missing (first venue tentative, no reservations, no safety decision); nonblank unprocessed equipment note with no structured requirements.

The prerequisite test also invokes actual `_safety_check_items()` to validate each venue/equipment fixture before invoking confirmation. Its local query fixture evaluates production column predicates and fails on unsupported shapes; it does not supply a precomputed readiness answer or mock an eligibility helper. Database/network connections are guarded in isolated tests.

The local test uses `AppTestCase`, `make_user`, `make_venue`, `make_event` and `auth_headers`; a confirmed booking and no-equipment event avoid unrelated reservation setup. It inspects only its own event, preserves every field on rollback and rolls all rows back. It checks an explicitly configured loopback PostgreSQL `TEST_DATABASE_URL` before app creation, refuses the configured development target and never falls back to `DATABASE_URL`. Importing this module suppresses `.env` loading; provide a separate local test URL through the process environment when running it alone. Tests invoke no database builder or DDL. GREEN verification separately provisioned a throwaway local container with the existing CI builder before tests, then removed it.

The frontend uses a coordinator planning response with a confirmed venue booking and approved safety summary. Its event-status assertions inspect the labelled event field, so an already confirmed venue cannot masquerade as event confirmation. API failures are server responses; React does not reimplement readiness.

## AC1 — Coordinator authorization

**TC-93-01 · Only the currently assigned stored coordinator can confirm**

- **Traces to:** AC1 · **Type:** Negative authorization, supported by positive TC-93-03.
- **Preconditions:** CF-SEED, otherwise ready event.
- **Steps:** POST without authentication; as C2; as O1; and as assigned C1 after the stored role changes to admin while the token still claims coordinator. Confirm as valid C1 in TC-93-03.
- **Expected result:** 401 without authentication, otherwise 403 for unauthorized callers; human refusal without private event details or confirmation summary. Every fixture field, including status/audit information, remains unchanged and no save occurs. Valid C1 succeeds.
- **Automated:** `EventConfirmationUnitTests.test_only_the_current_stored_coordinator_can_confirm`; positive `test_confirmation_sets_status_and_separate_coordinator_and_utc_timestamp`.

## AC2 — Required arrangements and missing-only feedback

**TC-93-02 · Confirm only with confirmed venue coverage, complete reservations or none required, and persisted safety approval**

- **Traces to:** AC2; also supplies SCRUM-91 AC3's backend gate · **Type:** Positive/negative business rule · **Depends on:** A1/A2.
- **Preconditions:** CF-SEED; valid C1 JWT.
- **Steps:** POST for the seven small scenarios below. Reset fixtures between scenarios; no exhaustive permutations.

| Scenario | Expected |
|---|---|
| Ready multi-venue phases, split active equipment quantities, approved safety | 200; event confirmed, one commit |
| No structured equipment requirements and no note; other prerequisites ready | 200; event confirmed, one commit |
| One-minute uncovered venue interval | 409; only `Confirmed venue booking` missing |
| One released microphone reservation leaves a shortfall; projector complete | 409; only `Reserved equipment` missing |
| Persisted safety decision absent; venue/equipment ready | 409; only `Approved safety check` missing |
| Tentative first venue phase, no active equipment reservations, no safety decision | 409; all three missing labels |
| Nonblank organiser equipment note, no structured requirements/reservations | 409; only `Reserved equipment` missing |

- **Expected result:** Each refusal identifies exactly the missing prerequisites in both list and message, changes no fixture information and makes no commit. A frontend-enabled action alone cannot satisfy the backend safety restriction.
- **Automated:** `EventConfirmationUnitTests.test_prerequisites_use_current_bookings_active_quantities_and_persisted_safety` (seven subtests).

## AC3 — Successful confirmation and attribution

**TC-93-03 · Save Confirmed with who and when, separately from earlier decisions**

- **Traces to:** AC3; positive AC1/AC2 · **Type:** HTTP unit + local PostgreSQL persistence · **Depends on:** A1/A3.
- **Preconditions:** Ready CF-SEED, valid C1; separate loopback test database with GREEN schema for the integration part.
- **Steps:** POST confirmation. Check mapped confirmation fields, actual event values, response and one commit. In the local test, retry after the failed save from TC-93-04, expire ORM state and reload the event.
- **Expected result:** `status == "confirmed"`, confirmer ID equals C1, naive UTC timestamp between request start/end, matching response attribution/time and a human success message. Original decision/safety fields and every other event field remain unchanged. The local reload must show persisted status/metadata, not cached values.
- **Automated:** `EventConfirmationUnitTests.test_confirmation_sets_status_and_separate_coordinator_and_utc_timestamp`; successful-retry half of `EventConfirmationLocalTests.test_flushed_failure_preserves_all_event_fields_and_retry_persists_confirmation`.

## AC4 — Saving failure

**TC-93-04 · Roll back status and partial confirmation metadata and show an error**

- **Traces to:** AC4 · **Type:** HTTP failure + real PostgreSQL transaction · **Depends on:** A1/A3.
- **Preconditions:** Ready event; session commit raises `SQLAlchemyError`. Integration requires the separate loopback test database with GREEN schema.
- **Steps:** POST with commit failure. In the local test, assert that confirmation status/metadata were assigned, flush SQL, then fail the commit; expire/reload and compare every event field with the pre-request snapshot.
- **Expected result:** 503, useful error, `retryable: true`, rollback, no private exception text or false success summary. Reloaded event retains its original status and null confirmation metadata with no partial changes. A subsequent successful retry is TC-93-03.
- **Automated:** `EventConfirmationUnitTests.test_failed_commit_returns_retryable_error_and_rolls_back`; failure half of `EventConfirmationLocalTests.test_flushed_failure_preserves_all_event_fields_and_retry_persists_confirmation`.
- **GREEN evidence:** the local test passed with the GREEN schema on isolated PostgreSQL 17. It assigned all three confirmation values, flushed SQL, forced commit failure, expired/reloaded and verified every event field matched the original snapshot. A successful retry then persisted status, coordinator ID and timestamp. The mocked HTTP test also passed; it is not being used as a substitute for real rollback evidence.

## Frontend — existing coordinator planning page

**TC-93-05 · Initiate confirmation and display successful event status**

- **Traces to:** AC1, AC3 · **Type:** Positive interaction · **Preconditions:** Successful coordinator-only planning response, mocked axios client, existing page in MemoryRouter.
- **Steps:** Load event, activate confirmation, receive proposed successful response.
- **Expected result:** POST `/events/1/confirm` with `{}`, visible success message and event status Confirmed. The venue's existing Confirmed label is not event-success evidence.
- **Automated:** `lets the assigned coordinator confirm and shows success with the confirmed status`.

**TC-93-06 · Explain missing prerequisites/save failure without false confirmation**

- **Traces to:** AC2, AC4 · **Type:** Negative interaction, parameterized 409/503 · **Preconditions:** Same planning page; server missing-safety or retryable-save response.
- **Steps:** Activate confirmation; inspect failure; attempt again with a successful response after the underlying problem is resolved.
- **Expected result:** Backend error appears in an alert; event remains Approved and no success message appears. Another attempt is available and can update event status after success.
- **Automated:** `shows the %s refusal without falsely confirming and permits another attempt` (409 and 503).

**TC-93-07 · Ignore a confirmation response after moving to another event**

- **Traces to:** AC3 · **Type:** Frontend regression · **Preconditions:** Existing planning page in MemoryRouter; Event A confirmation POST remains pending.
- **Steps:** Start confirming A, navigate within the same mounted route to Event B, wait for B's planning information, then resolve A's earlier POST successfully.
- **Expected result:** B stays Approved, with no confirmation success/error feedback from A. B's confirmation button is enabled; only A's confirmation POST was sent.
- **Automated:** `ignores a confirmation response after navigating to another event` in the existing SCRUM-93 frontend test file. No additional race-condition test matrix was added.

## Traceability matrix

| AC | Cases | Current execution |
|---|---|---|
| AC1 | TC-93-01; positive TC-93-03/05 | GREEN: stored-role/current-assignment denial and authorized success |
| AC2 | TC-93-02/06 | GREEN: seven backend scenarios and missing-only UI feedback |
| AC3 | TC-93-03/05/07 | GREEN: HTTP/UI plus actual PostgreSQL reload; stale frontend response ignored |
| AC4 | TC-93-04/06 | GREEN: HTTP/UI plus actual flushed transaction rollback |
| SCRUM-91 AC3 dependency | TC-93-02 approved vs absent persisted safety; TC-93-03 | GREEN backend gate; no SCRUM-91 files changed |

## Open questions for the customer

| ID | Question | Affects |
|---|---|---|
| Q1 | GREEN authorization accepted implementing the proposed action and existing RED contract. Customer-facing wording can be adjusted if requested. | A1; TC-93-01..06 |
| Q2 | Keep SCRUM-90/44's existing interpretation of venue coverage and no-equipment evidence? If particular additional venues are mandatory, how are those requirements recorded? Confirm the `approved` source-stage assumption; no further lifecycle transitions are implemented. | A2; TC-93-02 |
| Q3 | Resolved by GREEN brief: use `confirmed_by_id`, `confirmed_at` and repository audit conventions. | A3; TC-93-03/04 |

## RED execution — 29 Oct 2026 (Singapore)

Only SCRUM-93's focused tests were selected. No full backend/frontend suite was run.

Backend command, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_event_confirmation
```

**Backend result:** four unit methods run, zero passed, four failed methods (13 failing assertions including subtests), zero errors. One local class setup skipped before app creation/connection because a separate loopback PostgreSQL test URL was not configured for this run; its single integration method was not run. Unittest reports `Ran 4 tests` and `FAILED (failures=13, skipped=1)`; the skip counts a class setup, not a fifth executed method. Final run: 0.126 seconds, exit 1.

| Case | Actual result |
|---|---|
| TC-93-01 | Four subtests fail: 404 instead of 401/403; confirmation action and its authorization are absent. Later no-change assertions are not reached. |
| TC-93-02 | Seven subtests fail: 404 instead of 200/409. All existing readiness fixture-validation assertions pass before the missing-action failures; these are not separate passing tests. |
| TC-93-03 | Unit method fails at 404 instead of 200; audit mapping/attribution assertions not yet reached. Integration method not run. |
| TC-93-04 | Unit method fails at 404 instead of 503; commit/rollback assertions not reached. Integration method not run. |

Frontend command, from `frontend/`:

```powershell
$env:DEBUG_PRINT_LIMIT='500'
npm.cmd test -- src/pages/EventPlanningPage.confirmation.test.jsx --reporter=dot
```

The first sandboxed attempt failed before collection because esbuild could not read an ancestor directory/resolve the existing Vitest configuration. The focused command ran with expanded sandbox access afterward. Final execution results are recorded below; startup failure is not counted as RED evidence.

**Frontend result:** Vitest 2.1.9; one file, three tests failed, zero passed, zero skipped; exit 1. Final run: 382 ms test time, 56.48 seconds total. Each loads the existing planning page/event and fails looking for its confirmation button. POST/success/error/retry assertions are not reached; there are no fixture/import/runtime setup errors. The parameterized refusal case generates two tests.

**Combined:** seven executed unit/UI tests failed, zero passed; one local class setup skipped (one additional integration method defined but not executed). Failures are genuine missing SCRUM-93 route/control failures, not database or fixture failures. Existing helper fixture checks pass; no passing new test is being relabeled as RED.

## GREEN execution — 29 Oct 2026 (Singapore)

Existing RED assertions and TC IDs were retained. The two test files received only stale RED/proposed-contract comment updates; no tests, fixtures or assertions were weakened or added. No full suite was run.

**Isolated backend command**, from `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_event_confirmation.EventConfirmationUnitTests tests.test_safety_check_queue_unit
```

**Result:** 8 passed, 0 failed, 0 skipped, 0 errors; 0.185 seconds, exit 0. Four are SCRUM-93 methods (including all authorization/prerequisite subtests); four are the existing safety-queue unit regressions. The shared equipment completeness extraction preserves their results.

**Local PostgreSQL setup:** Docker PostgreSQL 17, unique `connectsphere-scrum93-*` container, `connectsphere_scrum93_test` database, randomly generated ephemeral owner/test passwords, published only on `127.0.0.1` with an automatically allocated port (49982 for this execution). No developer credentials were embedded in source. Both URLs were explicitly constructed for that loopback container; the CI builder independently rejects nonlocal hosts and the confirmation test guards its URL before opening a connection. The ordinary app URL in this process targeted an unused local development database, never used for tests. No `.env` was edited.

```powershell
# OWNER_DATABASE_URL and TEST_ROLE_PASSWORD target only the new local container.
.\.venv\Scripts\python.exe -B ci/build_test_database.py
# TEST_DATABASE_URL uses its restricted connectsphere_test role, as CI does.
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_event_confirmation tests.test_safety_check_queue_local tests.test_safety_approval.SafetyApprovalLocalTests tests.test_event_planning_info.PlanningFieldsTests.test_every_planning_field_is_always_present tests.test_event_planning_info.ViewPlanningInformationTests.test_assigned_coordinator_sees_the_events_planning_information
```

The CI helper built 15 tables from current models with RLS and restricted-role policies in the new container only. **Result: 10 passed, 0 failed, 0 skipped, 0 errors; 1.048 seconds, exit 0.** This includes all five SCRUM-93 methods (four isolated plus one real PostgreSQL integration method), the current-schedule/multi-venue/equipment SQL regression, both existing safety approval persistence/rollback tests, and two planning-view regressions. Six methods used actual local PostgreSQL. The container was removed in `finally` after execution; all row tests used `AppTestCase` rollback isolation. The shared-database SQL scripts were not executed.

**Frontend command**, from `frontend/`, with expanded sandbox access required by the existing esbuild setup:

```powershell
npm.cmd test -- src/pages/EventPlanningPage.confirmation.test.jsx src/pages/EventPlanningPage.test.jsx --reporter=dot
```

**Result:** Vitest 2.1.9; 2 files, 21 passed, 0 failed, 0 skipped; 54.65 seconds total, exit 0. SCRUM-93's 3 tests pass (success, missing prerequisite, save failure/retry), along with all 18 existing planning-page tests.

**Counts without double-counting:** SCRUM-93 has 5 backend + 3 frontend tests passed, none failed/skipped. Across the focused regressions, 14 unique backend methods and 21 frontend tests passed, none failed/skipped; four SCRUM-93 unit methods ran in both backend commands. Python emitted existing-style naive-UTC deprecation and test JWT key-length warnings; these were not failures and no unrelated configuration changes were made.

**SCRUM-91 AC3 verification:** TC-93-02 now exercises the real confirmation endpoint with otherwise ready arrangements: absent persisted safety approval produces 409 and no change/commit; approved persisted safety permits confirmation. This enforces the restriction on the backend, independent of the button. Local SCRUM-93 persistence and existing SCRUM-91 approval persistence/rollback also pass. SCRUM-91's older dependency-skipped method was neither changed nor selected; this is explicit SCRUM-93 evidence, not a claim that the old skipped method was completed.

## Dependencies, schema and stopping point

- **Prepared schema:** [backend/db/event_confirmation.sql](../../backend/db/event_confirmation.sql) adds only nullable `confirmed_by_id` (User FK) and `confirmed_at` (naive UTC timestamp), matching `Event`. It is idempotent and transaction-wrapped. The fields are audit-only and absent from both editable planning field lists; normal PATCH therefore refuses them under its existing validation. No new table/history/notification infrastructure exists.
- **Required shared coordination:** before merging/deploying these model changes, the project owner must run `backend/db/event_confirmation.sql` in the Supabase SQL editor. Ensure SCRUM-91's prior `backend/db/safety_approval.sql` has already been applied. Neither script was executed against Supabase here, and live schema state was not inspected. Adding columns to existing `events` does not require rerunning `test_role.sql`. Until schema application, model/schema checks and Event loads against the shared project can fail.
- **Separate integration coordination — SCRUM-45/74 owners:** attendee registration/publication and related workflows still use their existing `approved` rules. After transition to `confirmed`, the event is excluded from the public catalogue, attendee detail requests return 404 (including for registered attendees), new registrations are refused, and registration settings become unavailable. These are definite effects of the existing filters. Coordinate the intended policy with SCRUM-45/74 and related functionality owners; those workflows were explicitly excluded from this frontend fix and remain unchanged. Required venue identities are still not modeled; confirmation follows established continuous coverage semantics.
- **Exact changed files:** `backend/app/models.py` (two audit columns), `backend/app/events/routes.py` (confirmation operation and minimal shared equipment rule), `backend/db/event_confirmation.sql` (later owner-run schema addition), `frontend/src/pages/EventPlanningPage.jsx` (button/feedback/status update), the two existing SCRUM-93 test files (comments only during GREEN), and this document (GREEN evidence/coordination). No other Scrum document or test file changed.
- **Scope confirmation:** original Jira user story and all four ACs remain verbatim, with original TC IDs/traceability. No Supabase or remote/shared database access; no ordinary development database changes; no notifications, new dependencies, unrelated safety/venue/equipment workflows or registration/publication changes. No commits, pushes or PRs.

## Final review blocker fix — 29 Oct 2026 (Singapore)

Only `frontend/src/pages/EventPlanningPage.jsx`, its existing SCRUM-93 confirmation test file and this document changed in this follow-up. Each confirmation now has a request identity associated with its event ID. Loading another event or leaving the page invalidates that identity; success, error and pending-state completion updates are ignored when the identity is stale. The next event starts with its own available confirmation action. This follows the repository's existing ref-based request-identity approach without new shared hooks, services or test infrastructure.

**RED evidence:** after adding only TC-93-07, the focused confirmation file ran 4 tests: 3 passed, 1 failed, 0 skipped. The regression reached Event B, resolved Event A's pending POST, then failed because B displayed `Confirmed` instead of `Approved`. Exit 1; 1.66 seconds total. This demonstrated the actual blocker before changing production code.

**GREEN command**, from `frontend/`, with expanded sandbox access required by the existing esbuild setup:

```powershell
npm.cmd test -- src/pages/EventPlanningPage.confirmation.test.jsx src/pages/EventPlanningPage.test.jsx --reporter=dot
```

**Result:** Vitest 2.1.9; 2 files, 22 passed, 0 failed, 0 skipped; 2.92 seconds total, exit 0. All 4 SCRUM-93 confirmation tests (including the single new navigation regression) and all 18 existing planning-page regressions passed. Existing meaningful assertions were retained. No backend tests were rerun for this frontend-only follow-up; the user's separately reported full backend result is 1,145 run, 0 failures/errors, 7 skipped.

Original Jira user story and all four ACs remain verbatim. No backend confirmation logic, models, schema scripts, registration/publication workflows or other story files changed in this follow-up. No Supabase access, database operations, dependency installation, commits, pushes or PR creation occurred.

**Verdict: READY FOR PR.** The single blocking frontend issue is fixed and verified. Shared schema application remains the project owner's coordinated step; the separately documented SCRUM-45/74 integration policy concern remains outside this fix.
