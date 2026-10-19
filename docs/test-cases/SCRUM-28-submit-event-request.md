# SCRUM-28 — Submit an Event Request: Test Cases

**User story:** As an Event Organiser, I want to submit an event request containing the information needed for review so that ConnectSphere can assess my proposed event.

**Documentation reviewed:** 19 Oct 2026 against checked-out baseline `9d188f9`. **Current execution status:** not executed in this documentation update. Historical results below are reports from their stated date/build, not fresh verification.

**Converted source:** `SCRUM-28-Test-Coverage-Plan.xlsx`, sheets **Test Case Plan** (TC-28-01–17) and **AC Coverage Summary** (AC1–6, P1–P6, decisions and RED/GREEN evidence). Original Git blob: `3c649a5f58c55955aa35f8834511abe82c72e806`, available in baseline `9d188f9` at `docs/test-cases/SCRUM-28-Test-Coverage-Plan.xlsx`. All meaningful scenarios, IDs, results and limitations are retained here; obsolete assignment expectations are explicitly superseded, not treated as current passes.

**Related requirements:** [SCRUM-29 draft rules](SCRUM-29-draft-event-request.md), [SCRUM-81 unassigned queue](SCRUM-81-unassigned-queue.md), [SCRUM-81 initial assignment](SCRUM-81-lead-assigns-coordinator.md), [SCRUM-55 review](SCRUM-55-review-submitted-event-request.md), [SCRUM-27 permissions](SCRUM-27-authentication-authorization.md).

## Acceptance criteria and traceability

**Requirements source:** authoritative Jira wording supplied by the user in the final reconciliation request, 19 Oct 2026 (no Jira URL supplied). AC wording below is exact; later Coordinator Lead rules are documented separately. No tests were executed during this reconciliation.

| ID | Official Jira acceptance criterion | Test cases |
|---|---|---|
| AC1 | The organiser can enter the event name, purpose, description, proposed date and start/end times, expected attendance, venue requirements, accessibility needs, equipment requirements, and registration needs where relevant. | TC-28-01, 02 |
| AC2 | Before submission, the system checks the information against the agreed required-field and validation rules. | TC-28-03, 04 |
| AC3 | If information is missing or invalid, submission is prevented, the affected fields and necessary corrections are identified, and entered information is retained. | TC-28-03–05, 13; 02/16/17 support input/state protection |
| AC4 | Successful submission saves the request with status Submitted, displays a submission confirmation and unique reference, and makes it accessible to authorised reviewers. | TC-28-02, 08–10; 14–16 support recovery/state integrity; separate SCRUM-81 assignment enables reviewer access |
| AC5 | Repeating the submission action for the same request does not create a duplicate event request. | TC-28-11, 14, 16; 08/09 support same-row submission |
| AC6 | If submission fails, rejection is displayed with reasoning; the organiser is informed and their entered information remains available for retry. | TC-28-05, 12–15, 17; 10 is a later-workflow success boundary, not a failure test |

TC-28-06/07 enforce the story's organiser/session/ownership preconditions; they are supporting security cases, not direct required-field validation tests. AC4's reviewer access follows the later SCRUM-81 handoff described below: successful submission waits unassigned until a Lead assigns a coordinator. The exact Jira criterion is retained without adding automatic-assignment requirements.

## Working assumptions and confirmed repository changes

