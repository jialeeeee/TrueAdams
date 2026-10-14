# SCRUM-55 — Review a Submitted Event Request: Audit, RED and GREEN Verification

**User story:** As an Event Coordinator, I want to view the full details of a submitted event request so that I can check whether I have enough information to continue planning the event.

**Created:** 14 Oct 2026 · **RED verification completed:** 14 Oct 2026, with explicit user authorization. **Observed baseline:** 3 passed, 9 expected RED failures across 12 SCRUM-55 test instances. See section D for isolation, exact commands, timings and results.

**Current status — GREEN verified, 14 Oct 2026:** all 12 original selected SCRUM-55 instances pass across the targeted runs in section G. Sections A–F retain the historical audit and RED verification; section G records the authorized implementation, fixture maintenance, selector correction and regression limits.

**Focused post-GREEN review completed, 14 Oct 2026:** 31 selected instances passed (9 backend, 22 frontend); no production defect or production change during this review. Section H records the exact selection, added regression assertions and remaining verification limits.

**Story:** SCRUM-55, addressing SCRUM-31a (no Jira URL supplied).
**Related:** [SCRUM-31](SCRUM-31-event-clarification.md), [SCRUM-32](SCRUM-32-approve-reject-event-request.md), [SCRUM-34](SCRUM-34-view-event-planning-info.md), [SCRUM-62](SCRUM-62-managed-events-list.md).
**New automation:** [backend unit tests](../../backend/tests/test_review_requests_unit.py), [list component tests](../../frontend/src/pages/ReviewRequestsPage.test.jsx), additions to [detail component tests](../../frontend/src/pages/ReviewRequestPage.test.jsx).

## Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | Coordinator sees requests submitted for review; drafts are excluded. |
| AC2 | Each row shows event name, organiser, proposed date, submission date/time and status. |
| AC3 | No eligible requests produces an empty-state message. |
| AC4 | Opening the selected request shows its name, purpose, description, proposed date/start/end, expected attendance, venue/accessibility/equipment requirements and registration requirements. |
| AC5 | Existing clarification messages for that request are visible. |
| AC6 | Only Event Coordinators can access this view. |
| AC7 | List/detail load failures have explanatory feedback and a working retry. |

## Working assumptions and boundaries

- **A1 / Q1 — Statuses, confirmed by the user on 14 Oct 2026:** the separate SCRUM-55 review list includes only `submitted` and `under_review`. Draft, approved, rejected and cancelled requests are excluded. New fixtures cover both eligible statuses and all four excluded existing statuses. Preserve the managed-events list's all-status behavior and existing approval/rejection eligibility (only `submitted`); list eligibility does not change decision eligibility.
- **A2 / Q2 — Visibility, preserved by user instruction:** preserve current assigned-coordinator access, including reading the current stored role. Do not broaden to all coordinators or add an admin override. Unassigned and other coordinators' events remain excluded. Existing review details stay viewable in any status, per SCRUM-32 A7; do not narrow that shared endpoint as part of list filtering.
- **A3 / Q3 — Additive list contract, proposed for GREEN review:** `GET /api/events/review-requests` returns `{requests: [summary], message: string|null}`. A summary is `{id, title, organiser: {id, email}, start_time, submitted_at, status}`. The frontend route is `/events/review-requests`; each row opens existing `/events/<id>/review`. No existing API contract is changed. These names are test-design proposals, not implemented endpoints or confirmed customer decisions. Using a separate list preserves SCRUM-62's explicitly all-status `/managed` contract and the generic public `/events/` stub.
- **A4 / Q4 — Field meaning:** organiser is identified by existing `User.email` (there is no name column). Proposed date comes from naive Singapore-local `start_time`; no invented date column. Submission timestamps are naive UTC and use the existing `formatSavedAt` presentation. Registration requirements mean existing submitted `registration_required`; later registration window/capacity fields are a separate workflow. NULL displays the existing `Not provided`; recorded false displays `No`.
- **A5 / Q5 — Clarifications:** minimally read existing `GET /events/<id>/clarifications` from the review screen and display its history there. Do not add creation/reply features or narrow the organiser's legitimate access to the existing thread endpoint. Inline history is a proposed way to satisfy visibility in the review workflow. The standalone clarification page already exists, but review has no history or link to it.

## Seed data — RV-SEED (in memory only)

No database seed script, persisted rows, credentials or network services are used.

| Ref | Data | Purpose |
|---|---|---|
| U1 | id 1, organiser, `owner@test.invalid` | Organiser identity |
| U2 | id 2, coordinator | Current reviewer; current role changed in auth subcases |
| U3 | id 3, coordinator | Another reviewer |
| R7 | submitted, U2, organiser U1 | Eligible request, proposed 12 Dec 2026 17:00 Singapore, submitted 14 Oct 2026 01:00 UTC |
| R8 | draft, U2 | Draft exclusion |
| R9 | submitted, U3 | Assignment isolation |
| R10 | submitted, no coordinator | Unassigned exclusion |
| R11 | under_review, U2 | Second eligible status |
| R12/R13/R14 | approved/rejected/cancelled, U2 | Exclude all remaining existing statuses from this review queue |
| C20/C21 | Questions attached to R7/R9 | Cross-event history isolation |

Frontend fixtures use a submitted id 8 workshop to verify selection without hardcoding id 7, plus an under_review id 11 request to verify its visible status and review link. Detail cases reuse the existing full festival fixture, with recorded accessibility / NULL and registration true / false variants. History navigation loads populated threads for both event ids 7 and 8.

## A. Implementation audit

Implementation findings below come from source inspection. Only the SCRUM-55 tests were subsequently executed; see section D. Unrelated existing test outcomes were not re-verified.

