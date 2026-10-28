# SCRUM-46 — Submit Change Request for a Submitted Event: Test Cases

**User story:** As an Event Organiser, I want to request a change to an event I have submitted so that ConnectSphere can assess my updated needs before existing arrangements are altered.

**Created:** 26 Oct 2026 · **Status of all cases:** automated cases pass (27 Oct 2026, local PostgreSQL as in CI + Vitest; and the schema check + API tests on Supabase); end-to-end check passed in the browser, see [the DoD evidence](../evidence/SCRUM-46-dod-evidence.md) · **Automated tests:** `backend/tests/test_change_requests.py` (through the API), `backend/tests/test_change_requests_unit.py` (the rules, no database), `frontend/src/pages/ChangeRequestPage.test.jsx` (+ the link in `MyEventRequestsPage.test.jsx`) · **Endpoints:** `GET` and `POST /api/events/<id>/change-requests` · **Related:** SCRUM-52 (restricted fields; its `requires_review.next_step` points here), SCRUM-29 (the organiser's request fields and their rules), SCRUM-42/44 (equipment; an *accepted* change goes through SCRUM-44's release rule, not built here)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | I can request a change only for my own events whose status is Approved. |
| AC2 | I can propose new values for the permitted fields: date, time, expected attendance, venue requirements and equipment requirements. |
| AC3 | Each request records the event, the affected fields and the proposed values. |
| AC4 | If a change is disallowed or invalid (for example, negative attendance or an end time before the start time), submission is blocked and the reason is shown. |
| AC5 | If the event has no assigned coordinator, submission is blocked and I'm told why. |
| AC6 | On success, the request is saved with status "Pending Review" and a confirmation is shown. |
| AC7 | The approved event information is not overwritten by a pending request. |
| AC8 | If saving fails, the event and request state are unchanged and an error message is shown. |
| AC9 | The event's coordinator is notified of the pending change request with the proposed changes. |

## Working assumptions (to confirm)