- **A1 / Q2 — Field/validation rules:** reuse [SCRUM-29 A1–A9 and Q1–Q4](SCRUM-29-draft-event-request.md). Required to submit: title, purpose, description, start, end, expected attendance, venue requirements and explicit registration yes/no. Accessibility and equipment are optional. Only title is needed to save a draft; title max 255, attendance an integer at least 1, start/end valid naive Singapore-local timestamps, registration boolean. End must be after start at submission, even though a draft can save an invalid ordering. These inherited customer questions are not newly resolved here.
- **A2 — Ownership/security:** caller must retain the stored organiser role and own the draft; reuse JWT/current-user handling. No JWT redesign, admin override, new schema or new validation policy.
- **Changed by SCRUM-81:** its queue document AC6, A9 and TC-81-23/24 explicitly withdraw lowest-user-ID assignment and no-coordinator refusal. Current `submit_draft` changes status/time without assigning. New complete drafts therefore remain null in `coordinator_id`, `coordinator_assigned_at`, `coordinator_assigned_by_id`. TC-28-09/10 were renamed in the existing tests to match. The SCRUM-81 queue story is itself marked a team reading of Week 7 change 5; Q5–Q9 there remain open. This document does not upgrade that status to customer sign-off.
- **A3 — Handoff:** `GET /api/events/queue` lists submitted/unassigned events for Leads. `POST /api/events/<id>/assignment` performs initial assignment separately. Only after assignment can that current coordinator review; Lead status alone does not grant coordinator review. Existing previously assigned submissions retain their coordinator under SCRUM-81 A9/Q5.
- **A4 — Duplicate protection:** a repeated submit of a known ID is refused with 409, not a successful idempotent replay. Initial creation whose response/ID is lost remains deferred to SCRUM-29. No content matching, idempotency keys or new reference table were introduced.
- **A5 — Failure semantics:** confirmed commit failure rolls back; a lost COMMIT acknowledgement is 503 with `outcome_uncertain: true`, not a promise that the request is still Draft. The frontend checks the known ID, preserves edits and never infers Draft solely from absence in a list.

## Fixtures and test reference key (SUB-SEED)

Reuse **DR-SEED** in [test_event_drafts.py](../../backend/tests/test_event_drafts.py): dana owns incomplete D1 and complete D2; evan owns D3; S1 is already submitted. `COMPLETE` describes Winter Networking Night, 3 Dec 2026 18:00–21:00 Singapore time, 80 attendees, purpose/description/venue/accessibility/equipment text and registration true. `DRAFT_FIELDS` enumerates all ten fields. Integration cases use `DraftTestCase`/`AppTestCase` transactional fixtures and generated unique emails, not production-data resets.

Submission unit fixtures use event 7, organiser 1, admin 2, former coordinator 3 (attendee), and coordinators 5/9. Persistence is mocked and Engine/socket connections are guarded. The no-coordinator variant changes all fixture coordinators to attendee. Frontend fixtures use existing request ID 7 and mocked API responses in `MemoryRouter`.

| Key | Actual test file / class |
|---|---|
| DRAFT | [test_event_drafts.py](../../backend/tests/test_event_drafts.py); class stated in each reference |
| SUB | [test_event_submission.py](../../backend/tests/test_event_submission.py); `SubmissionUnitTests` |
| STALE | Same file; `SubmissionPersistenceTests` |
| UI | [DraftEventPage.test.jsx](../../frontend/src/pages/DraftEventPage.test.jsx); quoted `it`/`it.each` title |

## Test-case register

All 17 workbook IDs are preserved. “Integration” means an existing database-backed test definition, not an execution performed for this update. All were marked Essential in the workbook. Historical status is kept separately below.

