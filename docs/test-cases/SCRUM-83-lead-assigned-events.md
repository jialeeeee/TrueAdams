# SCRUM-83 — Event Coordinator Lead Views the Events They Assigned: Test Cases

**User story:** As an Event Coordinator Lead, I want to see the active events I have assigned, with their coordinator and status, so that I can supervise those coordinators and spot events that are stuck.

**Created:** 16 Oct 2026 · **Status of all cases:** Automated cases pass (16 Oct 2026, local Postgres + Vitest; Supabase run pending `db/coordinator_lead.sql`). · **Automated tests:** `backend/tests/test_lead_assigned_events.py`, `frontend/src/pages/LeadAssignedEventsPage.test.jsx` · **Endpoint:** `GET /api/events/supervised` (new) · **Related:** Week 7 customer change 5 (Event Coordinator Lead role), SCRUM-27/33 (coordinator assignment), SCRUM-62 (a coordinator's managed events)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The Lead sees the active events whose coordinator that Lead assigned, with coordinator, status and date, and can filter the list by coordinator. |
| AC2 | Events assigned by other Leads are not listed. |
| AC3 | Only the Lead can open this view. Anyone else is denied and sees no event data. |
| AC4 | If the list cannot be loaded, the user is told and no partial list is shown. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who assigned:** each event records who made its current coordinator assignment (`Event.coordinator_assigned_by_id`, set by `PUT /api/events/<id>/coordinator`). Only the latest assignment counts: if anyone else reassigns the event, it leaves the Lead's list. Events assigned before this was recorded (for example automatically on submission) have no assigner and appear in no Lead's list. *(Q1)*
- **A2 — The Lead role:** a user whose stored role is `coordinator_lead`, read from the database on every request. *(Q1)*
- **A3 — Active:** an event is active while its status is `submitted`, `under_review`, `approved` or `confirmed`. Drafts and `rejected`, `cancelled` and `completed` events are not listed. The rule is `SUPERVISED_ACTIVE_STATUSES` in `app/events/routes.py`. *(Q2)*
- **A4 — Only the Lead:** every other role is refused with HTTP 403, administrators included, and the refusal carries no event or coordinator data. *(Q3)*
- **A5 — Date and order:** the date is the event's proposed start (`start_time`), Singapore time, shown exactly as recorded. Soonest first; events with no date last; ties by event ID. A blank name or a missing date is sent as `null` and shown as "Not recorded". *(Q4)*
- **A6 — Filter:** the filter offers every coordinator of the Lead's listed (unfiltered) events, by email. Choosing one lists only that coordinator's events; "All coordinators" lists everything again. A value that is not a user ID is refused with HTTP 400. A coordinator with none of the Lead's active events gives an empty list with a message.
- **A7 — Load failure:** HTTP 503 with `retryable: true` and no list. The page shows the message with a Retry button and removes any list it was showing, so an out-of-date list is never shown as current.
- **A8 — Opening an event:** the rows are not links: the planning view is for the event's own coordinator (SCRUM-34), so a Lead would be refused. *(Q5)*

## Endpoint under test

- `GET /api/events/supervised[?coordinator_id=<user id>]` → **200** `{"events": [event, ...], "coordinators": [user, ...], "message": str | null}`.
  - event = `{"id", "title", "start_time", "status", "coordinator": user}`; `title` and `start_time` are `null` when not recorded.
  - user = `{"id", "email"}`. `coordinators` is always the unfiltered set, ordered by email.
  - `message` is the empty-state text when `events` is empty, otherwise `null`.
- **401** without a valid session; **403** for anyone who is not a Lead (checked before the filter); **400** `{"error", "field": "coordinator_id"}` for a filter that is not a user ID; **503** `{"error", "retryable": true}` if loading fails.

## Seed data (LS-SEED)

Users come from `backend/tests/seed_data.py`, plus three Leads: lena, liam and lucy (`coordinator_lead`). lucy has assigned nothing. Times are Singapore time.

| Ref | Title | Status | Coordinator | Assigned by | Proposed date (start) |
|-----|-------|--------|-------------|-------------|-----------------------|
| S1 | Harbour Lights Festival | submitted | alice | lena | 12 Dec 2026 17:00 |
| S2 | Alumni Mixer | approved | ben | lena | 20 Nov 2026 18:30 |
| S3 | Charity Fun Run | under_review | alice | lena | 5 Nov 2026 07:00 |
| S4 | Year-End Showcase | confirmed | ben | lena | 30 Nov 2026 19:00 |
| S5 | *(spaces only)* | submitted | alice | lena | *not recorded* |
| S6 | Winter Networking Night | cancelled | alice | lena | 1 Oct 2026 09:00 |
| S7 | Startup Expo | rejected | ben | lena | 15 Nov 2026 10:00 |
| S8 | Spring Workshop | completed | chloe | lena | 10 Sep 2026 14:00 |
| S9 | Draft Workshop | draft | alice | lena | 15 Jan 2027 10:00 |
| S10 | Product Launch | submitted | ben | liam | 20 Nov 2026 14:00 |
| S11 | Tech Summit 2026 | submitted | chloe | admin | 10 Nov 2026 09:00 |
| S12 | Legacy Forum | submitted | alice | *not recorded* | 25 Nov 2026 09:00 |

---

## AC1 — The Lead's list and filter

**TC-83-01 · The Lead sees the active events they assigned**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As lena, load the list.
- **Expected result:** HTTP 200. `events` holds exactly S1–S5. `message` is `null`.
- **Automated:** `test_lead_sees_the_active_events_they_assigned`

**TC-83-02 · Each event shows its coordinator, status and date**
- **Traces to:** AC1 · **Type:** Happy path
- **Expected result:** S1 is `{"id", "title": "Harbour Lights Festival", "start_time": "2026-12-12T17:00:00", "status": "submitted", "coordinator": {"id", "email"} of alice}`. Every event shows its own status and current coordinator.
- **Automated:** `test_each_event_shows_its_coordinator_status_and_date`

**TC-83-03 · Inactive events are not listed**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q2
- **Expected result:** S6 (cancelled), S7 (rejected), S8 (completed) and S9 (draft) are not listed, although lena assigned them.
- **Automated:** `test_inactive_events_are_not_listed`

**TC-83-04 · Soonest date first, undated last**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** Q4
- **Expected result:** S3, S2, S4, S1, S5.
- **Automated:** `test_events_are_listed_soonest_first_with_undated_last`

**TC-83-05 · Missing name and date are sent as not recorded**
- **Traces to:** AC1 · **Type:** Boundary
- **Expected result:** S5 is listed with `title: null` and `start_time: null`.
- **Automated:** `test_blank_name_and_missing_date_are_null`

**TC-83-06 · Filtering by coordinator**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As lena, load the list with `coordinator_id` alice, then ben, then an empty value.
- **Expected result:** alice → S3, S1, S5; ben → S2, S4; an empty value → S1–S5 as unfiltered.
- **Automated:** `test_filter_by_coordinator`

**TC-83-07 · The filter offers the coordinators of the Lead's events**
- **Traces to:** AC1 · **Type:** Happy path
- **Expected result:** `coordinators` is alice then ben, with or without a filter. chloe, who has only an inactive event of lena's, is not offered.
- **Automated:** `test_coordinator_options_are_the_coordinators_of_the_listed_events`

**TC-83-08 · A coordinator with none of the Lead's active events**
- **Traces to:** AC1 · **Type:** Empty state
- **Steps:** As lena, filter by chloe.
- **Expected result:** HTTP 200, `events` is empty and `message` is a non-empty sentence.
- **Automated:** `test_filter_by_a_coordinator_with_none_of_the_leads_events_is_empty`

**TC-83-09 · A filter that is not a user ID is refused**
- **Traces to:** AC1 · **Type:** Negative (input)
- **Steps:** Filter by `abc`, `1.5`, `-3` and `true`.
- **Expected result:** HTTP 400 with `field: "coordinator_id"` and no events.
- **Automated:** `test_invalid_coordinator_filter_is_refused`

**TC-83-10 · A Lead who has assigned nothing**
- **Traces to:** AC1 · **Type:** Empty state
- **Steps:** As lucy, load the list.
- **Expected result:** `events` and `coordinators` are empty and `message` is a non-empty sentence.
- **Automated:** `test_lead_with_no_assigned_events_gets_an_empty_state_message`

## AC2 — Other Leads' events

**TC-83-11 · Events assigned by anyone else are not listed**
- **Traces to:** AC2 · **Type:** Negative (scope) · **Depends on:** Q1
- **Expected result:** lena's list has none of S10 (liam), S11 (admin) or S12 (no assigner). liam's list is exactly S10.
- **Automated:** `test_events_assigned_by_other_leads_or_admins_are_not_listed`

**TC-83-12 · Filtering never reveals another Lead's events**
- **Traces to:** AC2 · **Type:** Negative (scope)
- **Steps:** As lena, filter by ben (who also coordinates liam's S10); as liam, filter by alice.
- **Expected result:** lena sees S2 and S4 only; liam gets an empty list.
- **Automated:** `test_filtering_never_reveals_another_leads_events`

**TC-83-13 · Reassignment by someone else moves the event out of the list**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** Q1
- **Steps:** An administrator reassigns S1 to chloe through `PUT /api/events/<id>/coordinator`; lena then loads her list with a token issued earlier.
- **Expected result:** S1 is no longer in lena's list; S2–S5 still are.
- **Automated:** `test_reassignment_by_someone_else_removes_the_event_from_the_leads_list`

## AC3 — Only the Lead

**TC-83-14 · Every other role is denied and sees no event data**
- **Traces to:** AC3 · **Type:** Negative (authorisation) · **Depends on:** Q3
- **Steps:** Load the list, with and without an invalid filter, as admin, alice, dana, farah, gus and hana.
- **Expected result:** HTTP 403 every time (never 400). The body has no `events` or `coordinators` and no event title.
- **Automated:** `test_only_leads_can_open_the_view`

**TC-83-15 · A valid session is required**
- **Traces to:** AC3 · **Type:** Negative (authorisation)
- **Steps:** Load the list with no token, an expired token and a deleted Lead's token.
- **Expected result:** HTTP 401 with no event data.
- **Automated:** `test_a_valid_session_is_required`

**TC-83-16 · A Lead whose role changes is denied at once**
- **Traces to:** AC3 · **Type:** Negative (authorisation)
- **Steps:** Change lena's role to coordinator, then load the list with her earlier token.
- **Expected result:** HTTP 403 with no event data.
- **Automated:** `test_lead_whose_role_changes_is_denied_at_once`

## AC4 — Loading fails

**TC-83-17 · The Lead is told, no partial list is sent, and retry works**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** Every database query raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true`, a message saying the events could not be loaded and to try again, and no `events`, `coordinators` or event titles. Loading again with the database working returns S1–S5.
- **Automated:** `test_load_failure_is_reported_without_a_partial_list_and_retry_works`

## Frontend

**TC-83-18 · The list shows name, coordinator, date and status**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** The page "Events I assigned" lists each event, in the order received, with its name, "Coordinator: <email>", "Proposed date: <date and time as recorded>" and "Status: <label>". A missing name or date shows "Not recorded".
- **Automated:** `LeadAssignedEventsPage.test.jsx`

**TC-83-19 · Filtering by coordinator**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** A "Coordinator" box offers "All coordinators" and each coordinator's email. Choosing one reloads the list with `coordinator_id`; choosing "All coordinators" reloads it without. A filtered empty list shows the server's message.
- **Automated:** `LeadAssignedEventsPage.test.jsx`

**TC-83-20 · Empty state**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** With no events, the server's message is shown and no list.
- **Automated:** `LeadAssignedEventsPage.test.jsx`

**TC-83-21 · Anyone else is denied and sees no event data**
- **Traces to:** AC3 · **Type:** Frontend
- **Expected result:** A 403 shows its message, with no list, no coordinator box and no Retry button.
- **Automated:** `LeadAssignedEventsPage.test.jsx`

**TC-83-22 · Load failure, no partial list, retry**
- **Traces to:** AC4 · **Type:** Frontend
- **Expected result:** A failure shows the server's error (or a fallback for a network failure) with a Retry button and no list. If a reload fails after a list was shown (e.g. on changing the filter), that list is removed. Retrying repeats the same filter and shows the list.
- **Automated:** `LeadAssignedEventsPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 18, 19, 20 |
| AC2 | 11, 12, 13 |
| AC3 | 14, 15, 16, 21 |
| AC4 | 17, 22 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 04, 06, 07 |
| Negative | 09, 11, 12, 14, 15, 16, 17 |
| Boundary | 03, 05, 13 |
| Empty state | 08, 10 |
| Frontend | 18, 19, 20, 21, 22 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Does "events I have assigned" mean the Lead who made the *current* assignment, or should a Lead keep seeing an event after another Lead or an administrator reassigns it? And how should events assigned before the Lead role existed be handled? Assumed: the current assignment only; older events belong to no Lead. | A1, A2, TC-83-11, TC-83-13 |
| Q2 | Which statuses count as "active"? Assumed `submitted`, `under_review`, `approved` and `confirmed`. | A3, TC-83-03 |
| Q3 | Should administrators also be able to open this view (for example, for every Lead)? Assumed not. | A4, TC-83-14 |
| Q4 | What order helps most to spot stuck events: soonest date, longest since assignment, or grouped by status? Assumed soonest date first. | A5, TC-83-04 |
| Q5 | Should the Lead be able to open an event from this list, and see what? Assumed not yet: there is no Lead view of an event. | A8 |
| Q6 | What makes an event "stuck" (for example, no status change for N days)? Nothing is flagged yet; the Lead judges from status and date. | — |