| AC | Assessment | Relevant source and actual behavior | Remaining gap |
|---|---|---|---|
| AC1 | Partial | `backend/app/events/routes.py:list_managed` checks current coordinator role and filters `coordinator_id`, then returns **all statuses**. `ManagedEventsPage.jsx` calls `/events/managed` and opens planning. `list_my_requests` and `list_mine` are organiser-only workflows. `list_events` is a public empty-array stub; `EventsPage.jsx` renders titles only. | No separate coordinator queue restricted to the confirmed submitted/under_review statuses. Preserve SCRUM-62's all-status list. |
| AC2 | Partial | `list_managed` sends id/title/start_time/status; `ManagedEventsPage` displays these. `Event` already has organiser_id/submitted_at; `User` has email. | Review-list organiser and submission timestamp, plus a dedicated list rendering all five facts. |
| AC3 | Partial | `/managed` supplies an empty message only when no events are assigned. Organiser lists have their own empty messages. | A coordinator with only ineligible requests still needs a review-queue empty state. |
| AC4 | Implemented | `review_request` → `_assigned_request` → `_request_payload` serializes all `DRAFT_FIELDS` and preserves null/false. `ReviewRequestPage` renders title plus its `DETAILS` definition list. Start/end include the proposed date, shown without timezone conversion; `display()` distinguishes absence from false. The planning screen also displays these fields. | Discovery/opening from the missing review list; complete component assertions on the actual review screen. No new fields/schema needed. |
| AC5 | Partial | `EventClarification` already exists. `list_clarifications` authenticates, loads the event, calls `can_view_clarifications`, joins senders, filters `event_id`, and returns oldest-first history. `ClarificationPage` renders that history in a separate workflow. | `ReviewRequestPage` only calls `/review`, has no clarification history or navigation to it. Cross-event history filtering lacks a populated-two-event test. |
| AC6 | Partial overall; existing detail guard implemented | Login issues a string user-id JWT. `api/client.js` adds the session token. `_current_user` reloads `User`; `_assigned_request` checks user, event, then `is_current_coordinator`. `permissions.py` requires both stored coordinator role and matching coordinator_id. App routes/nav are not role-gated; data protection is enforced by the API. | The new queue endpoint needs its own JWT/current-role guard. Existing review/history permissions should be reused, not redesigned; no new frontend token-role trust. |
| AC7 | Partial | `review_request` catches SQLAlchemyError, rolls back and returns 503/retryable. `ReviewRequestPage.load` uses server/fallback text and its Retry button reloads details. Managed-list and standalone clarification pages have similar recovery flows. | Equivalent feedback/recovery for the missing review list. No additional duplicate detail retry test is necessary. |

SCRUM-28's submission path validates the draft, assigns the lowest-id current coordinator, and records `submitted_at` and `submitted` together. Its existing unit test directly opens `/review` as the chosen coordinator and rejects organiser/admin/another coordinator. Reuse that submission and assignment behavior without changes.

## B. Test coverage matrix / traceability matrix

Paths below are relative to `backend/tests/` or `frontend/src/pages/`. Existing coverage is recorded from assertions, not inferred from test names alone.

| AC | Existing coverage | Gap and new cases | New classification / necessity |
|---|---|---|---|
| AC1 | `test_managed_events.py:ManagedListTests.test_coordinator_sees_only_the_events_assigned_to_them` covers assignment isolation, intentionally including approved/cancelled/under_review. Organiser-only list tests do not cover a coordinator queue. | TC-55-01, 06; submitted/under_review inclusion, draft/approved/rejected/cancelled exclusion, current-assignment boundary, queue routing. | Backend unit for eligibility; frontend component for display/opening. Both boundaries need coverage; neither repeats the managed-list requirement. |
| AC2 | `ManagedEventsPage.test.jsx:lists each event with its name, proposed date and status`; backend `test_each_event_shows_its_name_proposed_date_and_status`. | TC-55-01, 06 add organiser/submission timestamp and prove the separate queue contract. | Backend unit serialization + frontend visible fields, combined with list/selection cases. |
| AC3 | `test_managed_events.py:EmptyStateTests.test_coordinator_with_no_events_gets_an_empty_state_message`; managed-page empty test. | TC-55-02, 07 cover no eligible requests while assigned draft/approved/rejected/cancelled rows remain. | Backend unit for eligibility-derived emptiness; component for the user-visible message. |
| AC4 | `test_event_decisions.py:WhoAndWhenTests.test_coordinator_opens_the_full_request_to_review_it` asserts every request field and selected id; `ReviewRequestPage.test.jsx:shows the request's details and status` asserts only status/purpose/venue. Planning tests cover another screen. | TC-55-06 opens selected row; TC-55-09 checks all review fields, dates and null/false display. | Frontend component only; no duplicate backend full-detail test. |
| AC5 | `test_event_clarifications.py:SendQuestionTests.test_questions_are_listed_for_the_coordinator_and_the_organiser`, `test_unrelated_users_cannot_view_the_questions`; `ClarificationPage.test.jsx:loads the event and its earlier questions`; SCRUM-27 history-access tests. | TC-55-05 uses two events' populated histories; TC-55-10 displays history while reviewing and changes selection without retaining the other thread. | Backend unit for filtering; component for review-history visibility. Existing read-only API is reused. |
| AC6 | `test_authorization_unit.py:EventPermissionTests.test_assigned_identity_alone_does_not_grant_coordinator_privileges`; `test_authorization_http_unit.py:test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them` and `test_unrelated_organiser_and_attendee_direct_reads_are_denied` exercise `/review`. `test_event_submission.py:SubmissionUnitTests.test_submission_assigns_reviewer_and_preserves_access_boundaries` also checks chosen reviewer vs admin/owner/other coordinator. Existing `test_event_decisions.py` checks review sessions. | TC-55-03 protects the **new** list endpoint with missing/deleted sessions and each non-coordinator role using a reused token with a forged coordinator claim. TC-55-01 preserves assignment scope. | Backend unit only. Do not duplicate the existing detail-authorization matrix or implement a new permission model. |
| AC7 | `ReviewRequestPage.test.jsx:shows a retryable error when the request cannot be loaded` verifies error, Retry, and successful recovery. Managed and clarification pages have their own retry tests; `EventPlanningPage.test.jsx` also covers planning retries. | TC-55-04 backend outage/recovery; TC-55-08 list server/network failure and successful button retry. | Backend unit + frontend component for the missing list; reuse existing detail-retry coverage. |

No new integration tests are necessary. Mock-backed cases cannot prove PostgreSQL query execution, RLS, joins, or transaction durability; those claims are outside this audit's evidence. Existing persisted tests remain untouched and unexecuted.

## C. RED-phase changes and test cases

Files changed/created:

1. **Created** `backend/tests/test_review_requests_unit.py`: five isolated unittest methods, no `AppTestCase`, factory initialization or engine. Bare Flask app registers the actual events blueprint and uses real JWT validation; only persistence is mocked. Engine and socket guards reject accidental external access. `_ReadQuery` follows SCRUM-28's small fake-query pattern and evaluates production predicates rather than prefiltering results for the route.
2. **Created** `frontend/src/pages/ReviewRequestsPage.test.jsx`: three component test declarations (server/network retry variants). Renders existing `App` inside `MemoryRouter`; absent route wiring causes behavioral assertion failure, not a nonexistent component import. All API reads are mocked.
3. **Modified** `frontend/src/pages/ReviewRequestPage.test.jsx`: add Link import and two SCRUM-55 component test declarations (recorded/missing-value variants); existing cases/assertions retained.
4. **Created** this audit/test-case document. No other files changed.

The cases below were initially authored **UNEXECUTED**. Their original static predictions are retained; the actual results in section D supersede that authoring status, including the historical UNEXECUTED labels in the test files. No test code needed correction during verification.

### AC1 / AC2 — Review-list eligibility and payload

**TC-55-01** · **Traces to:** AC1, AC2 · **Type:** backend unit, positive/negative · **Preconditions:** RV-SEED.
**Steps:** GET proposed queue as U2. **Expected result:** only R7 and R11, all summary fields, message null, no writes; no order is imposed. Draft/approved/rejected/cancelled, other-coordinator and unassigned rows are excluded. **Automated:** `ReviewRequestsUnitTests.test_list_includes_only_assigned_submitted_and_under_review_requests`.
**Static prediction:** expected fail, route absent (404). Existing managed tests intentionally cover a different all-status list.

### AC3 — No eligible requests

**TC-55-02** · **Traces to:** AC3 · **Type:** backend unit · **Preconditions:** remove both eligible requests R7/R11, retain draft/approved/rejected/cancelled/other-coordinator/unassigned rows.
**Steps:** GET queue as U2. **Expected result:** empty requests and nonblank explanatory message. **Automated:** `ReviewRequestsUnitTests.test_no_eligible_requests_has_an_explanatory_empty_state`.
**Static prediction:** expected fail, route absent. Existing no-assignment tests do not cover assigned-but-ineligible requests.

### AC6 — New queue authorization

**TC-55-03** · **Traces to:** AC6 · **Type:** backend unit, negative · **Preconditions:** RV-SEED; token says coordinator while the stored role changes.
**Steps:** GET without a token, as a missing user, then using the same token with stored admin/organiser/venue_staff/tech_staff/attendee roles. **Expected result:** 401 for invalid sessions, 403 for each other role, no private event/organiser data or writes. **Automated:** `ReviewRequestsUnitTests.test_list_requires_a_valid_session_and_current_coordinator_role`.
**Static prediction:** expected fail, route absent. Existing endpoint guards do not automatically protect a new URL.

### AC7 — Queue load failure

**TC-55-04** · **Traces to:** AC7 · **Type:** backend unit · **Preconditions:** mocked event query raises SQLAlchemyError after the valid caller is loaded.
**Steps:** GET queue, restore reads, GET again. **Expected result:** 503, explanatory error, retryable true, rollback, no success list/private exception; recovery returns R7 and R11. **Automated:** `ReviewRequestsUnitTests.test_list_load_failure_is_retryable_and_recovery_returns_requests`.
**Static prediction:** expected fail, route absent. Other list error handlers do not establish this new endpoint's behavior.

### AC5 — Existing history isolation

**TC-55-05** · **Traces to:** AC5 · **Type:** backend unit · **Preconditions:** C20 for R7 and C21 for R9 both present in fake query input.
**Steps:** GET existing R7 history as U2. **Expected result:** only C20, selected event id, no C21 text, no writes. **Automated:** `ReviewRequestsUnitTests.test_clarification_history_contains_only_the_selected_requests_messages`.
**Static prediction:** might already pass: existing `list_clarifications` filters EventClarification.event_id. Removing that production filter would expose both fake rows and fail the assertion. Existing tests have multiple viewers, but not messages on two different events.

### AC1 / AC2 / AC4 — Queue display and selection

**TC-55-06** · **Traces to:** AC1, AC2, AC4 · **Type:** frontend component · **Preconditions:** mocked list summaries with submitted id 8 and under_review id 11.
**Steps:** visit proposed App route, inspect the rows, click id 8's event-name link. **Expected result:** all required summary facts, proposed Singapore time as recorded, submission time via existing audit formatter, both Submitted and Under review rows with the correct review links, selected request's review details, no POST. **Automated:** `displays the summary fields and opens the selected request for review`.
**Static prediction:** expected fail, App has no queue route. Existing managed-list links open planning instead of review and lack two summary fields.

### AC3 — Queue empty display

**TC-55-07** · **Traces to:** AC3 · **Type:** frontend component · **Preconditions:** mocked queue is empty with explanatory message.
**Steps:** visit queue. **Expected result:** message shown, no event row. **Automated:** `shows the empty review-list message`.
**Static prediction:** expected fail, route/page absent. This establishes rendering at the new workflow boundary without re-testing managed events.

### AC7 — Queue retry interaction

**TC-55-08** · **Traces to:** AC7 · **Type:** frontend component, server/network variants · **Preconditions:** first GET rejects, second resolves.
**Steps:** visit queue, read alert, click Retry. **Expected result:** backend error or sensible transport fallback, same GET repeated, list recovered and alert cleared. **Automated:** `explains a %s failure and recovers after Retry`.
**Static prediction:** expected fail, route/page absent. Existing retry tests target different components; detail retry is already sufficiently covered and is not duplicated.

### AC4 — Every submitted detail, recorded and absent values

**TC-55-09** · **Traces to:** AC4 · **Type:** frontend component, two related value variants · **Preconditions:** full existing request fixture with accessibility present/NULL and registration true/false.
**Steps:** render existing review route; inspect heading and each labeled definition. **Expected result:** all required submitted facts, correct start/end dates/times, recorded boolean answers distinct from missing accessibility, no fabricated defaults. **Automated:** `shows all submitted fields with %s values`.
**Static prediction:** might already pass: existing `DETAILS`/`display()` implement this. New coverage is needed because the current review component test checks only three values; the complete API test cannot detect omitted UI fields.

### AC5 / AC4 — History follows selected request