| Test ID | AC | Scenario / Preconditions | Action / Input | Expected Result | Test Type | Automated Test Reference |
|---|---|---|---|---|---|---|
| TC-28-01 | AC1 | Authenticated owner, complete saved D2. | GET draft and compare every `DRAFT_FIELDS` value to `COMPLETE`. | Same ID and all ten saved values, including optional details/registration/Singapore-local times; no missing submission fields. | Integration, reuse | DRAFT `ReopenTests.test_reopening_shows_everything_previously_saved` |
| TC-28-02 | AC1, AC4; supports AC3 | Complete edited form; save held pending. | Fill all ten inputs; Submit for review; resolve save then submit. | Current values in save body; busy controls protect in-flight edits; visible confirmation `Request #7`; Submitted form is read-only. | Component, extended | UI `saves the current edits, then submits, and shows the request as Submitted` |
| TC-28-03 | AC2, AC3 | Owner, D1; valid saved-state snapshot. | Save wrong kinds, unknown fields/non-JSON, 255/256-character title; forge organiser/coordinator/status. | 400 naming field where applicable, saved values unchanged; title 255 accepted/256 refused. No protected-field changes. | Integration, extended | DRAFT `SaveIncompleteTests.test_values_of_the_wrong_kind_are_refused`, `SaveIncompleteTests.test_an_event_name_is_required` |
| TC-28-04 | AC2, AC3; supports AC4 | Incomplete D1/complete D2. | Submit incomplete; clear optional details; save repeatedly; try end equal/before/one minute after start. | 400 with missing labels or end field; no transition on refusal. Optional nulls allowed. Saving alone stays Draft; invalid ordering can save but cannot submit. | Integration, reuse | DRAFT `SubmissionTests.test_an_incomplete_draft_cannot_be_submitted`, `SubmissionTests.test_optional_fields_are_not_needed_to_submit`, `SubmissionTests.test_end_must_be_after_start_to_submit`, `SubmissionTests.test_saving_never_submits` |
| TC-28-05 | AC3; supports AC6 | Save succeeds; submit reports missing fields. | Edit Purpose and submit. | Missing-field labels shown; purpose retained; Draft remains editable. No new highlighting requirement. | Component, reuse | UI `lists the missing fields when submission is refused, and stays a Draft with the edits kept` |
| TC-28-06 | Story access precondition | Missing/expired/deleted-user token; unknown event ID. | Direct draft open/save/submit requests. | Invalid session 401; missing record with valid session 404; saved draft unchanged. Malformed-token coverage is SCRUM-27. | Integration, reuse | DRAFT `SaveIncompleteTests.test_a_valid_session_is_required`, `ReopenTests.test_unknown_draft_returns_not_found` |
| TC-28-07 | Story access precondition | Another owner, coordinator, admin, attendee, venue/tech staff; original owner token after stored role changes. | Open/save/submit another owner's draft; additional role and stale-owner-token submit probes. | 403 without private details for covered probes; no draft change; stored organiser role plus ownership required. | Integration, extended | DRAFT `ReopenTests.test_another_users_draft_cannot_be_opened_saved_or_submitted` |
| TC-28-08 | AC4; supports AC5 | Owner, complete D2; snapshot ID/count/details. | Submit same draft; inspect response, stored row and drafts list. | 200, same ID/count, submitted status/time, details unchanged, removed from draft list. Assignment handoff is TC-28-09. | Integration, extended | DRAFT `SubmissionTests.test_submitting_a_complete_draft` |
| TC-28-09 | AC4; supports AC5 | Complete owned unassigned draft, coordinators available. | Submit; try direct review as owner/admin/available coordinators; inspect Lead queue in supplementary integration case. | 200, same ID/details, `submitted`, all three assignment fields null, one commit and no added row/reservation in unit mock; all tested review callers get 403 without title. Persisted request is visible in Lead queue. **Replaces automatic assignment.** | HTTP unit; supplementary integration | SUB `SubmissionUnitTests.test_submission_leaves_the_request_unassigned_and_preserves_access_boundaries`; [test_unassigned_queue.py](../../backend/tests/test_unassigned_queue.py) `SubmissionTests.test_a_submitted_request_waits_in_the_queue_without_a_coordinator` (TC-81-23) |
| TC-28-10 | AC4; later-workflow boundary | Complete owned draft; no fixture user has coordinator role. | Submit. | 200 Submitted, coordinator remains null, commit once; submission does not depend on a coordinator. **Replaces no-candidate 503/refusal/retry.** | HTTP unit | SUB `SubmissionUnitTests.test_submission_does_not_need_an_available_coordinator` (also TC-81-24) |
| TC-28-11 | AC5; supports AC4 | S1 and a real D2 submit transition; two separately created identical drafts. | Reopen/save/resubmit non-draft; submit D2 twice; submit each new identical request ID. | Existing non-draft 409; repeated D2 submit preserves full snapshot/count; separate identical IDs both submit and owner count increases by two. | Integration, extended | DRAFT `ReopenTests.test_submitted_request_cannot_be_reopened_as_a_draft` |
| TC-28-12 | AC6; supports AC4 | Complete D2; commit fails before successful acknowledgement. | Submit with failing commit, inspect full stored snapshot, restore commit and retry same ID. | 503/retryable; original draft/details/audits/assignment unchanged; recovery submits same ID without extra event. | Integration, extended | DRAFT `SaveFailureTests.test_failed_submission_leaves_the_draft_as_a_draft` |
| TC-28-13 | AC3, AC6 | Prerequisite save succeeds; submit returns end-time 400 or pre-commit 503. | Submit, inspect values/alert, correct end or recover and retry. | Useful explanation, all current values retained, controls recover, same ID saved/submitted on retry. | Component, two variants | UI `retains request details after submit rejection and retries the same request (%s)` |
| TC-28-14 | AC5, AC6; supports AC4 | Known saved ID 7; submit response lost; subsequent outcome submitted/draft/unavailable. | Check owner-scoped draft GET; after 409 inspect owner `/events/mine`; retry/check status as appropriate. | Confirmed non-draft shows reference/current status and blocks edits, preserving newer unsaved edits. Confirmed Draft retries only ID 7. Unknown outcome keeps inputs and check-only guidance, no extra submit/create; absent list entry never proves Draft. | Component, three variants | UI `reconciles uncertain submission outcomes without creating another request (%s)` |
| TC-28-15 | AC6; supports AC4 | Mock commit succeeds then ORM reads fail; separate lost-acknowledgement fault. | Public submit route; disable later column reads; then inject invalidated COMMIT connection. | Success has primitive ID/status/time without post-commit reads or false failure/rollback. Lost acknowledgement returns honest 503/retryable/`outcome_uncertain` and calls rollback. No database durability claim. | HTTP unit, fault subcase | SUB `SubmissionUnitTests.test_successful_submission_survives_post_commit_read_outage` |
| TC-28-16 | AC4, AC5; supports AC3 | Cached Draft object; underlying row already changed to Submitted with coordinator/time in same fixture transaction. | Try stale draft PUT then submit through public routes. | 409; stored submitted status/time/coordinator/assignment time and original description survive. Workbook also expected count/no-second-event; **current method does not assert row count** (G2). | Integration | STALE `SubmissionPersistenceTests.test_stale_draft_cannot_overwrite_submitted_request` |
| TC-28-17 | AC3, AC6 | Prerequisite save returns 400/503/network failure. | Submit current edits or retry failed save. | Explanation, edits/last-saved time retained; no submit POST after failed prerequisite save; retry saves same draft. | Component, reuse | UI `keeps the edits and the last-saved time when saving fails (%s), and saves on retry`, `does not submit when saving the edits first fails` |