- **A1 — Who and which events:** the event's organiser (`organiser` role, `event.organiser_id`), for an event whose status is `approved`. Everyone else gets HTTP 403 without the event's details. Other statuses are refused with 409 naming the status. The story's title says "Submitted Event" but AC1 says Approved; AC1 is built. *(Q1)*
- **A2 — The permitted fields:** "date" and "time" are the event's start and end (`start_time`, `end_time`, Singapore time, `YYYY-MM-DDTHH:MM`); expected attendance is `expected_attendance`; venue requirements is `venue_requirements`; equipment requirements is the organiser's note `equipment_requirements` (the text they wrote in their request, SCRUM-29), **not** SCRUM-42's structured list, which the coordinator records. Any other field, such as the venue, the title or whether registration is needed, is *disallowed*: 422 saying it can't be changed through a change request. *(Q2, Q3)*
- **A3 — What a request contains:** only the fields whose proposed value differs from the event's current value; a value equal to the current one is ignored, as in SCRUM-52. A request with no actual change is refused (422). The body is flat, `{"start_time": …, "expected_attendance": …}`, the same shape as SCRUM-52's `requires_review.requested`.
- **A4 — Valid values:** the same rules as an organiser's request (SCRUM-29): times are valid `YYYY-MM-DDTHH:MM` values and the end must be after the start, checked on the start and end the event would have if the change were accepted (a proposed end is compared with the current start when only the end changes); attendance is a whole number of at least 1; venue requirements can't be blank (they are required for a request); equipment requirements may be blank, meaning none. Text is at most 5,000 characters. Past dates are not refused, as in SCRUM-29. Every problem is named at once (`fields`). *(Q4)*
- **A5 — No coordinator:** an event with no coordinator can't take a request (409 `no_coordinator`), since nobody would review it. As everywhere else in the app (`is_current_coordinator`), the event's coordinator is the assigned user while they still have the `coordinator` role. If their role has changed, the event counts as having no coordinator: the form doesn't name them and they aren't notified. *(AC5)*
- **A6 — One at a time:** an event can have at most one change request pending review; another is refused with 409 `pending` until the first is decided. A database index enforces it, and the event row is locked while it is checked. If the index refuses a save anyway (a request saved by other code that didn't lock the event), the reply is the same 409 `pending`; any other refused save is a failed save (503). **Until a later story decides requests (A10), each event can take only one change request in total.** *(Q5, Q6)*
- **A7 — What is recorded:** a new `event_change_requests` row (`db/event_change_requests.sql`): the event, who asked and when, status `pending_review` (shown as "Pending Review"), and `changes` as `{field: {"from": current value, "to": proposed value}}`, so the reviewer sees both. The event row is not changed. *(AC3, AC7)*
- **A8 — Notification:** the event's coordinator gets an in-app notification (`change_requested`) naming each field with its current and proposed value, saved in the same commit as the request, then an email. If the email can't be queued the request still stands and the reply says `email_queued: false`.
- **A9 — Order of checks:** 401 (no valid user) → 404 (no such event) → 403 (not the event's organiser) → 400 (body isn't a JSON object) → 409 (not approved → no coordinator → a request already pending) → 422 (disallowed or invalid fields, or no change) → 503 (not saved, `retryable: true`). The event's state is checked before its fields, as for drafts (SCRUM-29) and reservations (SCRUM-44).
- **A10 — Deciding a request:** approving or rejecting a change request, and applying it, are not part of this story. *(Q6)*

## Seed data (CR-SEED)

Users: `USERS` from `backend/tests/seed_data.py` (dana and evan are organisers; alice and ben coordinators; hana Technical Support).

| Key | Event | Status | Organiser | Coordinator | Start – end | Attendance | Venue requirements | Equipment requirements |
|-----|-------|--------|-----------|-------------|-------------|------------|--------------------|------------------------|
| C1 | Charity Gala | approved | dana | alice | 2026-12-05 18:00 – 23:00 | 200 | Ballroom for 200 | 2 wireless microphones |
| C2 | Book Fair | submitted | dana | alice | 2026-12-10 09:00 – 17:00 | 100 | Hall | (none) |
| C3 | Spring Fair | approved | dana | (none) | 2026-12-12 10:00 – 16:00 | 80 | Lawn | (none) |
| C4 | Product Launch | approved | evan | ben | 2026-12-20 14:00 – 18:00 | 50 | Auditorium | Projector |
| C5 | Winter Concert | cancelled | dana | alice | 2026-12-15 19:00 – 22:00 | 300 | Concert hall | (none) |

---

## AC1 — Only my own approved events

**TC-46-01 · The organiser opens the change request form for their approved event**
- **Traces to:** AC1, AC2 · **Type:** Positive · **Depends on:** A1, A2
- **Steps:** As dana, `GET /api/events/<C1>/change-requests`.
- **Expected result:** HTTP 200 with C1's title, status, coordinator (alice) and current values of the five permitted fields; the permitted fields with their labels; `can_request: true`; no pending request.
- **Automated:** `test_tc_46_01_the_organiser_opens_the_form_for_their_approved_event`

**TC-46-02 · Events that aren't approved can't take a request**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** A1
- **Steps:** As dana, open C2 (submitted) and C5 (cancelled); then submit an attendance change for each.
- **Expected result:** The form says `can_request: false`, `blocked_reason: "not_approved"`, with a message naming the status. Submitting is refused with 409 naming the status. Nothing is saved; nobody is notified.
- **Automated:** `test_tc_46_02_events_that_are_not_approved_cannot_take_a_request`

**TC-46-03 · Who may request, and in what order**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** A1, A9
- **Steps:** Submit for C1 with no token and with a deleted user's token; for a missing event as dana; for C1 as evan (another organiser), alice (its coordinator), hana and admin; as dana with a body that isn't JSON. Also open the form as evan.
- **Expected result:** 401; 401 ("Your session is no longer valid"); 404; 403 each, without C1's title or values; 400. Nothing is saved.
- **Automated:** `test_tc_46_03_who_may_request_and_in_what_order`

## AC2 — Propose new values for the permitted fields

**TC-46-04 · Every permitted field can be changed in one request**
- **Traces to:** AC2, AC3 · **Type:** Positive · **Depends on:** A2
- **Steps:** As dana, propose for C1: start 2026-12-06 18:00, end 2026-12-06 23:30, attendance 250, venue requirements "Ballroom for 250", equipment requirements "4 wireless microphones".
- **Expected result:** HTTP 201; the request's changes list all five fields, in that order, each with its current and proposed value.
- **Automated:** `test_tc_46_04_every_permitted_field_can_be_changed_in_one_request`

**TC-46-05 · Only the fields that change are recorded**
- **Traces to:** AC2, AC3 · **Type:** Positive · **Depends on:** A3
- **Steps:** Propose for C1 its current start, end and venue requirements, and attendance 250.
- **Expected result:** HTTP 201; only expected attendance is recorded (200 → 250).
- **Automated:** `test_tc_46_05_only_the_fields_that_change_are_recorded`

**TC-46-06 · Fields that aren't permitted are refused**
- **Traces to:** AC2, AC4 · **Type:** Negative · **Depends on:** A2
- **Steps:** Propose for C1, each with attendance 250: a new title; a venue; registration not needed; a status; an unknown field.
- **Expected result:** HTTP 422 each time, `fields.<name>` saying it can't be changed through a change request. Nothing is saved; nobody is notified.
- **Automated:** `test_tc_46_06_fields_that_are_not_permitted_are_refused`

## AC3 — The request records the event, the affected fields and the proposed values

**TC-46-07 · The request is recorded with the event, fields, current and proposed values, who and when**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A7
- **Steps:** Propose for C1 start 2026-12-05 17:00 and attendance 250.
- **Expected result:** One `event_change_requests` row for C1, requested by dana with a time, status `pending_review`, changes `{"start_time": {"from": "2026-12-05T18:00:00", "to": "2026-12-05T17:00:00"}, "expected_attendance": {"from": 200, "to": 250}}`. The reply's request matches it.
- **Automated:** `test_tc_46_07_the_request_records_the_event_fields_and_values`

## AC4 — Disallowed or invalid changes are blocked, with the reason

**TC-46-08 · Invalid values are refused with the reason**
- **Traces to:** AC4 · **Type:** Negative (validation) · **Depends on:** A4
- **Steps:** Propose for C1, one at a time: attendance -5, 0, 1.5, "250" and `true`; end before start (both proposed); end equal to start; only an end of 2026-12-05 17:00 (before C1's current start); a start of "next Friday" and of "2026-02-30T10:00"; blank venue requirements; venue requirements over 5,000 characters; equipment requirements that aren't text.
- **Expected result:** HTTP 422 each time, with `fields` naming the field and a plain reason ("whole number of at least 1", "The end must be after the start.", "valid date and time", "can't be blank", "5000 characters"). Nothing is saved; nobody is notified.
- **Automated:** `test_tc_46_08_invalid_values_are_refused_with_the_reason`

**TC-46-09 · Every problem is named at once**
- **Traces to:** AC4 · **Type:** Negative (validation) · **Depends on:** A4
- **Steps:** Propose attendance -5, blank venue requirements and a title.
- **Expected result:** HTTP 422 naming all three fields.
- **Automated:** `test_tc_46_09_every_problem_is_named_at_once`

**TC-46-10 · A request must change something**
- **Traces to:** AC4 · **Type:** Negative · **Depends on:** A3
- **Steps:** Send `{}`; then C1's current values only.
- **Expected result:** HTTP 422 saying there are no changes to request. Nothing is saved.
- **Automated:** `test_tc_46_10_a_request_must_change_something`

**TC-46-11 · Clearing the equipment requirements is a change; text is tidied**
- **Traces to:** AC2, AC4 · **Type:** Boundary · **Depends on:** A4
- **Steps:** Propose equipment requirements "" for C1; separately, venue requirements "  Ballroom for 250  ".
- **Expected result:** HTTP 201: equipment "2 wireless microphones" → null; venue requirements recorded as "Ballroom for 250".
- **Automated:** `test_tc_46_11_clearing_equipment_is_a_change_and_text_is_tidied`

## AC5 — No coordinator

**TC-46-12 · An event without a coordinator can't take a request, and says why**
- **Traces to:** AC5 · **Type:** Negative · **Depends on:** A5
- **Steps:** As dana, open C3's form, then submit an attendance change.
- **Expected result:** The form says `can_request: false`, `blocked_reason: "no_coordinator"`, with a message that the event is waiting for a coordinator (SCRUM-70 AC5). Submitting is refused with 409, `reason: "no_coordinator"`, and the same message. Nothing is saved.
- **Automated:** `test_tc_46_12_an_event_without_a_coordinator_cannot_take_a_request`

**TC-46-28 · A coordinator whose role has changed doesn't count**
- **Traces to:** AC5, AC9 · **Type:** Negative · **Depends on:** A5
- **Steps:** Change alice's role to attendee. As dana, open C1's form, then submit an attendance change.
- **Expected result:** The form names no coordinator and says `blocked_reason: "no_coordinator"`. Submitting is refused with 409, `reason: "no_coordinator"`. Nothing is saved; alice gets no notification or email.
- **Automated:** `test_tc_46_28_a_coordinator_whose_role_changed_does_not_count`

## AC6 — Saved as Pending Review, with a confirmation

**TC-46-13 · A successful request is Pending Review and confirmed**
- **Traces to:** AC6 · **Type:** Positive · **Depends on:** A7
- **Steps:** Propose attendance 250 for C1.
- **Expected result:** HTTP 201, `request.status: "pending_review"`, `request.status_label: "Pending Review"`, and a confirmation naming Charity Gala and the field, saying it is pending review and the coordinator has been notified.
- **Automated:** `test_tc_46_13_a_successful_request_is_pending_review_and_confirmed`

**TC-46-14 · Only one request can be pending at a time**
- **Traces to:** AC6 · **Type:** Negative · **Depends on:** A6
- **Steps:** Propose attendance 250 for C1; then propose attendance 300; then open the form.
- **Expected result:** The second is refused with 409, `reason: "pending"`. The form shows the pending request and `can_request: false`. One request exists.
- **Automated:** `test_tc_46_14_only_one_request_can_be_pending_at_a_time`

**TC-46-15 · The event is locked while the pending check is made**
- **Traces to:** AC6 · **Type:** Business rule (concurrency) · **Depends on:** A6
- **Steps:** Propose attendance 250 for C1 and record the SQL sent.
- **Expected result:** The event is read `FOR UPDATE` before the pending requests are looked for.
- **Automated:** `test_tc_46_15_the_event_is_locked_before_the_pending_check`

**TC-46-29 · A request saved first elsewhere is reported as pending**
- **Traces to:** AC6 · **Type:** Business rule (concurrency) · **Depends on:** A6
- **Steps:** Propose attendance 250 for C1. Then, with the pending check made to find nothing (as if the first request were saved after it looked), propose attendance 300.
- **Expected result:** The database index refuses the second; HTTP 409, `reason: "pending"`, not 503. Only the first request, its one notification and its one email exist.
- **Automated:** `test_tc_46_29_a_request_saved_first_elsewhere_is_reported_as_pending`

## AC7 — The approved event is not overwritten

**TC-46-16 · The event keeps its approved values**
- **Traces to:** AC7 · **Type:** Positive · **Depends on:** A7
- **Steps:** Propose all five changes for C1 (as TC-46-04); reload C1, and open its coordinator's planning view.
- **Expected result:** C1's start, end, attendance, venue and equipment requirements and status are as before.
- **Automated:** `test_tc_46_16_the_event_keeps_its_approved_values`

## AC8 — A failed save changes nothing

**TC-46-17 · A failed save leaves the event and requests unchanged**
- **Traces to:** AC8 · **Type:** Negative (failure)
- **Steps:** Make saving the request fail, and then saving the notification, and each time propose attendance 250 for C1.
- **Expected result:** HTTP 503, `retryable: true`, "Your change request was not submitted, and the event is unchanged. Please try again.", no internal error text. No request, no notification, no email; C1 unchanged.
- **Automated:** `test_tc_46_17_a_failed_save_leaves_the_event_and_requests_unchanged`

**TC-46-30 · Any other refused save is a failure, not "pending"**
- **Traces to:** AC8 · **Type:** Negative (failure) · **Depends on:** A6
- **Steps:** Make the database refuse the request's row for a reason other than the one-pending index, and propose attendance 250 for C1.
- **Expected result:** HTTP 503, `retryable: true`, the not-submitted message. Nothing is saved; nobody is notified.
- **Automated:** `test_tc_46_30_any_other_refused_save_is_a_failure_not_pending`

**TC-46-18 · A failed load is an error, not an empty form**
- **Traces to:** AC8 · **Type:** Negative (failure)
- **Steps:** Make reading the change requests fail and open C1's form.
- **Expected result:** HTTP 503, `retryable: true`, no internal error text, no values.
- **Automated:** `test_tc_46_18_a_failed_load_is_an_error_not_an_empty_form`

## AC9 — The coordinator is notified

**TC-46-19 · The coordinator is told the proposed changes**
- **Traces to:** AC9 · **Type:** Positive · **Depends on:** A8
- **Steps:** Propose start 2026-12-05 17:00 and attendance 250 for C1.
- **Expected result:** alice has one `change_requested` notification for C1 naming Charity Gala, "Start" 2026-12-05 18:00 → 2026-12-05 17:00 and "Expected attendance" 200 → 250; one email is queued to alice with the same details; `notification: {"in_app": true, "email_queued": true}`. dana gets nothing.
- **Automated:** `test_tc_46_19_the_coordinator_is_told_the_proposed_changes`

**TC-46-20 · An email queue failure doesn't undo the request**
- **Traces to:** AC9 · **Type:** Negative (failure) · **Depends on:** A8
- **Steps:** Make queuing the email fail and propose attendance 250 for C1.
- **Expected result:** HTTP 201 with `email_queued: false`; the request and the in-app notification are saved.
- **Automated:** `test_tc_46_20_an_email_queue_failure_does_not_undo_the_request`

## The rules without a database (`test_change_requests_unit.py`)

The proposal rules on plain objects: permitted fields only; unchanged values ignored; times parsed as `YYYY-MM-DDTHH:MM` and compared on the resulting start and end; attendance a whole number of at least 1; venue requirements not blank; text trimmed and at most 5,000 characters; every problem named at once; changes listed in field order with `from` and `to` (A2–A4, A7); and the notification text naming each change. **Automated:** `ProposalRuleTests`, `DescriptionRuleTests`.

## Frontend

`ChangeRequestPage` (`/events/:eventId/change-request`), linked as "Request a change" from the organiser's approved requests on "My event requests".

**TC-46-21 · The form shows the event's current values to change** — AC1, AC2 · `shows the event's current values in the form`

**TC-46-22 · Submitting sends only what changed and shows Pending Review** — AC2, AC6 · `sends only the changed fields and shows the confirmation`

**TC-46-23 · Refused fields are explained and the entries kept** — AC4 · `shows why each field was refused and keeps the entries`

**TC-46-24 · An event without a coordinator, or not approved, says why and offers no form** — AC1, AC5 · `explains why no change can be requested`

**TC-46-25 · A pending request is shown instead of the form** — AC6 · `shows the pending request instead of the form`

**TC-46-26 · A failed save explains itself and keeps the entries for a retry** — AC8 · `keeps the entries after a failed save so it can be tried again`

**TC-46-27 · Approved requests link to the form** — AC1 · `MyEventRequestsPage` "offers a change request only for approved requests"

Also: `explains a failed load and offers Retry`; `does not send a request that changes nothing`.

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 21, 24, 27 |
| AC2 | 01, 04, 05, 06, 11, 21, 22 |
| AC3 | 04, 05, 07 |
| AC4 | 06, 08, 09, 10, 11, 23 |
| AC5 | 12, 24, 28 |
| AC6 | 13, 14, 15, 22, 25, 29 |
| AC7 | 16 |
| AC8 | 17, 18, 26, 30 |
| AC9 | 19, 20, 28 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | The story's title says "Submitted Event", but AC1 says Approved. Should a change also be requestable while a request is still submitted or under review (as built: no)? | A1, TC-46-02 |
| Q2 | Is "equipment requirements" the organiser's own note (as built), or SCRUM-42's itemised list recorded by the coordinator? | A2 |
| Q3 | Should the venue, or whether attendee registration is needed, also be changeable by a change request? SCRUM-52 treats both as restricted fields that need one. | A2, TC-46-06 |
| Q4 | Should a proposed date in the past be refused? | A4 |
| Q5 | May an organiser have more than one change request pending for an event, or withdraw one? Until requests can be decided, an event can only ever take one. | A6, TC-46-14 |
| Q6 | Who decides a change request (the event's coordinator?), and is the event updated automatically when it is approved? | A10 |
| Q7 | SCRUM-52 tells the **coordinator** to submit a change request for restricted fields, but AC1 lets only the **organiser** submit one. Should the coordinator also be able to submit one for the events they coordinate? | A1; SCRUM-52 B7 |