**TC-55-10** · **Traces to:** AC5, AC4 · **Type:** frontend component · **Preconditions:** mocked review and existing clarification responses for populated events 7 and 8.
**Steps:** open event 7 review, read its question, navigate to event 8 review on the mounted route. **Expected result:** selected title/question, old question absent, appropriate per-event history GETs, no POST. **Automated:** `shows the selected request's existing messages and replaces them when another request opens`.
**Static prediction:** expected fail: review never requests or displays history. Standalone clarification tests do not prove visibility in review or replacement when review selection changes.

## D. Test execution status

### Isolation verification before execution

| Selected file | Isolation established | Import/setup risks reviewed |
|---|---|---|
| `backend/tests/test_review_requests_unit.py` | Bare Flask/JWT test app; no `AppTestCase`, app factory call, SQLAlchemy engine initialization or persisted fixtures. `db.session` is mocked; `Event.query` uses `_ReadQuery`; clarification query input is an in-memory fake. Engine.connect/raw_connection and socket.connect are guarded. | Inspected tests package, app factory, extensions, config, task registration, models, permissions and blueprint import paths. Importing Config reads environment settings but does not initialize a database connection. SQLAlchemy()/Celery() construction and task registration do not contact services. SMTP calls are inside an uncalled task body; selected routes are GET-only. |
| `frontend/src/pages/ReviewRequestsPage.test.jsx` | Hoisted `vi.mock` replaces the shared API client with get/post spies before App and its pages load. App is rendered inside MemoryRouter/jsdom. | Reviewed App imports and page/helper top-level declarations: no import-time requests. No axios client request can run through the mocked module. |
| SCRUM-55 cases in `frontend/src/pages/ReviewRequestPage.test.jsx` | Same hoisted API mock; request/history fixtures are local objects. Direct page routing uses MemoryRouter; selected tests do not invoke decisions. | Reviewed file imports, shared setup/helper functions, SCRUM-55 cases, Vitest/jsdom config and cleanup. Other stories' test bodies are excluded by `--testNamePattern SCRUM-55`. |

No tests were withheld for isolation concerns. No live Supabase, Redis, SMTP, backend or other external service connection was made. No application server was started. The initial frontend attempt encountered a **local filesystem infrastructure issue**, not a network dependency: the sandbox blocked esbuild's config resolution. The same reviewed command then completed with approved filesystem escalation, without changing test config or dependencies.

### Exact execution commands and limits

From `backend/` (one execution):

```powershell
.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'tests.test_review_requests_unit.ReviewRequestsUnitTests'], timeout=60); sys.exit(result.returncode)"
```

From `frontend/` (same command attempted twice: first blocked during config loading, then completed with filesystem escalation):

```powershell
../backend/.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run(['node', 'node_modules/vitest/vitest.mjs', 'run', 'src/pages/ReviewRequestsPage.test.jsx', 'src/pages/ReviewRequestPage.test.jsx', '--testNamePattern', 'SCRUM-55', '--reporter', 'verbose', '--testTimeout', '5000', '--hookTimeout', '5000'], timeout=60); sys.exit(result.returncode)"
```

No discovery, full-suite command or CI command was used. Both commands have a 60-second process timeout; frontend tests/hooks additionally have 5-second limits. No process timed out, hung or required termination.

### Individual results

| Case | Test method / frontend case | Observed result and classification |
|---|---|---|
| TC-55-01 | `test_list_includes_only_assigned_submitted_and_under_review_requests` | **Expected RED:** 404 instead of 200; list endpoint absent. |
| TC-55-02 | `test_no_eligible_requests_has_an_explanatory_empty_state` | **Expected RED:** 404 instead of 200; list endpoint absent. |
| TC-55-03 | `test_list_requires_a_valid_session_and_current_coordinator_role` | **Expected RED:** all seven subcases return 404. Missing token/deleted user expect 401; admin/organiser/venue_staff/tech_staff/attendee expect 403. Endpoint absent. |
| TC-55-04 | `test_list_load_failure_is_retryable_and_recovery_returns_requests` | **Expected RED:** 404 instead of 503; endpoint absent, so injected query failure handler is not reached. |
| TC-55-05 | `test_clarification_history_contains_only_the_selected_requests_messages` | **Already GREEN:** selected event's message returned; other event's populated history excluded. |
| TC-55-06 | `displays the summary fields and opens the selected request for review` | **Expected RED:** selected request link absent; React Router reports no matching `/events/review-requests` route. |
| TC-55-07 | `shows the empty review-list message` | **Expected RED:** empty message absent; list route/page absent. |
| TC-55-08, server | `explains a server failure and recovers after Retry` | **Expected RED:** no alert; list route/page absent. |
| TC-55-08, network | `explains a network failure and recovers after Retry` | **Expected RED:** no alert; list route/page absent. |
| TC-55-09, recorded | `shows all submitted fields with recorded values` | **Already GREEN:** all required review details display correctly. |
| TC-55-09, missing/false | `shows all submitted fields with unrecorded accessibility and no registration values` | **Already GREEN:** missing accessibility and recorded false retain distinct displays. |
| TC-55-10 | `shows the selected request's existing messages and replaces them when another request opens` | **Expected RED:** first event's question absent; review does not request/display clarification history. |

| Scope | Executed test instances | Passed | Failed | Errored | Skipped within selection | Runner duration |
|---|---:|---:|---:|---:|---:|---|
| Backend selected class | 5 methods | 1 | 4 methods | 0 | 0 | 0.056 seconds test time; 1.175 seconds command wall time |
| Frontend SCRUM-55 cases | 7 instances | 2 | 5 | 0 | 0 | 58.91 seconds total; 5.39 seconds test time |
| **Combined selected baseline** | **12** | **3** | **9** | **0** | **0** | Separate runs; no combined elapsed-time claim |

The backend runner reports **10 failure records**: three failing methods plus seven failing subcases inside the fourth method. This is four failed test methods, not ten separately executed methods. Vitest additionally reports **27 skipped unrelated cases** in the explicitly selected detail file because their names did not match SCRUM-55; none executed. Its total summary is `5 failed | 2 passed | 27 skipped (34)`.

The initial frontend startup infrastructure error occurred before test execution (approximately 6.04 seconds command wall time). It is separate from the completed run's zero test errors. The successful startup run spent most time in jsdom environment/setup/collection; assertions themselves took 5.39 seconds. All selected failures are classified Expected RED; no unexpected assertion failures or test defects were observed.

