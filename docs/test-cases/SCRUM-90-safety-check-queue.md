# SCRUM-90 — Safety Officer Sees Events Awaiting a Safety Check: Test Cases

**User story:** As a Safety Officer, I want to see the events waiting for my safety check, so that I know which events I must review.

**Created:** 27 Oct 2026 · **Status:** PR #58 corrections verified: 4 backend unit methods, 1 dedicated local PostgreSQL test and 4 frontend tests pass. Original RED/GREEN evidence is retained below.
**Requirements source:** Jira wording supplied by the user; no Jira URL supplied.
**Automated tests:** [backend unit tests](../../backend/tests/test_safety_check_queue_unit.py), [one opt-in local PostgreSQL test](../../backend/tests/test_safety_check_queue_local.py), [frontend tests](../../frontend/src/pages/SafetyCheckQueuePage.test.jsx).
**Related:** [SCRUM-40](SCRUM-40-approve-venue-booking.md), [SCRUM-42](SCRUM-42-equipment-requirements.md), [SCRUM-44](SCRUM-44-reserve-equipment.md). SCRUM-91/92 decisions and lifecycle changes are outside this story.

## Acceptance criteria

| ID | Criterion (verbatim) |
|---|---|
| AC1 | An event appears once its venue booking is Confirmed and its equipment is reserved, or no equipment is required. |
| AC2 | The list shows event, venue, date, expected attendance and equipment. |
| AC3 | Only a Safety Officer can open the list. Anyone else is denied and sees no event data. |
| AC4 | If the list cannot be loaded, the user is told and no partial list is shown. |

## Working assumptions (to confirm)

- **A1 / Q1 — No equipment:** provisionally, no structured `EquipmentRequirement` rows plus a blank/null `Event.equipment_requirements` note means no equipment is required, as authorized for this RED phase. A note without structured requirements is not automatically ready. Free text is never parsed into quantities. The schema does not distinguish an affirmative declaration from nothing having been recorded.
- **A2 / Q2 — Reservations:** every structured requirement needs its full quantity covered by actual `EquipmentReservation` rows with status `reserved`, linked to that event and requirement. Sum split reservations; released history does not count. Arrangement status (e.g. `requested`) does not establish or invalidate reservation completeness. Existing SCRUM-44 creates reservations for the event period and releases them when its period/requirements change; these tests do not add a period-validation rule.
- **A3 / Q3 — Scope and dates:** any stored `safety_officer` can open the queue; no assignment exists. Display event start/end as recorded in Singapore time and venue names from confirmed bookings. Multiple confirmed bookings must not duplicate event rows. PR #58 explicitly requires exclusion of cancelled/rejected events and events ending at or before Singapore-local now. No approved-only allowlist or advance-notice window is added.
- **A4 / Q4 — Proposed additive contract:** `GET /api/events/safety-checks`, frontend `/events/safety-checks`. Return `{events: [...], message: string|null}`. Each event has `id`, `title`, `start_time`, `end_time`, `expected_attendance`, `venues: [{id, name}]` and `equipment: [{equipment_type, quantity, reserved_quantity}]`. Empty equipment displays "No equipment required". No ordering or safety decision fields are required. Names are implementation proposals, not Jira wording.
- **A5 / Q5 — Reload:** a simple Refresh action supplies a user-visible way to recheck readiness and verify AC4 after a previous successful load. Retrieval failure uses the existing 503/error/`retryable: true` convention. A refusal or failure must not leave event data visible. PR #58 requires superseded successes and failures to be ignored, using the request counter demonstrated by `UnassignedQueuePage`.
- **A6 / Q6 — Multi-venue schedule coverage (confirmed by the user, 27 Oct 2026):** confirmed booking periods collectively cover the current event's entire `[start_time, end_time)` without gaps; no single booking must cover the whole event. Bookings may be wider, overlap or meet at a phase boundary, and need not have identical times. The implemented PR #58 correction uses booked activity times, not setup/turnaround buffers or only `Event.venue_id`. The model has no venue-by-phase requirements, and none are introduced by this confirmed collective-coverage rule. Booking creation/approval/rescheduling remain unchanged.

## Seed data — SC-SEED (in memory only)

Stored user 90 has role `safety_officer`; the authorization test switches this stored role. Venues 10/11 are Aurora Hall/Meeting Room. Unless noted, events are approved, expected attendance 60, on 12 Dec 2026 17:00–20:00 Singapore time. Unit tests freeze now at 12 Dec 2026 16:00. No persisted unit fixtures or database seed scripts are used.