## Implementation traceability

All event API routes below live in [backend/app/events/routes.py](../../backend/app/events/routes.py). Frontend uses [DraftEventPage.jsx](../../frontend/src/pages/DraftEventPage.jsx), the shared [API client](../../frontend/src/api/client.js), and existing [App routes](../../frontend/src/App.jsx).

| Cases | Route/function/component |
|---|---|
| 01–08, 11–13, 16–17 | `POST /api/events/drafts` → `create_draft`; `GET/PUT /api/events/drafts/<id>` → `get_draft`/`save_draft`; `POST /api/events/drafts/<id>/submit` → `submit_draft`. `_own_draft` checks current user, record, owner/role and Draft; writes request a refreshed row lock. `_parse_draft`/`_parse_draft_value`, `DRAFT_FIELDS`, `REQUIRED_FOR_SUBMISSION`, `_draft_payload` define validation/serialization. |
| 02, 05, 13–14, 17 | `DraftEventPage` `FIELDS`, `toForm`, `toBody`, `persist`, `handleSubmit`, `checkSubmission`, `confirmSubmission`: save-before-submit, input retention, busy controls, ID receipt and same-ID reconciliation. `GET /api/events/mine` → `list_mine` supplies the owner-scoped non-draft receipt. |
| 09–10 | `submit_draft` sets submitted status/time only. `GET /api/events/queue` → `list_queue`, `_waiting_for_assignment`; `POST /api/events/<id>/assignment` → `assign_from_queue` performs SCRUM-81 assignment separately. `review_request`/`_assigned_request` refuse unassigned coordinator review. |
| 12, 15 | `_commit_draft_payload` snapshots primitive fields before commit (creation flush obtains ID); invalidated COMMIT connection reports uncertain outcome; confirmed submit failure rolls back in `submit_draft`. |