### Corrections and RED assessment

**No test corrections were necessary. No test file or shared test infrastructure was modified during verification.** This document alone was updated to record observed results and replace the historical unexecuted report.

The observed failures accurately identify the missing review queue endpoint/page and missing clarification history in review. Assertions after those first missing-capability failures remain unexercised until GREEN; this run does not claim that every later assertion has already been validated. The three passing instances establish existing message filtering and complete detail rendering; they are retained without forcing artificial failures.

**TC-55-04 review:** the first in-process GET injects an event-query SQLAlchemyError and expects the established 503/error/retryable/rollback contract. The test then restores its fake query and issues a second, independent GET. That is a client making another request after recovery, not server-side retry infrastructure. The user-facing Retry interaction belongs to frontend TC-55-08. No retry framework, job, reconnection mechanism or production change is required by this test design.

## E. Minimal GREEN-phase implementation plan (historical RED plan)

**Strictly required:**

1. Review the proposed list contract before implementation. Add one read-only list route in `backend/app/events/routes.py` with JWT, current stored coordinator role, current-assignment and an explicit `submitted`/`under_review` status filter, as confirmed by the user. Return summary fields using existing Event/User columns; wrap all dependent reads in the existing SQLAlchemyError/rollback/retryable response pattern. Never alter `/managed`, `/requests`, `/mine`, existing review status access, approval/rejection eligibility or authorization rules.
2. Add `frontend/src/pages/ReviewRequestsPage.jsx` with the summary list, eligible-empty message, server/fallback load error and Retry. Wire its route and discoverable navigation in `App.jsx`; link names to existing review details. No dashboard, controls, search or pagination.
3. Add a read-only clarification-history load/display to `ReviewRequestPage.jsx` using the existing history endpoint. Scope state to eventId and clear/replace prior history when selection changes; handle load failures without claiming an empty history. Reuse the local error/retry pattern without adding sending/reply actions. Keep existing decision functionality unchanged.
4. Once GREEN is authorized, adjust only the affected review test mock fixtures to return the proper history response for the additional GET, instead of returning `{request: ...}` for every URL. The existing test helper currently uses one response shape; this is a mock-contract maintenance dependency of inline history, not missing production capability. Do not weaken those existing assertions.

**Reuse:** `_current_user`, `COORDINATOR_ROLE`, `_is_current_coordinator`, `_error`, `_isoformat`, `_user_summary`, existing Event/User/EventClarification models, `_request_payload`, `/review`, `/clarifications`, apiClient, statusLabel and formatSavedAt. Initial assignment/submission already works through SCRUM-28. Full detail rendering and detail retry need no rewrite.

**Defer:** approval/rejection changes, assignment/reassignment, clarification creation/replies, notifications, dashboards, sorting/filtering controls, search, pagination, registration management, new statuses, dependencies and architecture/schema changes. No new table or migration is justified by these ACs.

**Separate observation, not a fix:** standalone `ClarificationPage` renders its composer unconditionally despite the endpoint's `can_send` flag (SCRUM-27 already has a unit capability test). Backend still denies unauthorized sends; do not expand SCRUM-55 into repairing the writing workflow.

## Open questions for the customer / GREEN review

- **Q1 — Resolved by the user on 14 Oct 2026:** include only submitted and under_review in the separate SCRUM-55 list; preserve the managed-events list's all-status behavior and existing approval/rejection eligibility. The RED tests encode this exact boundary; observed results are recorded in section D.
- **Q2 — Resolved by user instruction:** preserve existing authorization rules, including assigned-coordinator visibility. No broader access is proposed.
- **Q3:** Accept the additive `/review-requests` URL/page proposal, or choose an equivalent isolated route before GREEN? Reusing `/managed` by narrowing its results would conflict with SCRUM-62.
- **Q4:** Is email acceptable as organiser identity and is the existing local audit-timestamp formatter acceptable for submission time? No organiser-name field or new timestamp policy is assumed.
- **Q5:** Is inline read-only clarification history preferred, or is explicit navigation to a read-only history view sufficient? The prepared component case uses inline history; it can change if product review selects another presentation.

## F. RED-phase scope and safety confirmation (historical)

- Only the explicitly authorized SCRUM-55 unit/component tests were executed; section D records the verified baseline.
- No production code, database schema, environment configuration or API contract was modified.
- No unrelated user story was implemented; no infrastructure, dependency or persisted seed data was introduced.
- No unrelated tests were executed, altered, removed or weakened; unrelated Vitest cases were excluded by the SCRUM-55 name filter. No test code required correction during verification.
- No live Supabase, Redis or external service connections, application servers, full test suites or CI commands were used.
- No commits, pushes or pull requests were performed.
- Stop at this audit and RED verification. GREEN requires explicit user review/approval; no implementation, production refactor or pull request was performed.

## G. GREEN implementation and verification — 14 Oct 2026

### A. Production changes

| File | Change and acceptance criteria | Reuse / shared-code impact |
|---|---|---|
| `backend/app/events/routes.py` | Added `REVIEW_QUEUE_STATUSES`, `_review_summary_payload()` and JWT-protected `list_review_requests()` at `GET /api/events/review-requests`. Filters current coordinator assignment and submitted/under_review; sends all five summary facts and an eligible-empty message; returns retryable 503 on dependent read failures. AC1–3, AC6–7. | Reuses `_current_user`, `COORDINATOR_ROLE`, `_user_summary`, `_recorded`, `_isoformat`, Event/User and the established rollback/error convention. Reads each distinct organiser once. New definitions in shared routes file; no existing backend function changed. |
| `frontend/src/pages/ReviewRequestsPage.jsx` (created) | Dedicated queue with all summary fields, loading/empty/error states, Retry and links to existing request review. AC1–4, AC7. | Reuses apiClient, Link, statusLabel and formatSavedAt. Proposed times remain as recorded Singapore time; missing values use Not recorded. |
| `frontend/src/App.jsx` | Added the queue route and Requests for review navigation entry. AC1, AC4. | Additive wiring in the shared router/nav; existing routes preserved. API authorization independently controls data access. |
| `frontend/src/pages/ReviewRequestPage.jsx` | Added local read-only `ClarificationHistory` using the existing history GET, sender/time display, empty/loading/error states and Retry questions. Review selection remounts its local state by eventId; history ignores responses after unmount/retry. AC4–5, AC7. | Reuses existing detail rendering, detail load/retry, error helper, audit formatter and clarification authorization endpoint. Existing decision handler is unchanged. No message-writing controls added. |

