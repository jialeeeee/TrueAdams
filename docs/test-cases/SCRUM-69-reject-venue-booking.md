# SCRUM-69 — Reject a Pending Venue Booking Request: Audit and Test Cases

**Title:** Reject a pending venue booking request

As a Venue Staff member,
I want to reject a pending venue booking request with a reason
so that the Event Coordinator knows the proposed venue arrangement cannot proceed and why.

**Source:** SCRUM-69, Jira story and acceptance criteria supplied by the user; no Jira URL was supplied.

**Created / RED / GREEN:** 21 Oct 2026 | **Branch:** `feature/SCRUM-69-reject-venue-booking-request` | **Current status:** GREEN complete. All 20 SCRUM-69 backend methods (18 original plus 2 authorised request-history checks), 92 existing venue regressions, 7 app-factory checks and 42 frontend instances pass. Only the local Docker database received the additive migration. Supabase was not accessed. Phase 4 records the current implementation, commands and hand-off; earlier audit/RED sections are historical evidence.

**Related:** [SCRUM-39 requests](SCRUM-39-venue-booking-request.md), [SCRUM-40 approval](SCRUM-40-approve-venue-booking.md), [SCRUM-87 holds](SCRUM-87-tentative-venue-hold.md), [repository conventions](../../AGENTS.md).

## Acceptance criteria (verbatim)

- **AC1:** Venue Staff can view pending requests, including the event, venue, requested date, start/end times, and venue requirements.
- **AC2:** Only a request currently in Pending status can be rejected.
- **AC3:** Venue Staff must give a reason (not blank, at most 500 characters) when rejecting
- **AC4:** The rejection and reason are saved with the decision and visible to the Event Coordinator.
- **AC5:** A rejection does not create a booking.
- **AC6:** The coordinator is notified of the rejection and the reason.

## Phase 1 — Read-only audit (historical snapshot)

Statuses describe production code present on this branch, not completed rejection functionality. Phase 1 inspected source only and created this document. Phase 3 below records the subsequent authorised RED-only test changes and execution; it supersedes earlier Planned/Not run labels only for the exact automated checks listed. An existing helper or test for another decision does not establish that rejection works.

### Database representation and existing flows

- [VenueBooking](../../backend/app/models.py) maps to `public.venue_bookings`. A pending request is already a row in that table. `request_booking()` in [venues/routes.py](../../backend/app/venues/routes.py) inserts that row with `status="pending"`; `approve_booking()` updates the same row to `confirmed` and sets `Event.venue_id`. There is no separate request table or confirmed-booking model to introduce for SCRUM-69.
- The status is a `String(20)`, not an enum in the checked-in model or SQL. `rejected` is already used in scheduling comments and seeded tests, but there is no user-facing venue rejection operation. `decided_at` and `decided_by_id` already exist; no booking rejection-reason column exists in the model or checked-in SQL.
- The pending unique index applies only to `status='pending'`. The overlap exclusion constraint applies only to `status='confirmed'`. [scheduling.py](../../backend/app/venues/scheduling.py) selects confirmed bookings and, separately, unexpired `tentative` holds. Rejected requests are excluded by both filters.
- An expired hold remains `tentative`; expiry does not return it to `pending` (SCRUM-87 A9). Rejecting a hold would be a separate state transition and is not authorised by AC2.
- This is a repository audit of models and SQL scripts, not an inspection of the live Supabase schema or data. Whether existing scripts have been applied is unverified.

### AC audit

| AC | Status | Evidence in this branch | Precise gap | Proposed minimal change |
|---|---|---|---|---|
| AC1 | Implemented | `GET /api/venues/bookings`, `list_booking_requests()` and `_booking_payload()` return pending rows with event, venue, requested start/end dates and times, and requirements. `BOOKING_REVIEWER_ROLES={"venue_staff"}` and `_require_viewer()` enforce the stored role. `VenueBookingRequestsPage.jsx` displays these values in Singapore time. Existing `SavedAndVisibleTests.test_venue_staff_see_pending_requests`, `test_only_venue_staff_can_list_requests`, and frontend `lists each pending request with what Venue Staff need to assess it` cover the viewing flow. | No SCRUM-69 viewing functionality is missing. Existing list failures also cover payload reads and availability/conflict reads with 503 instead of a misleading empty or clear list. | Reuse unchanged. Add rejection controls to this page for AC2/AC3, without changing the list contract. |
| AC2 | Missing | `approve_booking()` and `place_hold()` lock and refresh the request row and refuse non-pending states; their tests cover those decisions only. The route inventory contains create/list, approve, and hold operations, but no rejection endpoint. | No rejection operation, Pending-only rejection guard, or rejection-specific authorisation exists. Other decisions' guards are patterns, not partial execution of rejection. | Add a local rejection route in `backend/app/venues/routes.py`, with stored-role authorisation, a refreshed row lock, and an explicit `pending` guard. Add Reject to the existing staff page. Preserve approval/hold behaviour. |
| AC3 | Missing | No venue rejection reason control, validator, or 500-character constant exists. The event rejection parser in `backend/app/events/routes.py` is for a different story and uses `MAX_DECISION_WORDS=1000`. | Missing, null, blank, whitespace-only, wrong-type and over-limit reasons are not validated for venue rejection. | Add a venue-local character validator and named 500-character constant; add a labelled reason field and matching frontend validation in `VenueBookingRequestsPage.jsx`. Do not change or reuse the event decision's word limit. |
| AC4 | Partially Implemented | `VenueBooking.decided_at` and `decided_by_id` can be reused. `_booking_payload()` supplies request context but no decision or reason. Coordinator `GET /api/events/<id>/planning` / `_planning_payload()` exposes the event and confirmed venue, not booking decisions. `VenueBookingRequestPage.jsx` shows only its in-memory submission receipt or the confirmed venue. The recipient-scoped notification API exists, but `App.jsx` has no notification page and these coordinator pages do not fetch notifications. | There is no saved venue rejection/reason or coordinator-facing rejection display. Audit columns alone do not satisfy AC4. | Add a nullable rejection-reason column to the existing booking model plus a new SQL script; save status/reason/decision metadata together. Under A4, show saved rejection notifications on the existing coordinator venue-request page using `GET /api/notifications/`; no planning payload change or new page is needed. |
| AC5 | Partially Implemented | Status-filtered `blocking_bookings()` / `unexpired_holds()` already exclude rejected rows; the confirmed-only DB exclusion constraint is compatible. Approval's `test_bookings_that_are_not_confirmed_do_not_conflict` seeds rejected rows and demonstrates existing conflict behaviour. SCRUM-39 `test_pending_request_does_not_block_the_venue` checks the starting state. | There is no rejection flow whose lack of confirmation, reservation, event mutation, or extra booking creation can be verified. Existing seeded statuses do not exercise rejection. | Update the existing request row to rejected, without inserting another booking/hold or setting the event venue. Add focused integration assertions; no scheduling change is indicated. |
| AC6 | Missing | `Notification`, `GET /api/notifications/`, `_queue_coordinator_email()` and `tasks.send_notification_email` exist. Approval and hold routes save their notification in the decision transaction, then queue email; their tests cover success, save failure and queue failure. | Nothing emits a venue rejection notification, includes its reason, or targets the current coordinator for this outcome. Infrastructure alone does not satisfy AC6. | In the rejection route add a rejection-specific notification message/kind for the current coordinator in the same transaction, then call the existing email helper after commit. Reuse the notification API and task unchanged; expose the saved message as described for AC4. |

### Minimal implementation inventory (recommendations, not changes made)

| Area | Exact proposed files | Purpose |
|---|---|---|
| Backend | `backend/app/venues/routes.py` | Add `POST /api/venues/bookings/<id>/reject`; local JSON/reason validation; authorisation; row lock and Pending-only transition; reuse decision fields; build payload and notification before the single commit; rollback on any dependent SQLAlchemy failure. Do not call approval/hold conflict checks or set `Event.venue_id`. |
| Model/schema | `backend/app/models.py`; new `backend/db/venue_booking_rejections.sql` | Add nullable `VenueBooking.rejection_reason` text; existing non-rejected rows remain valid. Reuse decision timestamp/staff columns. No new model, table, service or status enum migration is indicated by repository evidence. |
| Frontend — staff | `frontend/src/pages/VenueBookingRequestsPage.jsx` | Add per-request reason and Reject controls, 500-character validation, success removal/reload, server errors and input-preserving retries. Reuse `apiClient`, `decide()`, `explain()` and existing rendering where suitable. |
| Frontend — coordinator | `frontend/src/pages/VenueBookingRequestPage.jsx` | Under A4, load the caller's saved rejection notifications and display those matching this event, newest first, with full reason and request context. Keep existing submission/confirmed-venue flows. Do not infer rejection from an unset event venue. |
| Notifications | Rejection additions in `backend/app/venues/routes.py` only | Reuse `Notification`, `backend/app/notifications/routes.py`, `_queue_coordinator_email()` and `backend/app/tasks.py` unchanged. Include the reason in both in-app and email bodies. |
| Backend tests — later | New `backend/tests/test_venue_booking_rejection.py` | Automate the planned rejection cases using `AppTestCase`, existing seed data and fixture patterns. No duplicated pending-list tests. |
| Frontend tests — later | Extend `frontend/src/pages/VenueBookingRequestsPage.test.jsx` and `frontend/src/pages/VenueBookingRequestPage.test.jsx` | Cover new controls, boundaries, retained input, saved coordinator visibility and existing page-flow regressions. |
| Documentation — this phase | `docs/test-cases/SCRUM-69-reject-venue-booking.md` only | This audit and proposed tests. |