| Event | Venue booking | Equipment | Expected |
|---|---|---|---|
| E1 Reserved workshop | Confirmed venue 10: 16:00–21:00; venue 11: 17:30–19:30 | Microphones: required 2, active reservations 1 + 1; projector: required/reserved 1 | Included once; booking times need not be identical |
| E2 No equipment meeting | Confirmed | No structured requirements or note | Included |
| E3 Pending venue | Pending | No requirements/note | Excluded |
| E4 One requirement still missing | Confirmed | Microphones fully reserved; projector has only a released reservation | Excluded |
| E5 Unprocessed equipment note | Confirmed | "Speakers needed"; no structured requirements | Excluded |
| E6 Partly reserved microphones | Confirmed | Required 2, reserved 1 | Excluded |
| E7 No venue booking | None | No requirements/note | Excluded |
| E8/E9 | Confirmed; event cancelled/rejected | No requirements/note | Excluded |
| E10/E11 | Confirmed; event ended yesterday/ends exactly at frozen now | No requirements/note | Excluded |
| E12 Rescheduled event | Confirmed 17:00–20:00; event now 18:00–21:00 | No requirements/note | Excluded: current schedule not covered |
| E13 Venue phases | Venue 10: 17:00–18:00; venue 11: 18:00–20:00 | No requirements/note | Included once: continuous coverage |
| E14 Venue phases with gap | Venue 10: 17:00–18:00; venue 11: 18:01–20:00 | No requirements/note | Excluded: one-minute uncovered interval |

The frontend uses E1 with one venue plus E2, or an empty response. Backend eligibility is not reimplemented in React fixtures.

## AC1 — Eligibility

**TC-90-01 · Include only events ready by booking and equipment quantities**

- **Traces to:** AC1 · **Type:** Positive/negative · **Preconditions:** SC-SEED, Safety Officer JWT.
- **Steps:** GET the proposed queue against the complete mixed fixture set.
- **Expected result:** HTTP 200; event IDs exactly E1/E2/E13, each once. Split active quantities satisfy E1; pending/missing booking, incomplete quantities, released equipment, note-only requirements, cancelled/rejected or ended events, a stale booking and a booking gap exclude E3–E12/E14.
- **Automated:** `SafetyCheckQueueUnitTests.test_eligibility_uses_confirmed_bookings_and_complete_active_quantities`.
- **Local SQL regression (TC-90-01/02):** `SafetyCheckQueueLocalTests.test_current_schedule_and_equipment_readiness_through_postgresql` uses `AppTestCase` with the guarded dedicated local database. Its single fixture checks ready/full quantities, cancelled/rejected, ended, stale schedule, touching multi-venue phases and a gap. It asserts only about its own event IDs; all inserted rows are rolled back.

## AC2 — List contents

**TC-90-02 · Complete display information without duplicate events**

- **Traces to:** AC2 (supports AC1) · **Type:** Positive/boundary · **Preconditions:** SC-SEED.
- **Steps:** GET the queue as Safety Officer; inspect E1 and E2.
- **Expected result:** E1 occurs once, with title, both confirmed venues, event start/end, attendance 60 and both equipment types with required/reserved quantities. E2 has empty equipment. Nonempty response has `message: null`.
- **Automated:** `SafetyCheckQueueUnitTests.test_list_contains_the_required_information_without_duplicate_events`.

## AC3 — Access

**TC-90-03 · Refuse unauthenticated users and every other existing role**

- **Traces to:** AC3 · **Type:** Negative authorization · **Preconditions:** SC-SEED.
- **Steps:** Request without a JWT, then as stored admin, coordinator, coordinator_lead, organiser, venue_staff, tech_staff and attendee.
- **Expected result:** 401 without authentication; 403 for other roles. Human error, no events or private titles; no event listing query. Positive Safety Officer access is checked by TC-90-01/02.
- **Automated:** `SafetyCheckQueueUnitTests.test_unauthenticated_and_other_roles_are_denied_without_event_data` (subtests).

## AC4 — Load failure

**TC-90-04 · Equipment retrieval failure discards the whole response**

- **Traces to:** AC4 · **Type:** Negative · **Preconditions:** SC-SEED; equipment reservation query raises `SQLAlchemyError`.
- **Steps:** GET as Safety Officer with event data available but reservation retrieval failing.
- **Expected result:** 503 with human error and `retryable: true`; rollback; no events, event titles or internal exception text. Assert the failing retrieval was actually attempted.
- **Automated:** `SafetyCheckQueueUnitTests.test_equipment_retrieval_failure_returns_error_without_a_partial_list`.