### B. Acceptance criteria and tests

| AC | Implemented behavior | Coverage |
|---|---|---|
| AC1 | Separate queue includes assigned submitted/under_review only; excludes draft/approved/rejected/cancelled, other-coordinator and unassigned requests. `/managed` is unchanged. | TC-55-01 and TC-55-06 pass. |
| AC2 | Event name, organiser email, proposed start date/time, submission date/time and readable status appear in each row. | TC-55-01 and TC-55-06 pass. |
| AC3 | Empty eligible queue returns/displays a human message even while ineligible rows exist. | TC-55-02 and TC-55-07 pass. |
| AC4 | Selected row opens the existing review detail endpoint/page; all submitted fields retain recorded/missing/false meaning. Event changes reset previous selection state. | TC-55-06, both TC-55-09 variants and TC-55-10 pass. |
| AC5 | Existing history is read from the selected event's authorized endpoint and shown inline. Previous event's history disappears on selection change. | TC-55-05 and TC-55-10 pass. |
| AC6 | JWT plus freshly loaded stored coordinator role protects the queue; query is scoped to current coordinator_id. Existing detail/history authorization is unchanged. | TC-55-01 and TC-55-03 pass; prior detail-authorization coverage remains recorded in section B. |
| AC7 | Queue API returns established retryable errors; frontend server/network failures recover using Retry. Existing detail Retry remains intact; history has its own error/Retry questions path. | TC-55-04 and both TC-55-08 variants pass. Existing detail Retry test was inspected but not executed because it is outside the permitted selection; history-error retry was inspected statically. |

No remaining implementation gap was identified against the supplied ACs. This isolated selection does not establish real database/RLS behavior, browser appearance or whole-application regression freedom.

### C. Isolation and exact GREEN commands

Before execution, re-inspected the selected test modules, helpers, fixtures, mocks, setup, import paths and updated production reads. Backend remains a bare Flask app with mocked persistence/fake queries and connection guards; the app factory is never called. Importing configuration/task/model/blueprint modules does not open external connections. Frontend apiClient is mocked before App/page imports; MemoryRouter/jsdom is used. No test was withheld for isolation concerns.

From `backend/`, one execution, 60-second process timeout:

```powershell
.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'tests.test_review_requests_unit.ReviewRequestsUnitTests'], timeout=60); sys.exit(result.returncode)"
```

From `frontend/`, initial seven-case selection, 90-second process timeout and 5-second per-test/hook limits:

```powershell
../backend/.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run(['node', 'node_modules/vitest/vitest.mjs', 'run', 'src/pages/ReviewRequestsPage.test.jsx', 'src/pages/ReviewRequestPage.test.jsx', '--testNamePattern', 'SCRUM-55', '--reporter', 'verbose', '--testTimeout', '5000', '--hookTimeout', '5000'], timeout=90); sys.exit(result.returncode)"
```

From `frontend/`, rerun only the affected queue file after the selector correction:

```powershell
../backend/.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run(['node', 'node_modules/vitest/vitest.mjs', 'run', 'src/pages/ReviewRequestsPage.test.jsx', '--testNamePattern', 'SCRUM-55', '--reporter', 'verbose', '--testTimeout', '5000', '--hookTimeout', '5000'], timeout=90); sys.exit(result.returncode)"
```

Frontend commands used the local filesystem escalation required by esbuild during RED verification. One launch of the four-case rerun was rejected because the automatic approval review exceeded its deadline; no process started in that attempt. The permitted single retry launched and completed. No extra test execution or dependency/configuration change was used to work around that review timeout.

| GREEN run | Passed | Failed | Errored | Skipped | Duration |
|---|---:|---:|---:|---:|---|
| Backend five-method class | 5 | 0 | 0 | 0 | 0.042 seconds test time; 0.781 seconds command wall time |
| Initial frontend seven-case selection | 6 | 1 | 0 | 27 unrelated cases filtered out | 2.38 seconds total; 0.500 seconds test time |
| Affected frontend queue-file rerun | 4 | 0 | 0 | 0 | 1.32 seconds total; 0.325 seconds test time |
| **Latest result for each original selected instance** | **12** | **0** | **0** | **0 selected instances skipped** | Across the runs above, not a claim of a separate final full rerun |

The initial frontend failure revealed a latent **test-selector defect** after the missing route was implemented: `getByText(/Submitted/)` matched both `Submitted: <timestamp>` and `Status: Submitted`. Changed it to `getByText("Status: Submitted")`, which precisely asserts the intended status. This does not change acceptance criteria or weaken the assertion. No production implementation correction was required after the initial targeted execution. The three detail/history cases already passed and were not rerun unnecessarily.

Test maintenance:

- `ReviewRequestsPage.test.jsx`: corrected that one ambiguous status selector; all other assertions retained.
- `ReviewRequestPage.test.jsx`: existing helper now supplies the review payload once, while its mocked history endpoint returns an empty-history payload. This reflects the new read-only GET rather than falsely returning `{request: ...}` for every URL. Existing unrelated test bodies/assertions are unchanged. The permitted SCRUM-55 detail/history cases passed with this fixture.
- `test_review_requests_unit.py`: no GREEN-phase changes.
- Historical UNEXECUTED labels in source identify authoring state; the actual execution results here supersede them.

### D. Regression assessment

- Existing managed-list behavior, organiser lists, detail/history API contracts, submission, assignment and approval/rejection eligibility remain unchanged. A static AST comparison confirmed every pre-existing backend function/class definition is unchanged.
- Review detail is shared with decision workflows. Its decision handler is unchanged; state is remounted only when the selected event id changes. The additional history GET required the local fixture update described above. A static comparison confirmed existing unrelated detail-test bodies are unchanged.
- The full selected-request fields, null/false rendering and selected-event history passed targeted component tests. Real ORM execution and wider decision/accountability/reassignment workflows were not exercised.
- Later, with approval, relevant decision/detail Retry frontend cases and managed-events/authorization regressions would provide additional confidence. No broader suite or Supabase-backed test was run automatically.