The proposed reject endpoint is new because none of the existing venue write endpoints accepts a rejection decision. The proposed coordinator display deliberately uses an existing read API. A separate booking-history endpoint or notification screen is not demonstrated necessary. These choices await approval (Q3).

**Schema hand-off for a later implementation:** the new script must be idempotent, wrapped in `begin; ... commit;`, and name SCRUM-69 and `VenueBooking` in its header. The project owner must run it in the Supabase SQL editor before merging the model change; agents cannot run it. No new table means `test_role.sql` does not need to be re-run. Do not edit the previously applied SCRUM-39/40/87 scripts. The existing `test_database_tables_match_the_models` will check the new field once implementation is authorised; no live-schema match is claimed here.

## Working assumptions and adopted implementation choices (not additions to the ACs)

The six ACs above are unchanged. GREEN adopts the existing staff scope, repository error order and minimal validation choices below; these are implementation choices, not additional customer-agreed ACs. The GREEN instruction resolves Q3 by requiring independent recovery from request records. Other broader draft variants remain explicitly deferred.

- **A1 — Staff scope:** use the existing `BOOKING_REVIEWER_ROLES={"venue_staff"}` rule. Admins and coordinator leads do not inherit Venue Staff powers, and staff are not assigned individual venues in this model. *(Q1)*
- **A2 — Reason representation:** require a JSON object with a text `reason`; trim surrounding whitespace, reject an empty result, and count the trimmed string's Unicode code points, not words or bytes. Preserve internal whitespace. Set a venue-local `MAX_REJECTION_REASON_LENGTH=500` and a frontend constant with a matching comment. Use compatible counting in Python and JavaScript; JavaScript `.length` alone counts UTF-16 units for some characters. Do not silently truncate. Only `reason` is used by this route; other body keys never alter request details. Strict unknown-key refusal remains an unimplemented draft variant, not an AC requirement. *(Q2)*
- **A3 — Decision semantics:** update the existing request to `rejected`, retain its identity and original request details, save `rejection_reason`, reuse `decided_at` (naive UTC) and `decided_by_id`. Leave Event and other bookings/holds unchanged. Rejecting needs no availability check and is allowed for a pending request even if its event was cancelled, its time has started, or its slot now clashes; approval-only restrictions are not automatically requirements for rejection. Non-pending requests, including unexpired and expired tentative holds, remain ineligible. *(Q4)*
- **A4 — Visibility and channels:** notify the event's current assigned coordinator, rather than necessarily `requested_by_id`, using one in-app notification of proposed kind `venue_booking_rejected` and an email queued afterwards. The message identifies the rejection, full reason, event, venue, requested period and deciding staff member. The existing coordinator venue-request page recovers saved decisions from `GET /api/venues/bookings?event_id=<id>`, authorised against the current coordinator. It does not read notifications to recover decisions. Historical rejections are labelled as previous venue decisions alongside any later confirmed venue or new request receipt. No organiser/staff copy is assumed. Email queue failure is non-fatal and reported as `email_queued: false`; queueing is not proof of delivery. *(Q3)*
- **A5 — Missing coordinator or legacy request context:** because `event_id` and `Event.coordinator_id` are nullable, a pending legacy row could lack an event or a current coordinator. Provisionally refuse such a rejection with 409 and an actionable message, changing nothing, until notification can be addressed; a failed database read is instead 503, never treated as missing data. Do not copy existing approval/hold dereferences that assume these rows exist. *(Q5)*
- **A6 — Error order:** follow the supplied repository rule for the new rejection route: 401 valid stored user → 404 request exists → 403 Venue Staff → 400 body/reason → 409 state. SCRUM-40/87 documentation and routes instead check role before request lookup, and approval checks state without input validation. GREEN follows AGENTS.md for the new route and leaves the existing approval/hold order untouched. In either order, 403 responses contain no event, venue, reason or coordinator details. *(Q6)*
- **A7 — Consistency:** lock and refresh the booking row before validating its current status so rejection, approval and hold decisions serialize on that request. Save decision and notification once, atomically; read values needed by the response and email before commit. Handle SQLAlchemy read/flush/commit failures with rollback and 503 `retryable: true`; queue email only after a successful commit. Sequential retry after success returns 409, preserves the first decision and sends no additional notification. *(Q7)*

## Implemented endpoints under test

- `POST /api/venues/bookings/<id>/reject` with `{"reason": "Venue unavailable for the proposed arrangement."}`.
- **200:** `{"message", "booking": <existing request payload plus rejection_reason, decided_at, decided_by>, "notification": {"in_app": true, "email_queued": bool}}`; booking status is `rejected`.
- **400:** `{"error", "field": "reason"}` for invalid reasons; a plain JSON/body error for a malformed or non-object body. Additional keys are not used to change request fields.
- **401 / 403 / 404:** invalid session / denied role / unknown request, using A6 for the new rejection route.
- **409:** non-pending request (`reason: "not_pending"`); missing required request/coordinator context under A5 (distinct actionable message).
- **503:** `{"error", "retryable": true}` for dependent database failures, with nothing saved or queued.
- Existing reads reused: staff `GET /api/venues/bookings` without an event filter retains its pending-list contract. `GET /api/venues/bookings?event_id=<id>` returns this event's request rows, newest first, with saved reason and decision metadata; only its current coordinator may read them (401/404/403, 400 for malformed event ID, 503 retryable on database failure). No separate page or planning-payload change was needed. The existing recipient-scoped notification API remains available separately.

## Seed data (VR-SEED)

For later automated tests, create fresh test-owned rows inside `AppTestCase`'s rolled-back transaction. Never clear/reset shared Supabase tables or assume they are empty. Assertions must filter by this case's event, booking and recipient IDs.

Reuse `backend/tests/seed_data.py`, `AppTestCase.seed_users`, `seed_venues`, `make_user`, `make_event`, `auth_headers`, `missing_id` and the unique email handling already provided. Reuse SCRUM-40 `ApprovalTestCase` fixture/helper patterns (`add_booking`, `stored`, `notifications_for`) where useful without modifying its existing tests. Patch `tasks.send_notification_email.delay` so future tests send no real email. RED/GREEN reuse the existing fixture; the GREEN ownership check creates one coordinator lead via `make_user`, since VA-SEED's `USERS` does not include the separately defined lead seed set.

| Ref | Data |
|---|---|
| Users | gus (Venue Staff), alice and ben (coordinators), dana (organiser), hana (tech staff), farah (attendee), admin and lena (coordinator lead); an extra Venue Staff user for competing decisions. |
| Venues | `fully_recorded` = Aurora Ballroom; `recorded_as_none` = Civic Hall, from the existing seed data. |
| E1 | Approved Harbour Lights Festival, organised by dana, assigned to alice, expected attendance 250, venue unset. |
| E2 | Approved Winter Networking Night, organised by dana, assigned to ben, venue unset. |
| P1 | Existing pending request for E1 at Aurora Ballroom, 12 Mar 2027 16:00–22:30 Singapore time; requested by alice; requirements `Open-air waterfront space for 250, stage power`; setup 30 minutes, turnaround 15 minutes. |
| P2 | Existing pending request for E2 at Civic Hall, 3 Apr 2027 17:00–21:30 Singapore time; requested by ben. |
| R1 | Ordinary valid reason: `The required stage power cannot be provided for this arrangement.` |
| Clock | Fix Singapore now to 1 Mar 2027 12:00 for hold/started-time variants, using the existing local-time mocking pattern. Decision audit times remain naive UTC. |

Only cases that require other statuses create them. Create tentative rows with hold metadata as SCRUM-87 does, using future and expired expiries. Create a previously rejected row with decision metadata for immutability assertions once the new column exists. Take before/after snapshots of test-owned booking/Event rows and notification IDs.

## Existing automated coverage

During RED, the older backend story sources in this table were inspected only. GREEN ran the request/approval/conflict/hold regressions listed in Phase 4. Existing tests in the two targeted frontend files were executed: all 28 passed, including AC1's SCRUM-39 viewing tests. The separate app-factory baseline was also executed as required. New SCRUM-69 failures are recorded separately below.

