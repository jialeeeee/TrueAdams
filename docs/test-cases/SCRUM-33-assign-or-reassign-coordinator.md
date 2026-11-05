# SCRUM-33 — Assign or Reassign an Event Coordinator: Test Cases

**User story:** As an Event Coordinator Lead, I want to assign or reassign the Event Coordinator for a submitted event so that each event has a clear point of contact responsible for coordinating its arrangements.

**Created:** 5 Nov 2026, from the Sprint 1 test-case sheet and the automated tests written with it. The story was built in Sprint 1, before this template; this document records the same cases in the template, and no behaviour changed. · **Automated tests:** `backend/tests/test_event_coordinator.py`, `frontend/src/pages/EventDetailsPage.test.jsx` ("SCRUM-33 the event's coordinator") · **Status of all cases:** automated cases pass (5 Nov 2026, local PostgreSQL built by `ci/build_test_database.py`, and CI) · **Related:** SCRUM-61 (a coordinator asks to be reassigned), SCRUM-80/81 (the Lead's queue assigns an unassigned event), SCRUM-82 (only a Lead reassigns, W705), SCRUM-27/76 (who may see what)

**Changed by W705 (Week 7):** assignment moved to the Event Coordinator Lead, with no automatic assignment and exactly one coordinator per event. SCRUM-81 now makes the first assignment from the Lead's queue and SCRUM-82 restricts reassignment to Leads, so this story's endpoint refuses a first assignment (409) and refuses admins and coordinators (403). The cases below are the current ones.

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The authorised user can view the event's current assignment and select a coordinator eligible under the agreed assignment rules. |
| AC2 | Successful assignment records the selected coordinator and assignment time against the event and displays confirmation. |
| AC3 | An event has at most one current main coordinator. |
| AC4 | Relevant users can view the current coordinator. |
| AC5 | Successful reassignment replaces the previous current assignment without creating two main coordinators. |
| AC6 | If no eligible coordinator is available, the user is informed; the existing assignment, if any, and event status remain unchanged. |
| AC7 | If saving fails, the previous assignment remains unchanged and an error is displayed. |

## Working assumptions

- **A1 — Who assigns (AC1):** only Event Coordinator Leads, as main or additional role (W705, SCRUM-82). Admins, coordinators (including the current one), organisers and other staff are refused with 403. A coordinator who wants to hand an event over asks through SCRUM-61.
- **A2 — First assignment (AC1, AC2):** an event with no coordinator is assigned from the Lead's queue (SCRUM-81), so this endpoint refuses it with 409 and saves nothing.
- **A3 — Eligible (AC1):** every user holding the coordinator role, except the event's current coordinator. A coordinator may coordinate several events.
- **A4 — One coordinator (AC3, AC5):** `Event.coordinator_id` is a single nullable column, so an event can never hold two current coordinators; `coordinator_assigned_at` (naive UTC) is set on every assignment.
- **A5 — Who sees the coordinator (AC4):** admins, coordinators, the event's organiser, Venue Staff and Technical Support Staff. Attendees and other organisers are refused (403); the front end then shows nothing about the coordinator.
- **A6 — Not assignable (AC6):** draft and cancelled events can't be reassigned (409).
- **A7 — Order of checks:** 401 → 404 → 403 → 400, then the chosen coordinator (422) and the event's state (409), then a failed save (503), as AGENTS.md orders; a refusal changes nothing.

There are no open customer questions: W705 answered who assigns.

## Seed data (CO-SEED)

`tests/seed_data.py`: users **admin**; coordinators **alice**, **ben**, **chloe**; organisers **dana**, **evan**; attendee **farah**; Venue Staff **gus**; Technical Support **hana**; Leads **lena**, **liam**, **lucy**.

| Key | Event | Status | Organiser | Coordinator | Assigned at (UTC) |
|-----|-------|--------|-----------|-------------|-------------------|
| unassigned | Tech Summit 2026 | submitted | dana | — | — |
| assigned | Charity Gala | submitted | dana | alice | 2026-09-01 10:00 |
| evans_event | Product Launch | submitted | evan | ben | 2026-09-02 15:30 |
| draft | Draft Workshop | draft | dana | — | — |
| cancelled | Cancelled Meetup | cancelled | dana | — | — |

---

## AC1 — View the assignment and choose an eligible coordinator

**TC-33-01 · The current assignment is shown, or that there is none**
- **Traces to:** AC1, AC4 · **Type:** Happy path
- **Steps:** As admin, GET `/api/events/<id>/coordinator` for *unassigned*, then for *assigned*.
- **Expected result:** *unassigned*: 200 `{"event_id", "coordinator": null, "assigned_at": null}`. *assigned*: 200 with alice's id and email and `assigned_at` 2026-09-01T10:00.
- **Automated:** `test_unassigned_event_reports_no_coordinator`, `test_assigned_event_reports_current_coordinator_and_assignment_time`

**TC-33-02 · Eligible coordinators are every coordinator except the current one**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** A3
- **Steps:** As lena, GET `/api/events/<assigned>/eligible-coordinators`.
- **Expected result:** 200. Among the seed users: ben and chloe, each with id and email, and `message: null`. alice (current) is not listed; ben is listed although he coordinates *evans_event*; admin, dana, evan, farah, gus and hana never are.
- **Automated:** `test_lists_every_user_with_the_coordinator_role`, `test_listing_includes_contact_details_for_selection`, `test_excludes_the_events_current_coordinator`, `test_coordinator_of_another_event_is_still_eligible`, `test_never_lists_users_without_the_coordinator_role`, `test_message_is_null_when_coordinators_are_available`

**TC-33-03 · Only a Lead may list or choose**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** A1
- **Steps:** List eligible coordinators for *assigned* as admin, alice, ben, chloe, dana, farah, gus and hana. Try to assign chloe as each of them and as evan.
- **Expected result:** 403 with an error message every time; the assignment, its time and the event status are unchanged.
- **Automated:** `test_only_assigners_can_list_eligible_coordinators`, `test_non_assigners_cannot_assign`

**TC-33-04 · Only a coordinator can be chosen**
- **Traces to:** AC1 · **Type:** Negative (validation)
- **Steps:** As lena, assign *assigned* to admin, lena, dana, farah, gus and hana in turn; then to a user ID that doesn't exist.
- **Expected result:** 422 each time; nothing changes.
- **Automated:** `test_rejects_users_who_are_not_coordinators`, `test_rejects_a_user_that_does_not_exist`

**TC-33-05 · A malformed request is refused**
- **Traces to:** AC1 · **Type:** Negative (input)
- **Steps:** PUT the coordinator with: no `coordinator_id`; `null`; `"alice"`; a form body instead of JSON.
- **Expected result:** 400 each time; nothing changes.
- **Automated:** `test_rejects_malformed_requests`

**TC-33-06 · A valid session and an existing event are required**
- **Traces to:** AC1, AC4 · **Type:** Negative (authentication)
- **Steps:** View, list and assign without a token; with the token of a Lead whose account was deleted; and for an event ID that doesn't exist.
- **Expected result:** 401 without a valid session (nothing changes); 404 for the unknown event.
- **Automated:** `test_viewing_requires_authentication`, `test_listing_requires_authentication`, `test_assigning_requires_authentication`, `test_token_for_a_deleted_user_is_rejected`, `test_viewing_an_unknown_event_returns_not_found`, `test_listing_for_an_unknown_event_returns_not_found`, `test_assigning_to_an_unknown_event_returns_not_found`

**TC-33-07 · A first assignment goes through the Lead's queue** *(changed by W705)*
- **Traces to:** AC1, AC2 · **Type:** Business rule · **Depends on:** A2
- **Steps:** As lena, PUT alice as coordinator of *unassigned*.
- **Expected result:** 409; nothing is saved and nothing is committed. (SCRUM-81 assigns it from the queue.)
- **Automated:** `test_manual_initial_assignment_is_refused_without_a_commit`

## AC2 — Assignment is recorded and confirmed

**TC-33-08 · The coordinator and time are saved and confirmed**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As lena, assign ben to *assigned*.
- **Expected result:** 200 with a confirmation `message`, the event id and ben's id and email; the event stores ben with `coordinator_assigned_at` between the request's start and end, equal to the reply's `assigned_at`; the status stays submitted; *unassigned* and *evans_event* are untouched.
- **Automated:** `test_assignment_records_coordinator_and_time_and_confirms`, `test_assignment_does_not_change_event_status`, `test_assignment_leaves_other_events_untouched`

**TC-33-09 · Any Lead can assign; a coordinator can coordinate several events**
- **Traces to:** AC2 · **Type:** Positive
- **Steps:** lena assigns chloe to *assigned*; liam assigns chloe to *evans_event*. Separately, assign ben (already *evans_event*'s coordinator) to *assigned*.
- **Expected result:** each succeeds; ben coordinates both events.
- **Automated:** `test_every_assigner_role_can_assign`, `test_coordinator_can_coordinate_several_events`

**TC-33-10 · Draft and cancelled events can't be assigned**
- **Traces to:** AC2, AC6 · **Type:** Negative (state) · **Depends on:** A6
- **Steps:** Give *draft* and *cancelled* a coordinator, then try to assign ben to each; also cancel *assigned* and try again.
- **Expected result:** 409 each time; nothing changes.
- **Automated:** `test_rejects_events_that_cannot_be_assigned`, `test_reassigning_a_cancelled_event_is_rejected`

## AC3, AC5 — One current coordinator; reassignment replaces it

**TC-33-11 · The model holds exactly one coordinator**
- **Traces to:** AC3 · **Type:** Data integrity · **Depends on:** A4
- **Steps:** Inspect the model; create an event; give an event a coordinator and time.
- **Expected result:** `coordinator_id` is a single nullable reference to users and `coordinator_assigned_at` a nullable datetime; a new event has neither; an event stores one coordinator and one time.
- **Automated:** `test_new_event_has_no_coordinator`, `test_coordinator_column_is_a_nullable_reference_to_users`, `test_coordinator_assigned_at_is_a_nullable_datetime`, `test_event_stores_exactly_one_coordinator_and_assignment_time`

**TC-33-12 · Reassigning replaces the coordinator**
- **Traces to:** AC5 · **Type:** Happy path
- **Steps:** As lena, reassign *assigned* from alice to ben.
- **Expected result:** 200 with a confirmation; ben is stored with a new assignment time; viewing shows only ben and no event row still names alice; alice becomes eligible again (eligible: alice and chloe).
- **Automated:** `test_reassignment_replaces_the_previous_coordinator`, `test_reassignment_leaves_a_single_current_coordinator`, `test_previous_coordinator_becomes_eligible_again`

**TC-33-13 · Repeated reassignments keep only the latest**
- **Traces to:** AC3, AC5 · **Type:** Boundary
- **Steps:** Reassign *assigned* to ben, then chloe, then alice.
- **Expected result:** each step stores only that coordinator, the assignment times increase, and viewing shows alice.
- **Automated:** `test_repeated_reassignments_keep_only_the_latest_coordinator`

**TC-33-14 · Reassigning to the current coordinator is refused**
- **Traces to:** AC5 · **Type:** Negative (state)
- **Steps:** As lena, assign alice to *assigned* (she already is).
- **Expected result:** 409; the assignment time doesn't change.
- **Automated:** `test_reassigning_to_the_current_coordinator_is_rejected`

## AC4 — Relevant users see the current coordinator

**TC-33-15 · Who may see the coordinator**
- **Traces to:** AC4 · **Type:** Positive and negative (authorisation) · **Depends on:** A5
- **Steps:** View *assigned*'s coordinator as admin, alice, ben, dana, gus and hana; then as farah and evan.
- **Expected result:** the first six get alice's id and email; farah and evan get 403.
- **Automated:** `test_relevant_users_can_view_the_current_coordinator`, `test_unrelated_users_cannot_view_the_current_coordinator`, `test_new_assignment_is_visible_to_relevant_users`

**TC-33-16 · Frontend: the event page shows the coordinator and when they were assigned**
- **Traces to:** AC4 · **Type:** Frontend
- **Steps:** Open an event's details page with the coordinator endpoint returning alice; returning no coordinator; returning no assignment time; returning 403; failing.
- **Expected result:** "Coordinator: alice…" and "Assigned: <Singapore time>"; "No coordinator has been assigned yet."; "Assigned: Not recorded"; nothing about the coordinator (and no error) for a 403; on failure an alert while the rest of the event stays, and Retry reloads just that part.
- **Automated:** `EventDetailsPage.test.jsx` › "SCRUM-33 the event's coordinator" (the sheet's frontend cases TC-001, TC-002, TC-030 and TC-031)

## AC6 — Nobody eligible

**TC-33-17 · The Lead is told when no coordinator is eligible**
- **Traces to:** AC6 · **Type:** Negative (empty state)
- **Steps:** Leave alice as the only coordinator (others demoted, rolled back after); list eligible coordinators for *assigned*. Then leave none at all and list again.
- **Expected result:** 200 with an empty list and a non-blank `message` both times; the assignment and status are unchanged.
- **Automated:** `test_informs_the_user_when_no_coordinator_is_eligible`, `test_informs_the_user_when_there_are_no_coordinators_at_all`

**TC-33-18 · With nobody eligible, an attempt changes nothing**
- **Traces to:** AC6 · **Type:** Negative
- **Steps:** With alice the only coordinator, try to assign alice (409) and the demoted ben (422) to *assigned*; separately try to assign dana.
- **Expected result:** the stated refusals; alice remains the coordinator and dana sees her.
- **Automated:** `test_reassignment_with_no_eligible_coordinator_keeps_existing_assignment`, `test_rejected_reassignment_keeps_existing_assignment_visible`

## AC7 — A failed save changes nothing

**TC-33-19 · A failed save keeps the previous coordinator and says so**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Steps:** Make the commit fail and reassign *assigned* to ben; then view the coordinator.
- **Expected result:** 503 with an error and no `coordinator` in the reply; alice and the original assignment time remain, including on the next request (the session was rolled back).
- **Automated:** `test_failed_reassignment_keeps_previous_coordinator`, `test_failed_save_is_rolled_back_before_the_next_request`, `test_failed_save_does_not_report_success`

## Traceability matrix

| AC | Test cases | Automated |
|----|------------|-----------|
| AC1 | TC-33-01 to 07 | backend: ViewCurrentCoordinatorTests, EligibleCoordinatorTests, AssignCoordinatorTests, SaveFailureTests |
| AC2 | TC-33-07 to 10 | backend: AssignCoordinatorTests |
| AC3 | TC-33-11, 13 | backend: CoordinatorModelTests, ReassignCoordinatorTests |
| AC4 | TC-33-01, 06, 15, 16 | backend: ViewCurrentCoordinatorTests; frontend: EventDetailsPage |
| AC5 | TC-33-12 to 14 | backend: ReassignCoordinatorTests |
| AC6 | TC-33-10, 17, 18 | backend: EligibleCoordinatorTests, ReassignCoordinatorTests |
| AC7 | TC-33-19 | backend: SaveFailureTests |

## Open questions for the customer

None open. W705 (Week 7) and G4 clarifications settled who assigns and that an event has exactly one coordinator.
