# SCRUM-27 — Access Authorised Event Information and Functions: Test Cases

**User story:** As a system user, I want to sign in and access information and functions permitted for my role and involvement in an event so that I can carry out my activities while other users’ information remains protected.

**Documentation reviewed:** 19 Oct 2026, checked-out baseline `9d188f9`. **Execution status:** not executed during this documentation update. Existing test assertions were inspected, not imported or run.

**Sources:** [authentication integration tests](../../backend/tests/test_auth.py), [authorisation integration tests](../../backend/tests/test_authorization.py), [permission unit tests](../../backend/tests/test_authorization_unit.py), [HTTP unit tests](../../backend/tests/test_authorization_http_unit.py), [login component tests](../../frontend/src/pages/LoginPage.test.jsx), [API client tests](../../frontend/src/api/client.test.js). Related requirements: [SCRUM-81 initial assignment](SCRUM-81-lead-assigns-coordinator.md), [SCRUM-82 reassignment](SCRUM-82-lead-reassigns-coordinator.md), [SCRUM-83 Lead role](SCRUM-83-lead-assigned-events.md).

## Acceptance criteria and traceability

**Requirements source:** authoritative Jira wording supplied by the user in the final reconciliation request, 19 Oct 2026 (no Jira URL supplied). AC wording below is exact; later Coordinator Lead rules are documented separately. No tests were executed during this reconciliation.

| ID | Official Jira acceptance criterion | Test cases |
|---|---|---|
| AC1 | A user with valid authentication details can sign in. | TC-27-09, 12 |
| AC2 | A user with invalid authentication details is not granted access, and an error with reasoning is displayed. | TC-27-10; 11 supports failed-login session retention |
| AC3 | Access follows the agreed permissions for Event Organisers, Event Coordinators, Venue Staff, Technical Support Staff, and Attendees. | TC-27-01/02, 05, 06, 09, 13, 15 |
| AC4 | Where access depends on involvement in an event, the user can access only events and information permitted by that relationship. | TC-27-01/02, 03, 04, 05, 06, 13 |
| AC5 | Attempting to access or modify restricted information is denied, including through a direct link or request, and the information remains unchanged. | TC-27-01/02, 03–08, 13–15 |
| AC6 | If authentication fails because the service is unavailable, access is not granted and the user is informed that they can retry. | TC-27-11 (authentication outage/retry assertions only) |

TC-27-16 is supplementary reassignment-failure coverage. It is not evidence for AC6, which specifically concerns authentication-service unavailability. AC3/AC4 coverage follows the endpoint-specific rules below; no exhaustive whole-system permission matrix is claimed.

## Current rules and boundaries

- **A1 / Q1 — Resolved:** the supplied Jira story and six exact criteria replace the earlier reconstructed groupings. Test-case IDs and historical execution records are retained; their AC references now use the official numbering.
- **A2 / Q2:** use the established endpoint-specific permissions. Coordinator information is readable by admin, coordinator, venue staff and tech staff, plus the event's current organiser owner. That broader information access does not grant review, planning or clarification-writing rights. Venue browsing/details allow coordinator and venue staff. Do not infer a universal admin override or a new staff event scope.
- **Confirmed change:** [SCRUM-82 AC6 and “What changes from SCRUM-27/33”](SCRUM-82-lead-reassigns-coordinator.md) records team agreement on 17 Oct 2026: only `coordinator_lead` may reassign. Admin and current coordinator are now denied. The tests were updated accordingly. A Lead's initial assignment uses SCRUM-81; the reassignment endpoint refuses an unassigned event with 409 and `reason: "not_assigned"`.
- Review/planning/decision/question-sending require both the stored coordinator role and the current event assignment. Clarification history also allows the current organiser owner; its `can_send: false` does not grant question-sending rights.
- The SPA exposes navigation/page shells without role gating. Direct URL protection here means API refusal and absence of private payloads, not a claim that every page redirects to Login.

## Fixtures and reference key (AUTH-SEED)

Integration cases use `AppTestCase` users/events inside rolled-back transactions; no empty-database assumption or manual reset is required. `AuthorizationEvidenceTests` creates an organiser, assigned coordinator and submitted event; individual cases add an unrelated caller, replacement or Lead. Login tests use `AuthTests.PASSWORD` and `make_login_user()` (hashed password, unique test email).

HTTP unit fixtures: organiser 1, current coordinator 2, replacement coordinator 3, attendee 4, admin 5, Lead 6, submitted event 7 owned by 1 and assigned to 2. Persistence/email are mocked with Engine/socket guards. Pure rules use `SimpleNamespace`. Component tests use `MemoryRouter` and mocked HTTP; client tests use an adapter, not a server.

References below resolve as follows; every `Class.method` is in the named file. Quoted frontend titles identify actual `it`/`it.each` declarations.