| Existing source and tests | SCRUM-69 relevance | Limits / reuse |
|---|---|---|
| `backend/tests/test_venue_booking_request.py`: `SavedAndVisibleTests.test_venue_staff_see_pending_requests`, `test_only_venue_staff_can_list_requests`; `FailureTests.test_list_failure_is_retryable_and_not_shown_as_empty` | AC1 details, pending filtering, stored-role access to list, and list database failure. | Direct existing viewing coverage. Reference in TC-69-01; do not create equivalent tests. |
| `frontend/src/pages/VenueBookingRequestsPage.test.jsx`: `lists each pending request with what Venue Staff need to assess it`, `shows the empty state`, `shows a retryable error when the requests cannot be loaded` | AC1 display and loading states. | Direct existing viewing coverage; no Reject or reason coverage. |
| `backend/tests/test_venue_booking_approval.py`: `OnlyPendingTests`, `test_booking_and_venue_rows_are_locked_before_the_conflict_check`, `test_approving_confirms_the_booking_and_records_the_decision` | Patterns for authorisation, state protection, locking and decision metadata (AC2/AC4). | Approval only; no SCRUM-69 rejection coverage. The lock test inspects SQL, not a real competing transaction. |
| Same file: `test_bookings_that_are_not_confirmed_do_not_conflict`; `backend/tests/test_venue_booking_request.py`: `test_pending_request_does_not_block_the_venue`, `test_new_request_allowed_once_earlier_one_is_not_pending` | AC5 supporting rules, including manually seeded rejected requests. | Does not exercise the transition to rejected. Reuse rules; add only rejection-specific side-effect assertions. |
| `backend/tests/test_venue_booking_approval.py`: `test_coordinator_is_notified_in_the_app`, `test_coordinator_is_emailed`, `test_approval_stands_when_the_email_cannot_be_queued`, `SaveFailureTests` | AC4/AC6 notification API, transaction and queue patterns. | Approval only; no rejection reason, rejection recipient or rejection rollback assertions. |
| `backend/tests/test_venue_holds.py`: `test_only_a_pending_request_can_be_held`, `test_approving_a_hold_is_refused`; hold notification/failure cases | Tentative-state compatibility and shared notification/locking patterns. | No pending-only rejection coverage. Keep expiry/confirmation behaviour in SCRUM-87. |
| `backend/tests/test_tasks.py`: `test_send_notification_email_builds_the_expected_message`, `test_send_notification_email_uses_tls_and_authenticates`, `test_task_is_registered_with_celery_under_a_stable_name` | Reusable email transport. | Do not duplicate transport tests; rejection tests assert queued recipient and content, not live delivery. |
| `frontend/src/pages/VenueBookingRequestPage.test.jsx`: pending receipt and confirmed-venue cases | Existing coordinator page flows to preserve. | No persisted rejection display or notification fetching coverage. |

## Phase 2 — Test cases and current automation status

Cases below retain the broader draft scenarios and expected outcomes. **Automated** entries show the final GREEN result for implemented checks and distinguish remaining Planned / Not run variants. Original RED results remain recorded in Phase 3. Unless overridden, use VR-SEED, gus, P1 and R1. For every refused mutation assert unchanged test-owned booking/Event state, no new notification and no queued email. Cases trace to original ACs; extra authorisation, failure and interface expectations derive from assumptions/repository conventions, not additional ACs. The RED integration fixture reuses SCRUM-40 VA-SEED directly (zero setup/turnaround by default), rather than duplicating it to add buffers; buffer/calendar variants remain planned.

### AC1 — View pending requests

**TC-69-01 · Reuse existing pending-list coverage**
- **Traces to:** AC1 · **Type:** Regression · **Status:** Existing frontend and backend coverage PASS in GREEN
- **Preconditions:** VR-SEED equivalent request data; for loading-state checks use existing fixtures.
- **Steps:** Inspect/reuse SCRUM-39 TC-39-17/18/20 and its list-failure case when later running regression checks.
- **Expected result:** Venue Staff see event, venue, requested date/start/end and venue requirements for pending rows. Non-staff are denied; no-result and load-failure states remain distinct; Singapore request times are unchanged.
- **Automated:** Existing tests named in the first two rows of the coverage table. No new duplicate test planned.

### AC2 — Pending-only rejection and access control

**TC-69-02 · Venue Staff reject a pending request and persist the decision**
- **Traces to:** AC2, AC3, AC4, AC5 · **Type:** Happy path / persistence · **Depends on:** A1–A3
- **Preconditions:** VR-SEED; capture P1 and E1 before the call.
- **Steps:** Reject P1 with R1, expire/reload database state, then list pending requests.
- **Expected result:** HTTP 200; P1 retains the same ID, event, venue, requirements, requester, original timestamp, period and buffers. Status is rejected, reason is R1, deciding staff is gus, and UTC decision time lies between the call's start/end. Response agrees with stored values. P1 leaves the pending list; P2 stays. E1 is unchanged. No extra booking row or hold is created. Notification content is asserted separately in TC-69-17.
- **Automated:** `RejectionPersistenceTests.test_reject_pending_request_records_decision_without_creating_booking` in `backend/tests/test_venue_booking_rejection.py` — GREEN PASS; persistence and side-effect assertions now execute.

**TC-69-03 · Every non-pending state is refused**
- **Traces to:** AC2, AC5 · **Type:** Negative / state boundary
- **Preconditions:** Separate test-owned confirmed, rejected, cancelled, unexpired tentative and expired tentative rows; snapshot any decision/hold metadata.
- **Steps:** Send a valid rejection reason for each.
- **Expected result:** HTTP 409 `reason: "not_pending"`, naming the status; all snapshots remain unchanged. Expiry alone never makes a tentative row pending.
- **Automated:** `RejectionGuardUnitTests.test_only_pending_requests_can_be_rejected` — GREEN PASS; isolated subtests cover all five state/expiry variants without SQL.

**TC-69-04 · Retrying a successful rejection preserves the first decision**
- **Traces to:** AC2, AC4, AC6 · **Type:** Negative / duplicate submission
- **Preconditions:** P1 has been successfully rejected with R1.
- **Steps:** Reject it again with a different valid reason, representing a double-click or retry after a lost response.
- **Expected result:** Second call returns 409 `not_pending`; original reason/time/staff remain. Exactly one rejection notification and one queue call exist for this decision.
- **Automated:** `RejectionPersistenceTests.test_repeat_rejection_preserves_first_decision` — GREEN PASS, including refusal of the second decision.

**TC-69-05 · Only the stored Venue Staff role permits rejection**
- **Traces to:** AC2 · **Type:** Negative / authorisation · **Depends on:** A1
- **Preconditions:** P1 exists; tokens for alice, ben, dana, hana, farah, admin and lena. Also mint gus's token before changing his database role to attendee.
- **Steps:** Attempt rejection with each token; restore gus's stored role and retry with the same token.
- **Expected result:** Every non-staff attempt is 403 without private request details or side effects. The same token works once its user's database role is Venue Staff again.
- **Automated:** `RejectionGuardUnitTests.test_rejection_uses_current_stored_venue_staff_role` — GREEN PASS; covers refusal for all six stored non-staff roles despite a staff JWT claim. Same-token restoration to staff remains Planned / Not run; normal staff success is asserted by TC-69-02.

**TC-69-06 · Invalid sessions cannot reject**
- **Traces to:** AC2 · **Type:** Negative / authentication
- **Preconditions:** P1 exists; no token, malformed/expired token, token for deleted user, and valid signed token with unparsable identity.
- **Steps:** Attempt rejection using each session.
- **Expected result:** HTTP 401; no mutation, notification or queued email. Invalid stored-user identities receive the repository's session-invalid message.
- **Automated:** `RejectionGuardUnitTests.test_rejection_requires_valid_session` — GREEN PASS for no token, expired token, deleted user and unparsable identity. A malformed token variant remains Planned / Not run.

**TC-69-07 · Unknown request and competing validation failures**
- **Traces to:** AC2, AC3 · **Type:** Negative / error precedence · **Depends on:** Q6
- **Preconditions:** Use `missing_id(VenueBooking)` and a test-owned confirmed row.
- **Steps:** Try an unknown ID as gus; an unknown ID as a non-staff caller; an existing ID as non-staff with blank input; and a confirmed row as gus with blank input.
- **Expected result:** Provisionally 404, 404, 403 and 400 respectively under A6. Valid input on the confirmed row returns 409. No private record fields appear in denied responses. The non-staff/unknown-ID expectation must be finalised under Q6 before automation.
- **Automated:** `RejectionGuardUnitTests.test_unknown_request_is_not_found` — GREEN PASS with the required JSON domain 404. Combined-error precedence remains Planned / Not run pending Q6; no provisional order is imposed by RED tests.