Separate handoff evidence: [test_lead_assign_coordinator.py](../../backend/tests/test_lead_assign_coordinator.py) `AssigningTests.test_assignment_records_the_coordinator_the_lead_and_the_time`, and [test_unassigned_queue.py](../../backend/tests/test_unassigned_queue.py) `LeavingTests.test_an_assigned_event_leaves_the_queue`. Assignment/notifications remain SCRUM-81's responsibility. Downstream full detail coverage remains [test_event_decisions.py](../../backend/tests/test_event_decisions.py) `WhoAndWhenTests.test_coordinator_opens_the_full_request_to_review_it`; it no longer proves an automatic submission handoff.

## Historical execution evidence (not rerun)

Source: converted workbook **Test Case Plan O6:Q22** and **AC Coverage Summary A25:H50**, recorded GREEN on **14 Oct 2026**. It reports **18 distinct targeted passes: 3 backend unit methods and 15 draft-page instances**; no GREEN database test or full regression suite. Temp JSON paths below were recorded by the workbook; their files/results have not been independently revalidated.

The workbook's historical AC assessment was **AC1/AC3 Covered**, **AC2/AC4/AC5/AC6 Partially Covered**. It cited pending real-database round-trip/validation/state/rollback checks, assignment/status atomicity and stale-state/concurrency guarantees. Those labels belong to that audit and its old assignment rule, not a current execution verdict. Existing form entry, missing-field/time corrections and retry interactions had mock-backed evidence; no broader verification was inferred.

| Workbook cases | Recorded latest status on 14 Oct | Meaning / current limitation |
|---|---|---|
| 02, 05, 13, 14, 17 | Pass (part of 15 UI instances) | Full-field body, receipt, busy protection, missing/end-time/server messages, save/submit retention, same-ID recovery and newer-edit retention passed with mocked API. |
| 09, 10, 15 | Pass (3 unit methods) | 09 then selected lowest-ID eligible coordinator and checked review access; 10 then returned retryable 503 with unchanged Draft and later same-ID retry; 15 covered response snapshot and lost acknowledgement. **09/10's old results do not verify their new queue expectations.** |
| 01, 03, 04, 06, 07, 08, 11, 12 | Not run in that RED/GREEN exercise | Existing reuse plus five extended backend methods (03/07/08/11/12) remained unexecuted there. Do not interpret source coverage as a pass. |
| 16 | Blocked at setup | One restricted-DB attempt hit sandbox TCP permission denial before fixtures/assertions; no GREEN retry. Not evidence of an expected product failure. |

Execution commands are preserved for provenance only, not instructions executed during this update. Backend commands were from `backend/`, frontend commands from `frontend/`.

| ID | Exact recorded command |
|---|---|
| B1 | `.\.venv\Scripts\python.exe -B -m unittest -v tests.test_event_submission.SubmissionUnitTests` |
| B2 | `.\.venv\Scripts\python.exe -B -m unittest -v tests.test_event_submission.SubmissionUnitTests.test_successful_submission_survives_post_commit_read_outage` |
| B3 | `$env:PGCONNECT_TIMEOUT = '5'; .\.venv\Scripts\python.exe -B -m unittest -v tests.test_event_submission.SubmissionPersistenceTests.test_stale_draft_cannot_overwrite_submitted_request` |
| F1 | `npm test -- src/pages/DraftEventPage.test.jsx --reporter=verbose --reporter=json --outputFile=C:/Users/Mikhail/AppData/Local/Temp/scrum28-frontend-red.json` |
| F2 | `npm.cmd test -- src/pages/DraftEventPage.test.jsx --reporter=verbose --reporter=json --outputFile=C:/Users/Mikhail/AppData/Local/Temp/scrum28-frontend-red.json` |
| F3 | `npm.cmd test -- src/pages/DraftEventPage.test.jsx --testNamePattern 'saves the current edits\|reconciles uncertain submission' --reporter=json --outputFile=C:/Users/Mikhail/AppData/Local/Temp/scrum28-frontend-red-corrected.json` |
| F4 | `npm.cmd test -- src/pages/DraftEventPage.test.jsx --reporter=json --outputFile=C:/Users/Mikhail/AppData/Local/Temp/scrum28-frontend-green.json` |
| F5 | `npm.cmd test -- src/pages/DraftEventPage.test.jsx --testNamePattern 'reconciles uncertain submission' --reporter=json --outputFile=C:/Users/Mikhail/AppData/Local/Temp/scrum28-reconciliation-green.json` |