| Key | Test implementation |
|---|---|
| AUTH | [test_auth.py](../../backend/tests/test_auth.py), `AuthTests` |
| DB | [test_authorization.py](../../backend/tests/test_authorization.py), `AuthorizationEvidenceTests` |
| RULE | [test_authorization_unit.py](../../backend/tests/test_authorization_unit.py), `EventPermissionTests` |
| HTTP | [test_authorization_http_unit.py](../../backend/tests/test_authorization_http_unit.py), `AuthorizationHttpUnitTests` |
| LOGIN | [LoginPage.test.jsx](../../frontend/src/pages/LoginPage.test.jsx), `SCRUM-27 sign-in` |
| CLIENT | [client.test.js](../../frontend/src/api/client.test.js), `shared API client authentication` |

## Test-case register

TC-27-01–08 retain the grouping IDs mentioned in the existing authorisation modules; their original external register was unavailable. The source explicitly groups TC-27-01/02 for unrelated reassignment/self-assignment, so they remain one register row, with existing positive Lead coverage alongside. Later IDs below organise existing assertions only; they do not represent newly implemented tests. Expected results describe current requirements/behaviour, not execution results.

| Test ID | AC | Scenario / Preconditions | Action / Input | Expected Result | Test Type | Automated Test Reference |
|---|---|---|---|---|---|---|
| TC-27-01 / TC-27-02 | AC3, AC4, AC5 | Assigned submitted event; unrelated coordinator versus current stored Lead, admin/current coordinator. | Unrelated coordinator PUT to self-assign/replace coordinator and GET eligible coordinators; positive Lead PUT; repeat as admin/current coordinator. | Unrelated/admin/current coordinator get 403 without event details or changes; denied unit calls make no commit/add/email and unrelated GET makes no candidate lookup. Lead gets 200, replacement stored and lock/commit requested. | Integration; HTTP/rule unit | DB and HTTP `test_unrelated_coordinator_cannot_reassign_or_self_assign`; HTTP `test_lead_can_reassign_and_lock_is_requested`, `test_admin_and_current_coordinator_cannot_reassign`; RULE `test_only_leads_can_reassign` |
| TC-27-03 | AC4, AC5 | Lead reassigns; previous/replacement JWTs minted before reassignment. | Reuse tokens for planning/review/history reads and planning/decision/question/reassignment writes. | Old coordinator loses event reads/writes; denied writes leave fields/notifications unchanged and send no email. Replacement gets reads, planning edit 200, question 201, decision 200. Neither coordinator may list replacements. | Integration; HTTP/rule unit | DB `test_reassignment_moves_event_specific_read_and_write_privileges`; HTTP `test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them`; RULE `test_event_access_moves_to_new_coordinator` |
| TC-27-04 | AC4, AC5 | Event has no coordinator. | Try initial assignment via reassignment PUT as admin/coordinator, then Lead. | Non-Leads get 403. Lead gets 409 `not_assigned`; event unchanged. Initial assignment belongs to SCRUM-81. | Integration; HTTP/rule unit | DB `test_unassigned_event_cannot_be_assigned_through_reassignment_api`; HTTP `test_admin_and_current_coordinator_cannot_reassign`; RULE `test_unassigned_event_has_no_manual_initial_assignment` |
| TC-27-05 | AC3, AC4, AC5 | Owner's stored role changes; reuse original organiser token. | GET coordinator/history and organiser requests as attendee/coordinator/venue staff/tech staff. | Ownership alone gives no owner-only rights. History/organiser list denied; coordinator-information access remains for legitimate new internal roles, but not attendee. | Integration; HTTP/rule unit | DB `test_former_organiser_loses_owner_only_reads_with_original_token`; HTTP `test_former_organiser_loses_owner_reads_but_retains_new_role_permissions`; RULE `test_owner_must_still_be_an_organiser`, `test_new_role_preserves_its_legitimate_coordinator_information_access` |
| TC-27-06 | AC3, AC4, AC5 | Owner/current coordinator versus unrelated callers. | GET coordinator/history, or history `can_send`. | Own organiser can read coordinator; unrelated organiser denied. Unrelated history readers (organiser, coordinator, staff, attendee, admin) denied. Owner history has `can_send: false`, current coordinator true. | Integration; HTTP unit | DB `test_organiser_can_read_own_coordinator_but_not_unrelated_event_details`, `test_unrelated_users_cannot_read_clarification_history`; HTTP `test_read_only_clarification_history_has_no_sending_capability` |
| TC-27-07 | AC5 | Valid Lead or assigned coordinator, otherwise valid target/body. | Add organiser/event/user/status/audit fields to reassignment; PATCH identity/status/decision/registration-settings fields through planning. | Reassignment extras get 400; noneditable planning fields get 422. No mutation/commit/notification/email. | Integration; HTTP unit | DB `test_forged_reassignment_fields_leave_all_persisted_fields_unchanged`; HTTP `test_forged_relationship_fields_are_rejected_before_mutation`, `test_planning_cannot_smuggle_identity_or_noneditable_fields` |
| TC-27-08 | AC5 | Missing/deleted/nonnumeric identity, or malformed/expired/refresh/wrong-signature token. | Direct protected event requests; invalid-token unit case enumerates JWT-decorated events routes/methods. | Missing/deleted/nonnumeric user gets 401. Invalid token rejected with 401/422 before user lookup; no protected operation reached. | HTTP unit | HTTP `test_missing_deleted_and_nonnumeric_user_sessions_are_rejected`, `test_invalid_tokens_never_reach_the_user_lookup` |
| TC-27-09 | AC1, AC3 | Valid hashed credentials; coordinator or attendee user. | POST `/api/auth/login`; use returned JWT for venue details. | 200 nonempty access token with string user-id identity; no password/hash disclosure. Coordinator gets venue 200; authenticated attendee still gets 403 without venue name. | Integration | AUTH `test_valid_credentials_return_usable_access_token`, `test_login_token_preserves_role_restrictions` |
| TC-27-10 | AC2 | Wrong password/unknown email; missing/empty credentials. | POST credentials; submit corresponding login form. | Wrong password/unknown email share 401 public error; absent/empty fields get 400. UI explains refusal and stays at Login without creating a session. | Integration; component | AUTH `test_invalid_credentials_are_rejected`, `test_missing_or_empty_credentials_are_rejected`; LOGIN `displays the backend 401 explanation without authenticating or navigating`, `gives visible feedback for an empty %s`, `displays a backend 400 validation error` |
| TC-27-11 | AC2, AC6 | User lookup outage or frontend server/network failure. | Sign in, recover service, retry; also fail with an existing session. | Backend 503 with retry guidance and no token/private details. UI permits retry, stores token/navigates on success, clears error; failed login preserves an existing token. | Integration; component | AUTH `test_authentication_service_failure_is_retryable`; LOGIN `displays retry guidance for an authentication service outage`, `displays retry guidance for a network failure without an HTTP response`, `allows retry after failure and clears the error on successful navigation`, `preserves an existing session after a failed %s login` |
| TC-27-12 | AC1 | Login component and shared client; mocked response/adapter. | Enter credentials; receive token; initialise/reinitialise client with token before/after initialisation or none. | Correct POST body; token saved in sessionStorage and Events opened. Requests use current bearer token; no Authorization header when none stored. | Component; client unit | LOGIN `submits entered credentials to POST /auth/login`, `stores the returned token in sessionStorage and navigates to Events`; CLIENT `uses a sessionStorage token after fresh client initialization`, `uses a token stored after the client was initialized`, `omits Authorization when there is no session token` |
| TC-27-13 | AC3, AC4, AC5 | Previously authorised coordinator/Lead token; stored role changed, or forged admin/Lead claim. | Reuse token on venue/event reads and reassignment. | Stored role wins: 403 without details; event unchanged. Matching assigned id without coordinator role grants no coordinator privilege. | Integration; HTTP/rule unit | DB `test_venue_access_uses_current_role_with_an_existing_token`, `test_event_access_and_reassignment_use_current_role_with_an_existing_token`; HTTP `test_forged_role_claim_cannot_authorize_reassignment`; RULE `test_assigned_identity_alone_does_not_grant_coordinator_privileges` |
| TC-27-14 | AC5 | Unauthorised roles; unrelated caller with invalid target. | PUT reassignment, including malformed target. | 403 before target validation; all persisted event fields unchanged across organiser/attendee/staff/admin/current coordinator denials. | Integration; HTTP unit | DB `test_unauthorized_reassignment_preserves_every_persisted_event_field`; HTTP `test_authorization_precedes_validation` |
| TC-27-15 | AC3, AC5 | Attendee/unrelated organiser/staff directly request internal endpoints. | GET venue list/details and event coordinator/eligible/planning/review/history as covered by each matrix. | 403 without private venue/event/coordinator data. Page navigation cannot bypass these backend guards. | Integration; HTTP unit | DB `test_attendee_direct_reads_do_not_disclose_internal_information`; HTTP `test_unrelated_organiser_and_attendee_direct_reads_are_denied` |
| TC-27-16 | Supplementary resilience (not AC6) | Reassignment user/event read or commit raises SQLAlchemyError. | Lead PUT reassignment. | 503 `retryable: true`, rollback, no private exception or success payload. Read failure does not commit. Mocked rollback does not prove persistence durability. | HTTP unit | HTTP `test_database_failure_is_retryable_and_rolls_back`, `test_failed_commit_requests_rollback_without_a_success_payload` |