**TC-69-08 · Competing rejection, approval and hold cannot overwrite a decision**
- **Traces to:** AC2, AC4, AC5, AC6 · **Type:** Concurrency · **Depends on:** A7
- **Preconditions:** Two Venue Staff sessions and P1; use isolated local PostgreSQL test-owned data for a real race once authorised.
- **Steps:** Compete rejection against rejection, approval and hold on the same pending row. Inspect the new route's SQL for a refreshed `FOR UPDATE` read, following existing helper patterns; separately exercise two transactions for a behavioural race check.
- **Expected result:** Exactly one decision wins; the loser observes non-pending state and returns 409. Final fields and notification match the winning operation only. If rejection wins, no confirmed booking/hold is produced. A SQL-lock assertion alone is not reported as proof of race behaviour.
- **Automated:** Planned `test_rejection_locks_and_refreshes_request`; behavioural two-session check Planned / Not run, without changing the shared `AppTestCase` transaction contract.

### AC3 — Required reason and character boundaries

**TC-69-09 · Missing and blank reasons are refused**
- **Traces to:** AC3 · **Type:** Negative / validation
- **Preconditions:** P1 pending.
- **Steps:** Submit `{}`, null reason, empty string, spaces, tabs/newlines, and whitespace-only Unicode text.
- **Expected result:** HTTP 400 `field: "reason"`, explaining that a reason is required; no saved change, notification or email.
- **Automated:** `RejectionGuardUnitTests.test_rejection_reason_is_required` — GREEN PASS; six missing/null/blank/whitespace subtests.

**TC-69-10 · Invalid JSON, wrong types and extra fields cannot change the request**
- **Traces to:** AC3, AC5 · **Type:** Negative / invalid request · **Depends on:** A2
- **Preconditions:** P1 pending.
- **Steps:** Send no body, malformed JSON, scalar/list body, numeric/boolean/list/object reason, and valid reason with extra keys such as `status`, `venue_id` or `start_time`.
- **Expected result:** HTTP 400 with a body error or identified field. No coercion, mass assignment or side effect occurs.
- **Automated:** `RejectionGuardUnitTests.test_rejection_reason_must_be_text` and `test_rejection_requires_json_object` — GREEN PASS. Extra-key/mass-assignment variants remain Planned / Not run; they are not needed to establish the core missing rejection behaviour.

**TC-69-11 · Nonblank reasons up to exactly 500 characters are accepted**
- **Traces to:** AC3, AC4 · **Type:** Boundary / persistence
- **Preconditions:** Fresh pending row per variant.
- **Steps:** Reject with nonblank ASCII strings of 1, 499 and exactly 500 characters; reload each saved decision.
- **Expected result:** HTTP 200 for all variants; full reason is stored, returned and included in the saved notification without truncation.
- **Automated:** `RejectionPersistenceTests.test_rejection_accepts_exactly_500_characters_without_truncation` — GREEN PASS. The 1- and 499-character variants remain Planned / Not run; ordinary R1 is covered by TC-69-02, avoiding duplicate success tests.

**TC-69-12 · A 501-character reason is refused by the backend**
- **Traces to:** AC3 · **Type:** Boundary / negative
- **Preconditions:** P1 pending; bypass browser validation.
- **Steps:** POST a nonblank ASCII reason of exactly 501 characters.
- **Expected result:** HTTP 400 `field: "reason"` explaining the 500-character maximum; P1 stays pending, with no decision or notification. No silent truncation.
- **Automated:** `RejectionGuardUnitTests.test_rejection_refuses_501_character_reason` — GREEN PASS.

**TC-69-13 · Trimming and Unicode counting are consistent**
- **Traces to:** AC3, AC4 · **Type:** Boundary · **Depends on:** Q2
- **Preconditions:** Fresh pending rows for accepted variants.
- **Steps:** Submit padded R1 with internal spaces/newlines; submit 500 visible characters padded with surrounding whitespace; submit 500 and 501 supplementary Unicode code points through API and browser.
- **Expected result:** Under A2, surrounding whitespace is removed, internal whitespace retained, and both clients apply the same 500-code-point boundary. The accepted reason is identical in storage, response and notification. This interpretation is provisional pending Q2.
- **Automated:** Planned `test_rejection_reason_normalisation_and_unicode`; matching frontend boundary assertions extend TC-69-24.

### AC4 — Saved outcome is visible to the coordinator

**TC-69-14 · Reopen the existing coordinator page and see the saved rejection**
- **Traces to:** AC4, AC6 · **Type:** Happy path / frontend persistence · **Depends on:** A4
- **Preconditions:** P1 rejected in a previous request/session; alice is still E1's coordinator.
- **Steps:** As alice, open/reload E1's venue-request page and read the persisted request response via `GET /api/venues/bookings?event_id=<E1>`; separately inspect the notification API for AC6.
- **Expected result:** The page displays Rejected and the full saved reason with the event page, venue and requested period from the saved request record; it does not depend on staff-page state or the old in-memory submission receipt. E1's event status remains approved, not rejected. Existing pending receipt and confirmed-venue displays remain accurate if a later request/approval exists; older rejection messages are clearly historical.
- **Automated:** Frontend `shows the persisted rejection and reason when reopening the coordinator page` — GREEN PASS. Backend API/content assertions are in TC-69-17. The frontend `keeps the saved rejection visible alongside a later confirmed venue` case also passes. `test_coordinator_recovers_saved_decision_without_notifications` proves recovery from request rows after reassignment while forbidding notification queries.

**TC-69-15 · Coordinator display respects event access and notification ownership**
- **Traces to:** AC4, AC6 · **Type:** Negative / privacy · **Depends on:** A4
- **Preconditions:** Saved rejections for E1/alice and E2/ben; unrelated notification kinds for alice.
- **Steps:** Open E1's page as alice and attempt access as ben, dana, admin and a signed-out caller. Request each signed-in user's own notifications.
- **Expected result:** Alice's request-history response contains only E1's booking rows; other-event histories are not disclosed by the server. Existing planning permission checks deny other users (403; signed out requires login/401 at API). Other recipients' notification responses do not contain alice's rejection. Do not expose fetched content after an event access failure.
- **Automated:** `RejectionPersistenceTests.test_saved_decisions_require_current_coordinator_and_report_read_failure` - GREEN PASS; covers other coordinator/organiser/staff/admin/lead denial, missing JWT and retryable read failure. Notification recipient isolation remains covered by TC-69-17. Extra browser permission variants remain Planned / Not run.

### AC5 — No confirmed booking or reservation is produced

**TC-69-16 · Retain the request record without occupying the slot**
- **Traces to:** AC5 · **Type:** Integration / regression
- **Preconditions:** P1's venue/occupied period otherwise free within recorded operating hours; snapshot test-owned confirmed/hold rows, blocks and E1.
- **Steps:** Reject P1, then reload booking rows, calendar and search for its occupied period (including setup/turnaround). In a variant, preserve another event's existing confirmed booking/hold while rejecting P1.
- **Expected result:** Existing request P1 remains as rejected; no additional booking, confirmed status, hold, block or event venue assignment is created. Rejected P1 contributes no blocking period/conflict, and Aurora remains searchable when no other rule excludes it. Independent confirmed bookings/holds remain unchanged and continue to block their own periods. Never assert that rejection makes an independently blocked slot available.
- **Automated:** Reused TC-69-02 `test_reject_pending_request_records_decision_without_creating_booking` — GREEN PASS; checks unchanged test-owned booking IDs, original request fields, hold metadata and every Event field. Calendar/search, nonzero buffers and independent-blocker variants remain Planned / Not run; no duplicate scheduling tests were added.

### AC6 — Notify the current coordinator, including the reason

**TC-69-17 · Save and expose the complete rejection notification and queue email**
- **Traces to:** AC4, AC6 · **Type:** Happy path / integration · **Depends on:** A4
- **Preconditions:** P1 pending; capture test-owned recipient notification IDs; mock queue.
- **Steps:** Reject with R1; load alice's notifications, and those of ben, dana and gus. Inspect queue arguments and response flags.
- **Expected result:** Exactly one new `venue_booking_rejected` notification for alice linked to E1, explicitly stating rejection and R1 in full, event, venue, period and deciding staff. It appears in alice's notification API response and not others'. Exactly one email is queued to alice with event/venue in the subject and rejection/reason in the body. Response reports `in_app: true, email_queued: true`. This verifies queueing, not delivery.
- **Automated:** `RejectionPersistenceTests.test_rejection_notifies_coordinator_with_full_reason` — GREEN PASS.

**TC-69-18 · Reassignment changes who is notified**
- **Traces to:** AC6 · **Type:** Boundary / recipient selection · **Depends on:** A4
- **Preconditions:** P1 was requested by alice; E1 is reassigned to ben before rejection.
- **Steps:** As gus, reject P1 and inspect notifications and queue recipient.
- **Expected result:** Ben, the current assigned coordinator, receives the new in-app notification and email with R1; alice receives no new notification/email for this rejection. Do not silently substitute the original requester.
- **Automated:** `RejectionPersistenceTests.test_rejection_notifies_current_coordinator_after_reassignment` — GREEN PASS.