The command table contains literal title alternatives in F3; these are part of the historical Vitest pattern.

| Historical execution | Pass / fail / error / skipped | Preserved observation |
|---|---|---|
| RED B1, twice | 0 / 3 / 0 / 0 each | Same expected assertions on both runs; latest duration 0.031 s. Engine/socket guards, no database. |
| RED F1 launch | No cases collected | PowerShell npm.ps1 execution-policy failure; switched to npm.cmd without changing policy. |
| RED F2 sandbox launch | No cases collected | esbuild configuration access denied; workbook records authorised execution outside sandbox. |
| RED F2 collected run | 11 / 4 / 0 / 0 | Success extension initially had an ambiguous status-role selector; corrected test setup, not attributed to missing production behavior. |
| RED B3 | 0 / 0 / 1 / 0 | Connection denied during setup, no assertions; no repeat. |
| RED F3 corrected selection, twice | 0 / 4 / 0 / 11 each | Four expected production-gap failures after selector correction; other 11 cases excluded. |
| Distinct latest RED cases | 11 / 7 / 1 / 0 | 3 unit + 15 frontend cases + 1 blocked integration attempt counted once, not rerun totals. Backend reuse/five extensions unexecuted. |
| GREEN B1 | 3 / 0 / 0 / 0 | Old assignment/no-candidate rules plus response-read safety passed; isolated mocks only. |
| GREEN F4 | 15 / 0 / 0 / 0 | All page cases passed; entire frontend suite not run. |
| GREEN B2 focused recheck | 1 / 0 / 0 / 0 | Additive unknown-COMMIT-acknowledgement subcase; original assertions retained. |
| GREEN F5 focused recheck | 3 / 0 / 0 / 12 | Additive newer-unsaved-edit retention assertion; other page cases filtered out. |
| Distinct latest GREEN cases | 18 / 0 / 0 / 0 | 3 unit + 15 frontend; focused rechecks are not additional distinct passes. No successful database connection/attempt in GREEN. |

**Later change evidence:** [SCRUM-81-unassigned-queue.md](SCRUM-81-unassigned-queue.md) reports 17 Oct 2026 local PostgreSQL + Vitest passes, with Supabase pending, and explicitly identifies updated TC-28-09/10. Its TC-81-23/24 map to the new submission/queue behavior. This is a later narrative execution record, not a per-method raw log or fresh run. The separate initial-assignment document reports local PostgreSQL/Supabase/Vitest passes on 17 Oct; that does not resolve the queue document's separately pending Supabase status.

## Preserved implementation/decision history

These were workbook GREEN changes, not changes made by this documentation task. Original assertions were retained; the two additive fault/retention extensions were rechecked. Backend seed fixtures already supplied coordinators and did not need changes.