## Implementation traceability

| Cases | Production route/component and enforcement |
|---|---|
| 09–12 | [auth/routes.py](../../backend/app/auth/routes.py) `login`: credential validation, user lookup, password hash check, string-id JWT. [LoginPage.jsx](../../frontend/src/pages/LoginPage.jsx) `handleSubmit`: validation, token storage, feedback/navigation. [api/client.js](../../frontend/src/api/client.js): bearer-token interceptor. |
| 01–08, 13–16 | [events/permissions.py](../../backend/app/events/permissions.py): `is_coordinator_lead`, `is_current_coordinator`, `is_current_organiser`, `can_view_coordinator`, `can_view_clarifications`. [events/routes.py](../../backend/app/events/routes.py): `_current_user`, `assign_coordinator`, `list_eligible_coordinators`, `_require_reassignable`, `get_coordinator`, `get_planning`, `update_planning`, `review_request`, `_assigned_request`, `decide_request`, `list_clarifications`, `send_clarification`, `list_my_requests`. JWT decorators reject invalid tokens before these handlers. |
| 09, 13, 15 | [venues/routes.py](../../backend/app/venues/routes.py) `_require_viewer`, `VENUE_VIEWER_ROLES`: stored-role venue restrictions. |
| Direct URL context | [App.jsx](../../frontend/src/App.jsx): route/page shells. Existing SCRUM-55 direct-navigation component cases `shows a %s refusal without exposing request data` in [ReviewRequestsPage.test.jsx](../../frontend/src/pages/ReviewRequestsPage.test.jsx) supplement TC-27-15; this is cross-story evidence, not a new SCRUM-27 test. |