**TC-69-19 · Email queue failure does not undo a saved rejection**
- **Traces to:** AC4, AC6 · **Type:** Negative / queue failure
- **Preconditions:** Mock queue raises `ConnectionError`.
- **Steps:** Reject P1 and reload persisted state.
- **Expected result:** HTTP 200, rejected decision/reason and in-app notification remain saved; `email_queued: false`, `in_app: true`; failure is logged. No second decision or duplicate notification is created on a repeated rejection attempt. The UI must not claim email delivery.
- **Automated:** `RejectionPersistenceTests.test_queue_failure_after_commit_preserves_rejection_and_notification` and `test_email_delivery_failure_does_not_undo_committed_rejection` — GREEN PASS. The latter invokes the real task body through a mocked eager dispatch and makes mocked SMTP raise `SMTPException`; no SMTP connection occurs. It checks durability after simulated delivery failure, not delivery by a real asynchronous worker. Frontend queue-flag variants are in TC-69-24.

### Failure and edge scenarios supporting AC2–AC6

**TC-69-20 · Database read failure never masquerades as missing context or success**
- **Traces to:** AC2, AC4, AC6 · **Type:** Negative / failure
- **Preconditions:** Inject a SQLAlchemy read failure separately at stored-user, booking, event, venue, coordinator and dependent payload loads.
- **Steps:** Attempt rejection with otherwise valid data; restore the failed read and retry.
- **Expected result:** Each failure returns 503 `retryable: true`, rolls back and leaves no decision/notification/email. No 404, missing-coordinator response or success replaces a failed load. Recovered retry produces one saved decision and notification.
- **Automated:** `RejectionGuardUnitTests.test_rejection_read_failure_is_retryable` — GREEN PASS; covers the first dependent read, rollback and retryable response in isolation. Per-model later read failures and recovery variants remain Planned / Not run.

**TC-69-21 · Failed decision or notification save rolls everything back**
- **Traces to:** AC4, AC5, AC6 · **Type:** Negative / transaction failure
- **Preconditions:** Inject SQLAlchemy failure separately at decision flush, notification insert/flush and commit, including after decision changes are staged. Snapshot P1, E1 and notifications first.
- **Steps:** Attempt rejection; reload state after failure, then retry with storage restored.
- **Expected result:** HTTP 503 `retryable: true`, message says the rejection was not saved and can be retried. P1 is still pending with no new reason/time/staff; E1, bookings and notification IDs are unchanged. No email is queued before or after a failed commit. The recovered retry yields exactly one rejection and one notification. Assert successful email invocation occurs only after commit returns.
- **Automated:** `RejectionPersistenceTests.test_failed_commit_rolls_back_decision_and_notification`, `test_notification_insert_failure_rolls_back_decision`, and commit-order assertions in `test_queue_failure_after_commit_preserves_rejection_and_notification` — GREEN PASS. The notification INSERT hook, commit-failure hook, rollback/recovery and commit-before-email assertions were all reached and passed. A separate decision-flush failure variant remains Planned / Not run.

**TC-69-22 · Missing legacy event/coordinator is handled deliberately**
- **Traces to:** AC4, AC6 · **Type:** Negative / data dependency · **Depends on:** Q5
- **Preconditions:** A test-owned pending row with no event; separately an event with no assigned coordinator. Do not break foreign keys to manufacture dangling IDs.
- **Steps:** Reject each with R1.
- **Expected result:** Provisionally 409 with a useful missing-context/assignment message and no mutation or notification. No unhandled attribute error or false claim that the coordinator was notified. A database outage loading this context belongs to TC-69-20 (503), not this case.
- **Automated:** Planned `test_rejection_handles_missing_event_or_coordinator`; expected policy awaits Q5.

**TC-69-23 · Approval-only restrictions do not prevent declining a pending request**
- **Traces to:** AC2, AC5 · **Type:** Boundary / business rule · **Depends on:** Q4
- **Preconditions:** Separate pending requests whose event was cancelled, whose time already started, or whose venue period now clashes with a confirmed booking/block/hold. Retain all independent arrangements.
- **Steps:** Reject each with R1.
- **Expected result:** Under A3, each succeeds without changing its event or independent arrangements; rejection reserves nothing and does not call the approval availability-check helper. No extra event/time/conflict prohibition is invented from the approval story. Expectations await Q4.
- **Automated:** Planned `test_pending_rejection_does_not_require_approval_eligibility`.

### Frontend controls and recovery

**TC-69-24 · Staff enter a reason and reject the selected request**
- **Traces to:** AC2, AC3, AC4, AC6 · **Type:** Happy path / frontend boundary · **Depends on:** A2, A4
- **Preconditions:** Mock pending-list response with P1 and P2; mock rejection response and reload.
- **Steps:** Locate the event-labelled reason field and Reject action by accessible role/name; enter R1 and reject P1. Check 500/501-character variants and blank input; exercise `email_queued: false` success as a variant.
- **Expected result:** Only P1's ID and reason are sent through `apiClient` to `/venues/bookings/<id>/reject`. Blank/over-limit input is explained before posting; 500 characters can be submitted. Success shows the server's confirmation, removes P1 and reloads the list while retaining P2. The queue-failure success still shows the saved outcome without claiming email delivery. Existing Approve and Place tentative hold controls still use their original endpoints and inputs.
- **Automated:** In `VenueBookingRequestsPage.test.jsx`: `rejects the selected request with its reason (email queued: %s)` (2 instances), `requires a nonblank rejection reason (%j)` (3), `accepts exactly 500 characters without truncating the reason` (1), and `refuses a 501-character reason before sending a rejection` (1) — GREEN PASS. Existing approval/hold regressions PASS. Unicode interpretation remains deferred under Q2.

**TC-69-25 · Staff errors preserve the reason and allow appropriate retry**
- **Traces to:** AC2, AC3, AC4, AC6 · **Type:** Negative / frontend recovery
- **Preconditions:** Pending list loaded; enter distinct reasons for P1 and P2.
- **Steps:** Reject P1 when the server returns 400 (reason), 409 (no longer pending), 503 `retryable: true`, or the network fails. Retry the retryable variants after recovery.
- **Expected result:** Server `error` is shown, with a sensible connection fallback when absent. No false success/removal occurs on failure; both typed reasons are retained. A retry uses P1's original reason and can succeed. A 409 explains stale status without promising that retry will succeed; refreshing can reconcile the pending list. No cross-request reason mix-up.
- **Automated:** `keeps each request's reason after a rejection failure (%s)` in `VenueBookingRequestsPage.test.jsx` (400, 409, 503 and network: 4 instances) — GREEN PASS. Only retryable/network variants assert a successful retry; 409 does not promise recovery by retry.

**TC-69-26 · Coordinator outcome-load failure is explicit and recoverable**
- **Traces to:** AC4, AC6 · **Type:** Negative / frontend read failure · **Depends on:** A4
- **Preconditions:** Existing coordinator page can load planning/venues; saved-notification read fails with 503 or network error.
- **Steps:** Open the page, observe failure, restore notification loading and use Retry.
- **Expected result:** Explain that saved venue outcomes could not be loaded, without claiming no rejection exists or losing request-form inputs. Retry displays the saved outcome once available. Existing confirmed-venue/pending-receipt behaviour remains accurate. A permission failure displays its error and no private saved outcome.
- **Automated:** `reports saved rejection load failure and retries without losing request details` in `VenueBookingRequestPage.test.jsx` — GREEN PASS. It exercises the retryable 503 variant; network/permission variants remain Planned / Not run.


## Traceability matrix

| AC | Test cases | Existing versus planned |
|---|---|---|
| AC1 | TC-69-01 | Existing SCRUM-39 frontend viewing/empty/retry cases PASS; existing backend viewing tests also PASS in GREEN. |
| AC2 | TC-69-02–08, 20, 23–25 | Focused checks PASS in GREEN; combined precedence, concurrency and approval-only eligibility variants remain Planned. |
| AC3 | TC-69-02, 07, 09–13, 24–25 | Core reason validation and exact 500/501 boundaries GREEN PASS at API and UI. Normalisation/Unicode and extra variants remain Planned. |
| AC4 | TC-69-02, 04, 08, 11, 13–15, 17, 19–22, 24–26 | Persistence/visibility/notification checks GREEN PASS. Unimplemented draft variants are identified per case. |
| AC5 | TC-69-02–03, 08, 10, 16, 21, 23 | Core request retention/no-confirmation/no-hold/no-event-change checks GREEN PASS. No duplicate scheduling coverage added. |
| AC6 | TC-69-04, 08, 14–15, 17–22, 24–26 | Recipient/reason/atomicity/queue/delivery-failure checks GREEN PASS. Existing email transport tests are reused by reference. |

| Type | Test cases |
|---|---|
| Happy path / persistence | 01, 02, 11, 14, 16, 17, 18, 24 |
| Boundary / invalid input | 03, 07, 09–13, 18, 22–24 |
| Authentication / authorisation / privacy | 01, 05–07, 15 |
| Duplicate / concurrent decisions | 04, 08 |
| Failure / recovery | 19–22, 25–26 |
| Frontend | 01, 13–15, 24–26 |

## Open questions for the customer / implementation decisions