| Workbook item | Historical correction / classification | Current disposition |
|---|---|---|
| P1 | `DraftEventPage.handleSubmit`/receipt displays existing `Event.id` as `Request #<id>`; no schema/reference mechanism. | Retained, TC-28-02. |
| P2 / D1 | `submit_draft` selected lowest-ID current coordinator; no candidate meant retryable 503 before mutation; assignment/status/time shared commit. No workload/advanced assignment or role override. | **Superseded by SCRUM-81 AC6/A9**, TC-28-09/10. Historical passing assertions are archived above, not current expectations. |
| P3 / D2 | Known-ID lost-response recovery via owner draft GET, then owner mine list after 409; non-draft receipt blocks edits; unknown outcome exposes status-check-only action. | Retained, TC-28-14. Lost initial-create ID idempotency remains deferred to SCRUM-29; no keys/tables/columns/migrations. |
| P4 | Shared create/save/submit snapshot helper avoids false failure from expired ORM reads after commit; flush on creation obtains ID; invalidated connection reports uncertainty. Pattern followed existing decision response safety. | Retained, TC-28-15; rollback behavior covered separately by 12 and save regressions 17. Mocks do not prove durability. |
| P5 | Busy/non-draft controls prevent an in-flight response from overwriting edits; controls recover on failure. No parallel page or generic retry framework. | Retained, TC-28-02. Relaxed draft saving unchanged. |
| P6 | Fresh locked/identity-map-refreshed event read before draft writes prevents stale Draft checks; keeps 409 contract, may wait on competing writers. | Retained, TC-28-16. Single-session stale-state assertions are not proof of concurrent transaction scheduling. |

The workbook's GREEN production scope was only `backend/app/events/routes.py` and `frontend/src/pages/DraftEventPage.jsx`. It recorded broader VERIFY as separately authorised but not started: stale-state plus the five backend extensions first, then affected authorisation/draft/review/reassignment regressions. That statement is historical, not a request to run them now. Creation-idempotency keys, new request/reference tables, advanced assignment, booking/reservation behavior, new validation policies, new pages/endpoints for SCRUM-28, schema changes and broad regression infrastructure remained excluded/deferred; later SCRUM-81 endpoints are a separate story.

## Coverage gaps and open questions

| ID | Gap / unresolved question | Effect |
|---|---|---|
| Q1 (resolved) | Official Jira story and all six exact criteria supplied on 19 Oct 2026. | Replaces the earlier workbook-summary wording; existing IDs, historical results and separate Lead-workflow interpretation are retained. |
| Q2 | SCRUM-29 field/required-field assumptions and SCRUM-81 Q5–Q9 remain open in their source documents. | Preserve those assumptions; do not present them as newly agreed here. |
| G1 | No tests run for this update; historical mock/partial results do not establish current database, transaction, RLS or full regression status. | 14 Oct five extensions/stale-state pending status retained; later queue report is scoped separately. |
| G2 | Workbook TC-28-16 expected unchanged count/no second event, but its actual method asserts stored fields, not row count. It simulates stale state in one transaction rather than real concurrent requests. | Explicit assertion/coverage limitation; count invariants do have separate TC-28-08/11 coverage. No test modification made. |
| G3 | TC-28-10 uses in-memory users, not a real zero-coordinator database fixture. | Unit coverage exists for no-coordinator success; PostgreSQL execution of that precise variant is not established by the method. |
| G4 | Lost first-create response without a known ID remains outside same-request duplicate protection. | Deferred SCRUM-29 scope; known-ID reconciliation must not be described as creation idempotency. |
| G5 | Existing source comments still name the removed workbook in `test_event_submission.py` and `DraftEventPage.test.jsx`. | Historical pointers now resolve through this conversion/provenance note. Automated tests were deliberately not edited. |

## Course alignment and conversion check

Read [Week2-UserStories.pdf](../../Slides%20+%20Docs/Week2-UserStories.pdf), printed slides 27/34/44/67 (PDF pages 25/28/38/60) and Given–When–Then at PDF page 27. Read the relevant test-design pages in the exact Week 4 file, [Week4-TestCases_SoftwareArchitecture.pdf](../../Slides%20+%20Docs/Week4-TestCases_SoftwareArchitecture.pdf), especially pages 21–24 and 26–32: specific inputs/conditions/actions/results, positive/negative/boundary selection, reuse of cross-cutting checks and separate execution evidence. Page 23 describes the template as one useful representation, not a mandatory Excel format.

Both workbook sheets were read during conversion, including the execution and P1–P6/decision notes. TC-28-01–17 are preserved; the workbook AC summaries have now been reconciled to the exact six Jira criteria supplied on 19 Oct 2026. Historical pass/not-run/blocked records, commands, selector/launch issues and deferred scope remain distinct from current expectations. The 19 Oct update uses static reference/link review only; it does not claim a fresh GREEN result.