### E. Scope and engineering judgment

The four production files listed above comprise the implementation. The state remount and ignored stale history responses are localized safeguards needed to keep the selected request's data accurate; no broader refactor was performed. No additional user story or unrelated production defect was implemented. The previously noted standalone clarification composer's treatment of `can_send` remains deferred; backend send authorization is unchanged.

No dependencies, schema migrations, model fields, infrastructure, background jobs, notifications or server-side retry mechanism were introduced. The proposed additive route and inline-history presentation were adopted under the user's GREEN authorization; organiser email and the existing audit formatter were reused as instructed.

### F. Safety and stop condition

- No live Supabase, Redis, SMTP, backend or other external service connections were made.
- No application server, full test suite, integration test, broad regression run or CI command was executed.
- Only the permitted isolated SCRUM-55 tests ran; 27 unrelated frontend cases were filtered out in the initial frontend run.
- No tests were removed, bypassed or weakened. The selector correction and necessary mock-contract maintenance are documented above.
- No commits, pushes or pull requests were performed.
- GREEN is achieved for all 12 original selected instances. Stop here pending further user instructions.

## H. Focused post-GREEN regression review — 14 Oct 2026

### Findings and regression surface

**No blocking regression was found. No production file changed during this review.** Inspected the actual production diff, queue and detail call sites, model columns, permission helpers, serializers, API client, router/navigation, timestamp formatter and directly affected fixtures.

- **Queue SQLAlchemy correctness:** production chains `filter_by(coordinator_id=user.id)` and `filter(Event.status.in_(REVIEW_QUEUE_STATUSES))`, yielding AND predicates on the same Event query. Added an isolated test that supplies a real SQLAlchemy Query, intercepts Query.all(), inspects the actual production WHERE predicates and compiles the statement with the PostgreSQL dialect. No SQL is executed. Both assignment and the exact submitted/under_review set are checked independently of the lightweight filtering fake.
- **Authorization:** JWT remains required. `_current_user` uses stored User.role and the queue requires coordinator; assignment is filtered before serialization. The existing detail/history checks follow reassignment and reject unrelated roles. Public navigation remains consistent with the existing app: the link/page shell is visible, while backend 401/403 prevents access to request data. Added direct-navigation component assertions for both refusals. No token-role trust or new frontend permission model was introduced.
- **Timestamps/serialization:** submitted_at is the existing stored naive UTC audit timestamp, serialized through `_isoformat` and displayed through formatSavedAt. A missing stored timestamp stays null; it is not replaced with the current time or the proposed date. Proposed times remain naive Singapore-local values shown as recorded. Organiser serialization reuses id/email; all payload reads remain in the SQLAlchemyError boundary.
- **Read failures:** a secondary organiser read failure produces 503/retryable/rollback with no partial success payload or exception disclosure. An actual absent organiser can remain null under the existing data semantics. The new regression distinguishes these cases without a database.
- **Queries:** one Event query plus one lookup per distinct organiser (in addition to current-user lookup); repeated events for one organiser do not cause repeated lookups. No writes, notifications or emails are added. Many distinct organisers would still entail multiple lookups; a batch/join optimization is deferred because no load-related defect is demonstrated and the scope excludes broader queue infrastructure.
- **Additional history GET:** history has separate loading/error/retry state, so it does not block request details or erase a typed decision reason. Retry questions reloads only history, not details. Cleanup ignores a late response from the previous event, while the eventId key resets the selected review state. Added explicit in-flight response and independent retry assertions.
- **Existing decisions:** approval, rejection, decision accountability, failed-save reason retention/retry and the prohibition on approving non-submitted statuses pass with the new GET. No decision handler or backend eligibility change was needed.
- **Managed events/router:** existing managed list remains all-status and its names still link to planning; the new queue links to review. The two selected managed-component cases exercise both contracts. Existing backend managed implementation was inspected and remains unchanged.
- **Dependencies/state:** no new dependency, schema change or server-side retry system. New state is confined to the queue load result/error and the independent history load/result/retry lifecycle.

### Focused regression assertions added

All new cases below **passed** in the isolated execution recorded below. Existing assertions were retained, not weakened. Modified only the three existing SCRUM-55 test files plus this report.

**TC-55-11 — Real production ORM query and missing submission timestamp**
- **Traces to:** AC1, AC2, AC6 · **Type:** backend unit.
- **Preconditions:** existing RV-SEED with R7.submitted_at null; Event.query supplies a real Query bound to the mocked session. Query.all is intercepted before any SQL execution.
- **Steps:** GET queue; capture/compile its production statement; inspect WHERE predicates and returned timestamps.
- **Expected result:** coordinator equality to caller id 2 AND status IN submitted/under_review; null submission stays null, recorded R11 timestamp unchanged; no writes.
- **Automated:** `ReviewRequestsUnitTests.test_real_orm_query_scopes_assignment_and_status_and_preserves_null_submission`.

**TC-55-12 — Secondary organiser read outage**
- **Traces to:** AC2, AC7 · **Type:** backend unit.
- **Preconditions:** mocked caller/event reads succeed; organiser lookup raises SQLAlchemyError.
- **Steps:** GET queue.
- **Expected result:** 503/retryable and rollback, no partial requests or private exception text, no writes.
- **Automated:** `ReviewRequestsUnitTests.test_organiser_read_failure_does_not_return_partial_or_fabricated_data`.

**TC-55-13 — Independent history retry preserves planning review input**
- **Traces to:** AC4, AC5, AC7 · **Type:** frontend component.
- **Preconditions:** mocked review loads; history initially rejects with a server explanation and then succeeds.
- **Steps:** read details/error, type a decision reason, click Retry questions.
- **Expected result:** history recovers, alert clears, typed reason stays intact, detail GET happens only once, no POST.
- **Automated:** `retries failed history without reloading details or losing a typed decision reason`.

**TC-55-14 — Late previous-event history response**
- **Traces to:** AC4, AC5 · **Type:** frontend component.
- **Preconditions:** first event's history is a deferred local promise; second event's review/history succeeds.
- **Steps:** navigate while first history is loading, then resolve the old promise.
- **Expected result:** second event's title/history remains; no previous-event message or write appears.
- **Automated:** `ignores a late history response after a different request is selected`.