| # | Question and provisional recommendation | Affects |
|---|---|---|
| Q1 | Do admins also reject, or is access restricted to the existing stored `venue_staff` role across all venues? Recommend matching current staff scope. | A1, TC-69-05 |
| Q2 | Does the 500-character limit apply after trimming surrounding whitespace, and should supplementary Unicode characters count as one code point? Recommend trimming and consistent code-point counting; the numeric limit itself is fixed by AC3. | A2, TC-69-09–13, 24 |
| Q3 | Resolved by the GREEN instruction: a notification alone must not be the only recovery path. The current coordinator reads saved request rows through the existing bookings API with an event filter. Notification ownership does not limit decision recovery after reassignment. | A4, TC-69-14–15, 17–19, 24, 26 |
| Q4 | May any pending request be rejected even after its event is cancelled, time has started, or a conflict arises? Recommend yes: declining creates no reservation. Tentative holds remain excluded by AC2; rejection/cancellation of a hold is separate scope. | A3, TC-69-03, 23 |
| Q5 | What should happen when a legacy request lacks an event or assigned coordinator? Recommend refusing with an actionable 409 and no change until assignment/context is repaired; do not invent a recipient. Existing approval/hold code assumes these rows exist, so copying it verbatim risks an unhandled failure. | A5, TC-69-22 |
| Q6 | Should the new endpoint follow the supplied repository's 401 → 404 → 403 → 400 → 409 order or the venue approval/hold role-first order? Recommend the supplied repository rule for this route while leaving other stories unchanged; finalise precedence before implementation. | A6, TC-69-07 |
| Q7 | Can the later concurrency check use isolated local PostgreSQL with two independent transactions? The shared Supabase savepoint fixture is not suitable for proving a real race, and source inspection of a lock is not a race test. | A7, TC-69-08 |

**Shared-contract boundary:** adding the reason column and new rejection path is the proposed SCRUM-69 work. Changing approval/hold transitions, planning payloads, notification ownership rules, tentative expiry semantics, or globally reordering authorisation would affect other stories and needs discussion first. No such change was made. GREEN resolves Q3 through request-row recovery and adopts A5/A6 locally for the new rejection flow; shared approval/hold behaviour is unchanged. No demonstrated need to refactor shared scheduling or build a new notification service was found.

## Phase 3 — RED implementation and execution record (historical)

### Scope and isolation

Only these automated test files were added/modified:

- New `backend/tests/test_venue_booking_rejection.py`: 9 isolated HTTP/JWT methods plus 9 local database integration methods.
- `frontend/src/pages/VenueBookingRequestsPage.test.jsx`: 11 new SCRUM-69 instances; existing cases unchanged.
- `frontend/src/pages/VenueBookingRequestPage.test.jsx`: 3 new SCRUM-69 instances; existing cases unchanged apart from importing Testing Library's `waitFor` for the new recovery case.

This document is the only documentation changed. No production code, dependency, environment file, SQL script or schema was changed; no database was reset/rebuilt/migrated; `ci/build_test_database.py` was not run. No commits, pushes or PRs were made.

The fixture/configuration inspection found that `tests/base.py:get_test_app()` explicitly calls `create_app(TestConfig)`; its sole real connection is `db.engine.connect()`. `TestConfig.SQLALCHEMY_DATABASE_URI` comes from `TEST_DATABASE_URL`, not `DATABASE_URL`. SCRUM-40's inherited fixtures use that session. The new isolated tests register the venues blueprint directly on Flask with JWT, mock persistence/email, and fail loudly on `Engine.connect`, `Engine.raw_connection` or socket connections. They do not open a database connection. The integration class checks the exact host/port/database/username before inherited fixture setup can connect. No independently configured database connection was found in the fixtures used by these runs.

**All database-dependent execution targeted the existing local Docker PostgreSQL database, never Supabase:**

| Item | Observed result |
|---|---|
| Docker container | `trueadams-test-pg`, running; published port `127.0.0.1:5433->5432/tcp` |
| Effective TestConfig before initial baseline | `127.0.0.1 5433 postgres connectsphere_test` |
| Effective TestConfig before each backend RED execution | `127.0.0.1 5433 postgres connectsphere_test` |
| Effective TestConfig before final baseline | `127.0.0.1 5433 postgres connectsphere_test` |
| Actual connected role/schema, before and after | Baseline query verifies `connectsphere_test`, `public` |
| Model/table compatibility, before and after | Baseline `test_database_tables_match_the_models` PASS |

`DATABASE_URL` was also overridden to the supplied **local owner URL**, making the normal app configuration local and distinct from the restricted test login. `PYTHON_DOTENV_DISABLED=1` was set as an additional precaution. No `.env` or `.env.example` was edited or used as a source of test credentials. Setting `OWNER_DATABASE_URL` does not open an owner connection; no owner database operation was run.

### Exact execution commands

Docker inventory, from the repository root:

```powershell
docker ps --filter name=trueadams-test-pg --format '{{.Names}} {{.Status}} {{.Ports}}'
```

The first sandboxed inventory attempt was denied Docker pipe/config access. The same read-only command succeeded with execution escalation and confirmed the existing running container. No container was created, restarted or altered.