## Frontend

**TC-90-05 · Open the queue, display details and explain an empty list**

- **Traces to:** AC1, AC2 · **Type:** Positive/empty · **Preconditions:** Mock API client; signed-in session; render existing App in MemoryRouter at the proposed route.
- **Steps:** Open with eligible summaries, then remount with an empty list and human message.
- **Expected result:** Queue heading, event/venue/date/attendance/equipment fields and no-equipment text are visible; empty response shows its message without old rows. API URL matches the proposed contract.
- **Automated:** `opens the route, shows event details, and explains an empty queue`.

**TC-90-06 · Show refusal without event data**

- **Traces to:** AC3 · **Type:** Negative · **Preconditions:** Mock API returns 403 with a human error.
- **Steps:** Open the proposed route directly.
- **Expected result:** Safety queue heading and refusal alert; no event title, venue or equipment. A missing screen cannot pass by merely rendering no data.
- **Automated:** `shows the authorization refusal without exposing event information`.

**TC-90-07 · Failed initial load or refresh shows an error without old data**

- **Traces to:** AC4 · **Type:** Negative · **Preconditions:** Mock initial success followed by 503; separately an initial 503.
- **Steps:** Load E1/E2, click Refresh and inspect the failure; remount with an initial failure.
- **Expected result:** Human alert; no previously loaded event titles or venue and no partial rows; initial failure also displays the alert without event data.
- **Automated:** `clears previously loaded data on failure and explains an initial failure`.

**TC-90-08 · A superseded response cannot overwrite the newest refresh**

- **Traces to:** AC4 · **Type:** Negative regression · **Preconditions:** StrictMode (as in `main.jsx`) leaves one initial request pending; a second initial request succeeds.
- **Steps:** Refresh to a newer empty result; then settle the older request as a success or a failure, in two combined scenarios.
- **Expected result:** The latest empty message remains visible; neither old event data nor an old error is restored.
- **Automated:** `ignores older results and errors after a newer refresh`.

## Traceability matrix

| AC | Backend | Frontend |
|---|---|---|
| AC1 | TC-90-01, 02 | TC-90-05 |
| AC2 | TC-90-02 | TC-90-05 |
| AC3 | TC-90-01/02 positive, 03 refusal | TC-90-06 |
| AC4 | TC-90-04 | TC-90-07, 08 |

## Open questions for the customer

| ID | Question | Assumption/cases |
|---|---|---|
| Q1 | Is absence of structured requirements and an organiser note sufficient to mean no equipment is required? | A1, TC-90-01/05 |
| Q2 | Confirm full active quantities per recorded requirement as the equipment readiness rule. | A2, TC-90-01/02 |
| Q3 | Confirm shared officer visibility and event dates with all confirmed venues in one event row. | A3, TC-90-02/05 |
| Q4 | Confirm the proposed route and summary presentation. | A4, all cases |
| Q5 | Confirm the simple Refresh action used to reload the list. | A5, TC-90-07 |
| Q6 | Resolved by the user, 27 Oct 2026: collective coverage across confirmed venues without gaps is the readiness rule; a single booking need not cover the whole event. | A6, TC-90-01/02 |

## RED execution — 27 Oct 2026

Commands executed from `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_check_queue_unit
```

**Actual:** exit 1; 4 methods run in 0.089 seconds; `FAILED (failures=11)` (3 standalone assertions plus 8 authorization subtest assertions). No errors, connection-guard failures or import failures. Only the new module's tests were selected; importing `_ReadQuery` does not execute SCRUM-55 tests.

| Case | Expected status | Observed failure |
|---|---|---|
| TC-90-01 | 200 | 404: listing endpoint absent |
| TC-90-02 | 200 | 404: listing endpoint absent |
| TC-90-03 | 401 without JWT; 403 for the seven other roles | All eight subcases return 404 because the endpoint/guard is absent |
| TC-90-04 | 503 | 404: endpoint absent, injected retrieval failure not reached |

Commands attempted from `frontend/` (the environment variable only shortens DOM diagnostics):

```powershell
$env:DEBUG_PRINT_LIMIT='700'
npm test -- src/pages/SafetyCheckQueuePage.test.jsx --reporter=dot
```

The first attempt did not start Vitest: PowerShell execution policy blocked the `npm.ps1` launcher. Retried using the installed Windows command launcher:

```powershell
$env:DEBUG_PRINT_LIMIT='700'
npm.cmd test -- src/pages/SafetyCheckQueuePage.test.jsx --reporter=dot
```