## Historical execution evidence

No dedicated SCRUM-27 execution report or raw run output was found. Git commits `a261144` (27 Sep 2026, authentication/tests) and `6567308` (13 Oct 2026, event-scoped authorisation) establish implementation history, **not passing execution results**.

| Existing evidence source | Recorded outcome | Limit |
|---|---|---|
| [SCRUM-55 section H](SCRUM-55-review-submitted-event-request.md), 14 Oct 2026 | Its exact backend selection reports HTTP `test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them` and `test_unrelated_organiser_and_attendee_direct_reads_are_denied` passing, within 9 backend/22 frontend passes. | Historical report; before SCRUM-82 changed reassignment to Lead-only. Does not establish all current authorisation tests pass. |
| [SCRUM-82 header and change record](SCRUM-82-lead-reassigns-coordinator.md), 17 Oct 2026 | Reports automated cases passing on local PostgreSQL + Vitest and lists all three affected SCRUM-27 authorisation modules among updated tests. | Narrative status without a per-method SCRUM-27 execution log/count. Do not infer a complete SCRUM-27 run or a current-build result. |

## Gaps and open questions

| ID | Gap / question | Impact |
|---|---|---|
| Q1 (resolved) | Official story and all six Jira criteria supplied on 19 Oct 2026. | Exact wording recorded above and existing cases remapped; no execution/sign-off inferred. |
| Q2 | Jira AC3 names five roles but does not enumerate an exhaustive endpoint-level permission matrix. | Documented cases cover existing role/relationship boundaries; broader whole-system permission completeness is not established. Lead rules remain governed by the linked later requirements. |
| G1 | No current execution performed; no full login-to-protected-page browser evidence located for SCRUM-27. | Component, rule, HTTP and integration source coverage must not be described as an executed end-to-end flow. |
| G2 | HTTP mocks cannot establish real row locks, transaction rollback/durability or Supabase policies. | Persisted tests exist, but their latest full execution is not established here. |
| G3 | [ClarificationPage.jsx](../../frontend/src/pages/ClarificationPage.jsx) renders its composer without consulting the API's `can_send`; its local `canSend` controls text/busy state. The API still denies unauthorised sending. | Existing SCRUM-55 section E observation remains a UI capability mismatch; no frontend test here asserts organiser read-only controls. No code change made. |

## Course alignment

[Week 2](../../Slides%20+%20Docs/Week2-UserStories.pdf): measurable ACs (printed slide 27, PDF page 25), Given–When–Then (PDF page 27), checklist/scenario choice (slide 34, PDF page 28), testability (slide 44, PDF page 38), and story → AC → case → test class → code (slide 67, PDF page 60). The supplied deck's pagination differs from printed slide numbers. [Week 4: Test Cases & Software Architecture](../../Slides%20+%20Docs/Week4-TestCases_SoftwareArchitecture.pdf), pages 21–24 and 26–32, supports explicit conditions/inputs/results, separate execution records and focused positive/negative/boundary coverage. Page 23 calls the template one useful representation; Markdown does not imply a prescribed course file format.