Before **each** backend shell invocation, from `backend/`, set this complete environment in that same shell. The existing virtual environment was selected through PATH; nothing was installed:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://connectsphere_test:ci-only@127.0.0.1:5433/postgres'
$env:OWNER_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/postgres'
$env:TEST_ROLE_PASSWORD = 'ci-only'
$env:DATABASE_URL = $env:OWNER_DATABASE_URL
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PATH = (Resolve-Path '.venv/Scripts').Path + ';' + $env:PATH
```

Initial baseline (after setting that environment):

```powershell
python -c "from app.config import TestConfig; from sqlalchemy.engine import make_url; u=make_url(TestConfig.SQLALCHEMY_DATABASE_URI); print('Test database:',u.host,u.port,u.database,u.username); assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'UNSAFE DATABASE TARGET!'"
if ($LASTEXITCODE -ne 0) { throw 'Database verification failed; baseline not run.' }
python -m unittest -v tests.test_app_factory
if ($LASTEXITCODE -ne 0) { throw 'Baseline failed; do not proceed to RED execution.' }
```

Backend RED (environment set again in the same new shell):

```powershell
python -c "from app.config import TestConfig; from sqlalchemy.engine import make_url; u=make_url(TestConfig.SQLALCHEMY_DATABASE_URI); print('Test database:',u.host,u.port,u.database,u.username); assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'UNSAFE DATABASE TARGET!'"
if ($LASTEXITCODE -ne 0) { throw 'Database verification failed; RED tests not run.' }
$redLog = Join-Path $env:TEMP 'scrum69-backend-red.log'
python -m unittest -v tests.test_venue_booking_rejection *> $redLog
$redExit = $LASTEXITCODE
```

The backend RED command was run twice: initially, then after strengthening the tests to verify the failed commit was actually invoked and record email/commit order outside the callback (the email helper catches callback exceptions). Both runs reported 18 methods, 42 assertion failures including subtests, zero errors. Before the second run the complete environment and verification command were repeated. That same shell then ran the final baseline with a **fresh verification immediately before it**:

```powershell
python -c "from app.config import TestConfig; from sqlalchemy.engine import make_url; u=make_url(TestConfig.SQLALCHEMY_DATABASE_URI); print('Test database:',u.host,u.port,u.database,u.username); assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'UNSAFE DATABASE TARGET!'"
if ($LASTEXITCODE -ne 0) { throw 'Database verification failed; final baseline not run.' }
python -m unittest -v tests.test_app_factory
if ($LASTEXITCODE -ne 0) { throw 'Final baseline failed.' }
```

Targeted frontend execution, from `frontend/` (API mocked; no database access):

```powershell
$redLog = Join-Path $env:TEMP 'scrum69-frontend-red.log'
npm.cmd test -- src/pages/VenueBookingRequestsPage.test.jsx src/pages/VenueBookingRequestPage.test.jsx --reporter=verbose *> $redLog
$redExit = $LASTEXITCODE
```

The first sandboxed frontend attempt failed before collection: esbuild could not traverse a parent directory to resolve `vitest.config.js` due to access restrictions. This was an **unexpected execution-environment failure, not RED evidence**. Repeating the same targeted command with execution escalation succeeded in collecting/running both files; no config or dependency change was needed.

### Actual results and limits

| Execution | Count | Classification | Evidence / explanation |
|---|---|---|---|
| Initial `tests.test_app_factory` | 7 passed, 0 failed | PASS | Existing local schema, restricted role and app factory are operational. |
| New backend tests, final run | 18 methods; 42 assertion failures counting subtests; 0 errors, 0 skips | Expected RED | 41 assertions fail on HTTP 404 instead of the required status; the unknown-request case fails because Flask's unregistered-route HTML 404 is not the JSON domain error. All 18 methods have expected failures. No setup/import/database failure occurred. |
| Existing cases in the two frontend files | 28 passed | PASS | Includes SCRUM-39 AC1 display/empty/retry and existing request/approval/hold flows. |
| New staff frontend cases | 11 failed | Expected RED | Reason textbox and/or Reject action do not exist. |
| New coordinator frontend cases | 3 failed | Expected RED | Persisted rejection messages and saved-outcome loading/error UI do not exist. |
| Frontend total | 42 instances: 28 passed, 14 failed | PASS for existing behaviour; Expected RED for SCRUM-69 | Vitest 2.1.9 completed both targeted files. |
| Final `tests.test_app_factory` | 7 passed, 0 failed | PASS | Local target reverified immediately before execution; models still match unchanged tables. |

**Limits:** all backend feature cases stop at the missing route, and frontend feature cases stop at missing controls/messages. The deeper persistence, rollback, queue-order, delivery-failure, boundary and recovery assertions are written, but **have not yet been reached or proven**. They must execute during GREEN; absence of setup errors is not proof of transactional correctness. The mocked eager SMTP failure is not a real broker/worker delivery test. No full backend or frontend suite, live email, Supabase or real concurrency test was run.

### Executed automation by AC

Names below refer to `backend/tests/test_venue_booking_rejection.py` unless a frontend file is specified. This focused mapping supplements the full draft traceability matrix above.

| AC | Implemented checks | Result |
|---|---|---|
| AC1 | Existing SCRUM-39 list/details/empty/retry tests in `VenueBookingRequestsPage.test.jsx`; no duplicate tests added. | PASS |
| AC2 | `RejectionGuardUnitTests.test_only_pending_requests_can_be_rejected`, `test_rejection_uses_current_stored_venue_staff_role`, `test_rejection_requires_valid_session`, `test_unknown_request_is_not_found`; `RejectionPersistenceTests.test_reject_pending_request_records_decision_without_creating_booking`, `test_repeat_rejection_preserves_first_decision`; staff frontend actions. | Expected RED |
| AC3 | Unit `test_rejection_reason_is_required`, `test_rejection_reason_must_be_text`, `test_rejection_requires_json_object`, `test_rejection_refuses_501_character_reason`; persistence `test_rejection_accepts_exactly_500_characters_without_truncation`; frontend blank/500/501 cases. | Expected RED |
| AC4 | Persistence `test_reject_pending_request_records_decision_without_creating_booking`, `test_rejection_notifies_coordinator_with_full_reason`; coordinator frontend saved-message/filter/retry cases. | Expected RED |
| AC5 | Persistence `test_reject_pending_request_records_decision_without_creating_booking`; non-pending immutability checks; transaction rollback cases. Request rows are retained, not deleted. | Expected RED |
| AC6 | Persistence `test_rejection_notifies_coordinator_with_full_reason`, `test_rejection_notifies_current_coordinator_after_reassignment`, `test_failed_commit_rolls_back_decision_and_notification`, `test_notification_insert_failure_rolls_back_decision`, `test_queue_failure_after_commit_preserves_rejection_and_notification`, `test_email_delivery_failure_does_not_undo_committed_rejection`; unit `test_rejection_read_failure_is_retryable`. | Expected RED |

### Remaining assumptions and proportionate deferrals

The original six ACs remain unchanged. The tests use the existing Venue Staff-only rule and draft `/reject` JSON contract. They provisionally use saved notifications on the existing coordinator page (A4/Q3); the user-facing accessibility labels in the staff tests are proposed UI labels, not new ACs. They do not impose combined-error precedence (Q6), legacy missing-coordinator policy (Q5), supplementary Unicode counting/trimming (Q2), or rejection eligibility after event cancellation/start (Q4).

Those unresolved variants, plus real concurrency, calendar/search regression and extra body fields, remain **Planned / Not run**. They were not added merely to increase case counts. Resolve the relevant assumptions before implementing those branches; changes affecting shared story contracts still require discussion.

## Database compatibility plan recorded at RED (historical; current hand-off in Phase 4)

1. Add only nullable `VenueBooking.rejection_reason` text to the model, reusing existing decision metadata and text status. Pair it with a new idempotent `backend/db/venue_booking_rejections.sql`, wrapped in a transaction. Existing approved/pending/held rows must remain valid; no new table is required.
2. For the shared Supabase database, the project owner must review/run the new SQL in the Supabase SQL editor before merging; no agent operation against Supabase is authorised here. Existing SQL scripts must not be rewritten. No new table means no `test_role.sql` rerun is required.
3. For the **existing local Docker test database**, prefer applying the same additive SQL explicitly after GREEN approval. Reverify the exact container, loopback endpoint, database and local owner role before any owner operation; then reverify the restricted test target and run `tests.test_app_factory`. Do not use `create_all()` as an upgrade procedure: it creates missing tables but does not add columns to existing tables.
4. If a clean local rebuild is needed, obtain explicit approval for that separate operation. Preserve any needed test data/volume, verify that only `trueadams-test-pg` and its explicitly identified local storage are affected, and provision a genuinely empty local database before using `ci/build_test_database.py`. The script's owner URL must be loopback; apply the restricted-role setup as the repository's CI does, restore the expected `127.0.0.1:5433/postgres` target, and run the model/table baseline before feature tests. Never run the builder against existing tables and assume it migrated them. No rebuild/drop/reset was performed during RED.
5. CI's throwaway PostgreSQL is built from updated SQLAlchemy models, so it will include the new field on a fresh build. The separate Supabase schema job still requires the owner's SQL to have been applied. Verify both paths during GREEN; the current passing local baseline only establishes compatibility of the **current unchanged** model and schema.

**Historical RED stop point:** no production/schema work had been performed at that stage. The subsequent explicit GREEN instruction authorised Phase 4 below.

## Phase 4 — GREEN implementation and verification

**Result, 21 Oct 2026:** all six original ACs are implemented. Final targeted execution: **119 backend tests PASS; 42 frontend instances PASS**, with no failures, skips, database connection errors or schema mismatches. Earlier audit/RED descriptions are historical, not the current implementation status.

### Exact implementation scope

| Production file | Change and reason |
|---|---|
| `backend/app/venues/routes.py` | Add `POST /api/venues/bookings/<id>/reject` with current stored-user/role checks, nonblank text reason of at most 500 characters, refreshed request-row lock and Pending-only decision. Save rejected status, reason, UTC decision time and staff, plus the current coordinator's in-app notification in one commit; queue email afterwards through the existing helper. No availability check, booking insert, hold or Event venue update occurs. |
| Same routes file | Add coordinator mode to existing `GET /api/venues/bookings` using `event_id`. Validate ownership with `is_current_coordinator`, return only this event's persisted request rows and decision fields, newest first. The existing staff pending-list response remains unchanged when the parameter is absent. SQLAlchemy failures are retryable 503 errors. `_require_viewer(roles=None)` loads a valid stored user and defers the role check until record lookup; existing callers retain their existing role checks. |
| `backend/app/models.py` | Add only nullable `VenueBooking.rejection_reason` text; reuse existing decision timestamp/staff fields. No unrelated model or Event field changed. |
| `frontend/src/pages/VenueBookingRequestsPage.jsx` | Add accessible per-request reason/Reject controls, matching character validation, shared Axios decision handling, removal/reload after success and retained per-request reasons on errors. Existing approval/hold behaviour is retained. |
| `frontend/src/pages/VenueBookingRequestPage.jsx` | Load persisted outcomes through the authorised event-filtered bookings API. Show previous rejection, venue, period and full reason alongside the existing form/receipt/confirmed venue. A retryable outcome-read failure has its own Retry action, which preserves unsent form details. No notification read is required for decision recovery. |
| New `backend/db/venue_booking_rejections.sql` | Idempotent additive migration for the one nullable column; no new table, index, default or data rewrite. |

The notification model, listing API, email task, scheduling rules, existing approval/hold route bodies, planning API, CI workflow and dependencies were not changed.

### Necessary test adjustments

- The GREEN instruction explicitly superseded RED's notification-only visibility assumption. The three coordinator frontend cases now mock the event-filtered **booking records**, assert the persisted reason/status/period, preserve later confirmed-venue display, and retry saved-outcome failures without losing input. The notification API is not called for recovery. This changes the data source to satisfy AC4; it does not weaken reason/visibility assertions.
- Two focused integration methods were added: `test_coordinator_recovers_saved_decision_without_notifications` forbids notification SELECTs and proves a newly assigned coordinator can read an earlier saved decision; `test_saved_decisions_require_current_coordinator_and_report_read_failure` covers denied roles, no JWT and a retryable database read failure.
- All 18 original backend methods and their assertions remain. The local-only target guard now also permits the existing CI service at `localhost:5432/postgres` with the restricted role. The exact execution target here remained `127.0.0.1:5433/postgres`; no CI database or Supabase connection was made. This avoids making the new tests incompatible with the existing workflow.
- The first GREEN backend run found two defects in the newly added read-access test: the inherited seed lacks the separately defined lead user, and Flask-JWT's missing-token response uses `msg`, whereas the reused domain-error helper requires `error`. The test now creates its own lead with `make_user` and checks the existing missing-token 401 contract. The subsequent full targeted run passed; no production auth handler or unrelated fixture was changed.

### Actual before/after results

| Target | RED evidence | Final GREEN evidence |
|---|---|---|
| Original SCRUM-69 backend methods | 18 methods fail, 42 assertion failures counting input subtests, zero errors | All 18 PASS, including previously unreached persistence, 500-character, rollback, notification INSERT failure, recovery, commit-order, broker failure and mocked eager SMTP-failure assertions |
| Additional coordinator read checks | Not present in RED | 2 PASS; SCRUM-69 backend total is 20 |
| Existing booking request regression module | Not run in RED | 25 PASS |
| Existing booking approval regression module | Not run in RED | 24 PASS |
| Existing booking conflict regression module | Not run in RED | 10 PASS |
| Existing tentative hold regression module | Not run in RED | 33 PASS |
| App-factory schema/role/API checks | 7 PASS before and after RED | 7 PASS before GREEN changes and 7 PASS after the local migration, included in the final run |
| Two frontend booking-page files | 28 existing PASS, 14 SCRUM-69 fail | All 42 PASS: 28 existing and 14 SCRUM-69 |
| Final targeted backend total | — | **119 PASS: 20 SCRUM-69 + 92 existing venue regressions + 7 app-factory** |

No full backend suite or unrelated frontend suite was run. No live email was sent. Real competing-transaction races, manual browser verification, supplementary Unicode/normalisation boundary variants, extra JSON-key refusal, legacy-context variants and the broader calendar/search scenarios remain **Not run / Planned** as identified above. The real PostgreSQL failure hooks were reached during GREEN; rollback is now supported by executed assertions rather than just RED scaffolding. Row locking follows the existing approval/hold pattern; no claim of a real concurrency race test is made.

### Current AC-to-evidence traceability

| AC | Current implementation and executed evidence |
|---|---|
| AC1 | Existing pending-list API/UI unchanged; SCRUM-39 viewing, role, empty and load-error coverage passes in the targeted request module/frontend files (TC-69-01). |
| AC2 | `reject_booking()` reloads the stored caller, locks/refreshes the request and only updates `pending`; state/auth/duplicate tests pass (TC-69-02–07). Tentative rows remain ineligible even when expired. |
| AC3 | Backend and frontend enforce required nonblank text and the 500-character boundary; direct API 501 refusal and persisted full 500-character reason pass (TC-69-09–12, 24–25). |
| AC4 | Reason and decision metadata persist on `VenueBooking`. The current coordinator reads those rows independently of notifications, including after reassignment; wrong-user requests are denied and frontend saved display/recovery passes (TC-69-02, 11, 14–15, 26). |
| AC5 | The same request ID remains; test-owned booking IDs, all original request details and every Event field remain unchanged except the request's decision fields; no hold details are created (TC-69-02/16). Scheduling/regression rules still pass. |
| AC6 | One current-coordinator in-app notification with full reason is committed with the decision, then email is queued. Correct recipient after reassignment, notification ownership, rollback and queue/delivery-failure durability assertions pass (TC-69-17–21). |

### Exact GREEN testing commands

From `backend/`, each test shell set the following environment explicitly before importing the app. These are the supplied **local-only** credentials; no environment file was edited:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://connectsphere_test:ci-only@127.0.0.1:5433/postgres'
$env:OWNER_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/postgres'
$env:TEST_ROLE_PASSWORD = 'ci-only'
$env:DATABASE_URL = $env:OWNER_DATABASE_URL
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PATH = (Resolve-Path '.venv/Scripts').Path + ';' + $env:PATH
python -c "from app.config import TestConfig; from sqlalchemy.engine import make_url; u=make_url(TestConfig.SQLALCHEMY_DATABASE_URI); print('Test database:',u.host,u.port,u.database,u.username); assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'UNSAFE DATABASE TARGET!'"
if ($LASTEXITCODE -ne 0) { throw 'Database verification failed.' }
```