The sandboxed attempt stopped before test collection: esbuild could not read the ancestor directory/resolve the existing Vitest config (access denied). The **same command** was then run with elevated sandbox permissions and completed.

**Actual completed frontend run:** Vitest 2.1.9; exit 1; 1 file, 3 tests failed; test time 3.069 seconds, total duration 34.64 seconds. TC-90-05, 06 and 07 each fail at `findByRole("heading", { name: "Events awaiting a safety check" })`: the safety queue page/route is absent. Existing App matches the generic event-detail route instead. No missing-component import, unhandled runtime error or test-infrastructure failure was reported in this completed run.

**RED evidence boundary (historical):** the two failed frontend startup attempts were infrastructure failures, not RED evidence. Completed backend/frontend runs established the missing endpoint/screen baseline. Later eligibility, display, refusal and stale-data assertions were then unexecuted behind those initial failures; GREEN execution below reaches these assertions. No entire suite was run.

Isolation: plain unittest/Flask/JWT, mocked session and model queries, reused SCRUM-55 `_ReadQuery` (simple predicates only; unsupported query shapes fail loudly). No app factory, `AppTestCase`, engine initialization or SQL execution. Engine/socket connection attempts raise immediately. The module suppresses dotenv loading while importing app code. Frontend API calls are mocked. These tests establish HTTP/UI behavior; they do not prove PostgreSQL query semantics or persistence.

During RED, only the new backend and frontend test files were run. No production edits, schema changes, dependency installations, Supabase/shared database access, commits, pushes or PRs were performed in that phase.

## GREEN execution — 27 Oct 2026

The user authorized only the listing endpoint, simple page/routing, this document and a minimal correction for an objectively incorrect test assumption. No test cases or AC mappings were added or removed.

### Implementation

- `backend/app/events/routes.py`: additive read-only `GET /api/events/safety-checks`; existing JWT guard and stored-user lookup, Safety Officer allowlist before event reads, batched retrieval of confirmed bookings/events/requirements/active reservations/venues. Required quantities are checked per event and requirement. Events appear once with distinct confirmed venues; note-only events are excluded. A dependent retrieval failure rolls back and returns 503/error/`retryable: true` without any list. No event-status filter was added.
- `frontend/src/pages/SafetyCheckQueuePage.jsx`: existing API/error/date utilities; event, venues, Singapore-local dates, expected attendance and equipment; loading/empty/refusal/error states. Refresh/Retry clears old results before loading, so a failure cannot leave the previous list visible.
- `frontend/src/App.jsx`: import, protected static route and a navigation link; no navigation redesign or changes to other pages.

### Exact commands and observed results

From `backend/` (executed twice):

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_check_queue_unit
```

First run: 4 methods, 1 failing authorization subcase, exit 1, 0.066 seconds. The unauthenticated request correctly returned HTTP 401, but Flask-JWT-Extended's existing response contains `msg`, whereas TC-90-03 incorrectly required `error` even for the JWT library's refusal.

**Necessary test correction:** in `backend/tests/test_safety_check_queue_unit.py`, accept a nonempty `msg` only for the missing-JWT subcase (or `error`); other-role refusals must still contain `error`. The expected 401/403 statuses, exclusion of event data and prohibition on event queries are unchanged. No production JWT behavior was modified and no AC assertion was removed.

**Final backend run:** exit 0; **4 methods passed, 0 failures/errors**, 0.063 seconds. All eight authorization subcases passed, together with eligibility, quantities, duplicate prevention, display payload and the injected retrieval failure.

From `frontend/`:

```powershell
npm.cmd test -- src/pages/SafetyCheckQueuePage.test.jsx --reporter=dot
```

Executed outside the filesystem sandbox using the permission path that resolved the RED config-loader access restriction. **Actual:** exit 0; Vitest 2.1.9; **1 file, 3 tests passed, 0 failed**; tests 192 ms, total duration 1.48 seconds. Frontend test file unchanged.

| Cases | Final result |
|---|---|
| TC-90-01 | PASS: exactly E1/E2 qualify from mixed fixtures |
| TC-90-02 | PASS: required information and one row per event |
| TC-90-03 | PASS: missing-JWT and seven other-role refusals |
| TC-90-04 | PASS: injected equipment retrieval failure, rollback and no partial payload |
| TC-90-05 | PASS: route/display/no-equipment/empty states |
| TC-90-06 | PASS: refusal without event information |
| TC-90-07 | PASS: failed refresh clears prior data; initial failure shows error |

### Scope and verification limits

The verbatim Jira story/ACs, TC-90-01 through TC-90-07 and mappings are preserved. A1–A5/Q1–Q5 remain provisional presentation/business assumptions. The explicit no-equipment declaration is still absent from the schema; absence of structured requirements and a blank/null note is the authorized provisional interpretation.

No Supabase, local or remote database connection, migration, schema check, production data access, dependency installation, notification or safety decision workflow was used. Existing SCRUM-76 documentation and unrelated files were not edited. No commits, pushes or PRs were created.

At the original GREEN stage, only the two targeted test files were executed; no broad regression suite was run. Database query execution/persistence, live browser behavior and CI were not verified by those mocked tests. The later PR #58 correction evidence below supersedes that stage's verification scope.

## PR #58 corrections and verification — 27 Oct 2026

### Focused changes

- `backend/app/events/routes.py`: filter cancelled/rejected events and `end_time <= singapore_now()` in SQL; select confirmed bookings only for candidate event IDs and their date range, avoiding irrelevant historical bookings. `_safety_schedule_covered` checks the union of each event's booked periods for complete current schedule coverage. Existing equipment quantities, user authorization and all-or-error response handling remain intact. No approved-only filter or new lifecycle rule is added.
- `frontend/src/pages/SafetyCheckQueuePage.jsx`: reuse the small `loadAttempt` counter from `UnassignedQueuePage`; both success and failure paths ignore superseded responses.
- Extend TC-90-01's mixed unit fixtures rather than adding backend methods; freeze the clock for deterministic past/end-boundary checks. Add only TC-90-08 on the frontend, combining older successes/errors in one method. Add one opt-in PostgreSQL test for actual query/eligibility behavior.

### Exact focused test commands and results

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_check_queue_unit
```