**TC-55-15 — Direct queue navigation with session/role refusal**
- **Traces to:** AC6 · **Type:** frontend component, 401 and 403 variants.
- **Preconditions:** apiClient is mocked to return each backend refusal.
- **Steps:** navigate directly to the queue route.
- **Expected result:** exact explanatory alert, no event/organiser details, no POST. Actual stored-role decisions remain covered by the backend tests.
- **Automated:** `shows a %s refusal without exposing request data`.

### Isolation and exact test execution

Before running, inspected imports, setup, helpers and mocks for every selected file. The two backend classes use bare Flask/JWT apps, mocked sessions, in-memory rows and Engine/socket guards. The authorization fixture mocks email dispatch; no Redis/SMTP calls occur even when an existing decision workflow is exercised. App imports construct extensions/register tasks and models but do not call create_app/init_app or connect. The new real-query regression intercepts Query.all() and compiles only with local metadata; Engine guards remain active. Frontend files mock apiClient before page/App imports, render MemoryRouter/jsdom and use the inspected cleanup setup. No tests were withheld for isolation concerns.

Executed once from `backend/`, with a 60-second process timeout:

```powershell
.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'tests.test_review_requests_unit.ReviewRequestsUnitTests', 'tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them', 'tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_unrelated_organiser_and_attendee_direct_reads_are_denied'], timeout=60); sys.exit(result.returncode)"
```

Executed once from `frontend/`, with a 90-second process timeout and 5-second test/hook limits, using the local filesystem escalation required by esbuild:

```powershell
../backend/.venv/Scripts/python.exe -B -c "import subprocess, sys; result = subprocess.run(['node', 'node_modules/vitest/vitest.mjs', 'run', 'src/pages/ReviewRequestsPage.test.jsx', 'src/pages/ReviewRequestPage.test.jsx', 'src/pages/ManagedEventsPage.test.jsx', '--testNamePattern', 'SCRUM-55|approves, shows Approved|rejects with the trimmed reason|shows a retryable error when the request cannot be loaded|keeps the reason exactly as typed|confirms the outcome with who decided and when|offers no Approve button|lists each event with its name, proposed date and status|opens each event.s planning page', '--reporter', 'verbose', '--testTimeout', '5000', '--hookTimeout', '5000'], timeout=90); sys.exit(result.returncode)"
```

**Exact backend selection — all passed:**

1. `ReviewRequestsUnitTests.test_clarification_history_contains_only_the_selected_requests_messages`
2. `ReviewRequestsUnitTests.test_list_includes_only_assigned_submitted_and_under_review_requests`
3. `ReviewRequestsUnitTests.test_list_load_failure_is_retryable_and_recovery_returns_requests`
4. `ReviewRequestsUnitTests.test_list_requires_a_valid_session_and_current_coordinator_role`
5. `ReviewRequestsUnitTests.test_no_eligible_requests_has_an_explanatory_empty_state`
6. `ReviewRequestsUnitTests.test_organiser_read_failure_does_not_return_partial_or_fabricated_data`
7. `ReviewRequestsUnitTests.test_real_orm_query_scopes_assignment_and_status_and_preserves_null_submission`
8. `AuthorizationHttpUnitTests.test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them`
9. `AuthorizationHttpUnitTests.test_unrelated_organiser_and_attendee_direct_reads_are_denied`

**Exact frontend selection — all passed:**

| File | Executed cases |
|---|---|
| `ReviewRequestsPage.test.jsx` (6) | `displays the summary fields and opens the selected request for review`; `shows the empty review-list message`; `shows a 401 refusal without exposing request data`; `shows a 403 refusal without exposing request data`; `explains a server failure and recovers after Retry`; `explains a network failure and recovers after Retry` |
| `ReviewRequestPage.test.jsx` (14) | `shows all submitted fields with recorded values`; `shows all submitted fields with unrecorded accessibility and no registration values`; `shows the selected request's existing messages and replaces them when another request opens`; `retries failed history without reloading details or losing a typed decision reason`; `ignores a late history response after a different request is selected`; `approves, shows Approved, and removes the buttons`; `rejects with the trimmed reason and shows it`; `shows a retryable error when the request cannot be loaded`; `confirms the outcome with who decided and when`; `keeps the reason exactly as typed after a failed save and resends it on retry`; `offers no Approve button for a under_review request`; `offers no Approve button for a approved request`; `offers no Approve button for a draft request`; `offers no Approve button for a cancelled request` |
| `ManagedEventsPage.test.jsx` (2) | `lists each event with its name, proposed date and status`; `opens each event's planning page` |

| Scope | Passed | Failed | Errored | Selected skipped | Duration |
|---|---:|---:|---:|---:|---|
| Backend | 9 | 0 | 0 | 0 | 0.098 seconds test time; 0.766 seconds command wall time |
| Frontend | 22 | 0 | 0 | 0 | 4.48 seconds total; 1.75 seconds test time |
| **Total selected** | **31** | **0** | **0** | **0** | Separate runs, no combined elapsed-time claim |

Frontend reported 23 additional cases skipped by the explicit name filter; they were not executed. Existing datetime.utcnow() deprecation warnings occurred in the mocked reassignment/decision path. This predates SCRUM-55, matches the repository's naive-UTC contract and was left unchanged.

### Outcome and readiness

All original 12 SCRUM-55 instances were included and remain GREEN. AC1–AC7 remain satisfied by the reviewed implementation and focused evidence; no blocking regression or necessary production correction was found. SCRUM-55 is **ready for commit and PR review on this focused evidence**, with the following limits made explicit for reviewers:

- SQL compilation and mocked request handling do not prove live PostgreSQL execution, Supabase grants/RLS, transaction behavior, query plans or production performance.
- No live login-to-review browser flow, deployed route/proxy behavior or end-to-end email/Redis interaction was tested.
- The public nav link is not itself role-hidden; API authorization protects data. That follows the established application pattern and was not expanded into a new authentication/navigation story.
- Larger queues with many distinct organisers could benefit from a future batch lookup; no performance test or optimization was added here.

No production changes, dependencies, schema/environment changes, unrelated story implementation, full-suite discovery, integration runs, external service connections or application servers were introduced by this review. No tests were removed or weakened. No commits, pushes or PRs were performed. Stop after this focused regression report.