The initial unchanged-schema baseline command was:

```powershell
python -m unittest -v tests.test_app_factory
if ($LASTEXITCODE -ne 0) { throw 'Initial baseline failed.' }
```

The final targeted command (after resetting the full environment and re-running the verification above in the same shell) was:

```powershell
$greenLog = Join-Path $env:TEMP 'scrum69-backend-green.log'
python -m unittest -v tests.test_venue_booking_rejection tests.test_venue_booking_request tests.test_venue_booking_approval tests.test_venue_booking_conflicts tests.test_venue_holds tests.test_app_factory *> $greenLog
$greenExit = $LASTEXITCODE
```

Final output: `Ran 119 tests in 5.690s`, `OK`, exit code 0. The earlier test-defect run reported one assertion failure and one subtest error, both in the added read-access test described above; neither was counted as GREEN. No database error or schema mismatch occurred in either run.

From `frontend/`, the exact targeted command was:

```powershell
$greenLog = Join-Path $env:TEMP 'scrum69-frontend-green.log'
npm.cmd test -- src/pages/VenueBookingRequestsPage.test.jsx src/pages/VenueBookingRequestPage.test.jsx --reporter=verbose *> $greenLog
$greenExit = $LASTEXITCODE
```

Final output: `Test Files 2 passed (2)`, `Tests 42 passed (42)`, exit code 0. Execution escalation was used for the previously identified esbuild sandbox directory restriction; no config or dependency change was made.

### Migration applied locally and teammate hand-off

Docker inventory reconfirmed `trueadams-test-pg` running with `127.0.0.1:5433->5432/tcp`. Before connecting for the migration, the effective test URL and owner URL were parsed and asserted as the exact supplied loopback endpoints. The connected owner identity/database were checked as `postgres` / `postgres`. The script was applied with a raw local SQLAlchemy/psycopg2 cursor in autocommit mode so the SQL file controls its own `begin`/`commit`. Information-schema column sets and the booking-row count were compared before/after.

Observed migration result: **only `rejection_reason` added; booking-row count unchanged (0 before, 0 after)**. No DROP, DELETE, reset, rebuild, volume operation or other schema change was executed. An initial shell-quoting attempt stopped with a Python syntax error before any connection; the migration then succeeded using a literal PowerShell here-string. Supabase was never accessed.

The complete SQL addition in [venue_booking_rejections.sql](../../backend/db/venue_booking_rejections.sql) is:

```sql
begin;

alter table public.venue_bookings
  add column if not exists rejection_reason text;

commit;
```

For teammates updating an **existing** local Docker database, activate/use the existing backend virtual environment, run the full local environment/verification block above, and confirm the container inventory. Then run this guarded additive application from `backend/`:

```powershell
@'
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

url = make_url(os.environ["OWNER_DATABASE_URL"])
assert (url.host, url.port, url.database, url.username) == (
    "127.0.0.1", 5433, "postgres", "postgres"
), "UNSAFE MIGRATION TARGET"
engine = create_engine(url)
connection = engine.raw_connection()
try:
    connection.autocommit = True
    cursor = connection.cursor()
    cursor.execute("select current_database(), current_user")
    assert cursor.fetchone() == ("postgres", "postgres")
    cursor.execute(Path("db/venue_booking_rejections.sql").read_text(encoding="utf-8"))
finally:
    connection.close()
    engine.dispose()
'@ | python -
if ($LASTEXITCODE -ne 0) { throw 'Migration failed; do not reset the database.' }
```

This is a reproducible shorter version of the successful guarded application, without the extra column/row-count audit reads. The file is idempotent and adds only a nullable column; no `test_role.sql` rerun is required because the existing table's grants/policies remain in place.

Re-run the effective **test-role** verification immediately before checking compatibility:

```powershell
python -c "from app.config import TestConfig; from sqlalchemy.engine import make_url; u=make_url(TestConfig.SQLALCHEMY_DATABASE_URI); print('Test database:',u.host,u.port,u.database,u.username); assert (u.host,u.port,u.database,u.username)==('127.0.0.1',5433,'postgres','connectsphere_test'), 'UNSAFE DATABASE TARGET!'"
if ($LASTEXITCODE -ne 0) { throw 'Database verification failed.' }
python -m unittest -v tests.test_app_factory
```

For a **genuinely new, empty local/CI database**, `ci/build_test_database.py` creates the current model schema and restricted-role setup, including this column, using the verified loopback owner URL. That builder was not run during this task. It uses `create_all()`, which does **not** add columns to an existing table; existing local databases must apply the additive SQL above. No destructive rebuild procedure is needed for SCRUM-69.

For shared **Supabase**, the project owner must later run **`backend/db/venue_booking_rejections.sql` in the Supabase SQL editor before merging**. The separate Supabase schema CI job will otherwise detect the model/table mismatch. No agent applied or verified that remote migration. Current local GREEN results do not establish remote schema compatibility.

**Stop point:** implementation, targeted verification and documentation are complete. No commits, pushes or PRs were made. Remaining hand-off is the owner's shared-schema application; deferred scenarios above have not been represented as executed.