Before the backend fixes, the expanded fixture reproduced one failing method: cancelled, rejected, ended, end-at-now and stale-period events were incorrectly returned. The other three methods passed (0.106 seconds; exit 1).

**Final:** 4 methods passed, 0 failures/errors, 0.063 seconds; exit 0. The final fixture also verifies touching venue phases qualify and a gap does not. The original AC1–AC4 assertions remain intact.

From `frontend/`:

```powershell
npm.cmd test -- src/pages/SafetyCheckQueuePage.test.jsx --reporter=dot
```

First run: Vitest 2.1.9; 1 file, 4 tests passed, 0 failed; test time 347 ms, total duration 55.11 seconds; exit 0. It began while the request-counter change was being applied. The exact command was repeated once after all code/test edits were finished to verify stable files: **4 tests passed, 0 failed; test time 372 ms, total duration 1.67 seconds; exit 0**. No frontend RED failure is claimed for this correction pass.

From `backend/`, explicitly selecting the existing dedicated local database:

```powershell
$env:SCRUM90_LOCAL_TEST_DATABASE_URL='postgresql://connectsphere_test:ci-only@127.0.0.1:5433/trueadams_s90_fresh'
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_safety_check_queue_local
```

Docker inventory and metadata reads confirmed the existing local container `trueadams-test-pg`, loopback port 5433, dedicated database and required columns. No schema creation, migration or rebuild was performed. The test is skipped unless explicitly enabled; before app setup it refuses any target other than that exact loopback host/port/database/restricted-role combination and refuses an app cached for another database.

The first local run reproduced the stale-booking bug against PostgreSQL (1 test, 1 assertion failure, 0.309 seconds; exit 1). After coverage checking and the combined phase/gap fixture were completed, **1 test passed, 0 failures/errors, 0.227 seconds; exit 0**. Fixture rows were rolled back by `AppTestCase`. Existing UTC timestamp deprecation and test JWT key-length warnings were emitted; no unrelated code was changed to address them.

### Scope, limitations and PR housekeeping

All four original ACs and the original seven cases/mappings are preserved. Only the explicitly requested closed/past/schedule coverage and stale-response corrections were made; A6/Q6 records the user-confirmed collective multi-venue coverage rule. This confirmation matches the already verified implementation, so only documentation changed afterward and tests were not rerun. There is no new review persistence, approval/rejection, notification, assignment, schema, dependency, pagination, sorting or general query refactor.

No Supabase or remote/shared database access occurred. Only the dedicated local test database received rolled-back test fixtures; no development/production records or schema were altered. Only the three focused SCRUM-90 test files were executed; no full suite or CI claim is made. No commits, pushes or PR modifications were performed.

`SCRUM-76-authorised-access.md` was left untouched. It should be excluded from PR #58 and submitted separately as a documentation-only change. **READY FOR REVIEW**; the collective-coverage question is resolved.
