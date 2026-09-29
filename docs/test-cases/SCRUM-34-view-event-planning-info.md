# SCRUM-34 — View Event Planning Information: Test Cases

**User story:** As an Event Coordinator, I want to view the planning information for events I am authorised to manage so that I have an accurate picture of arrangements as they develop.

**Created:** 27 Sep 2026 · **Status of all cases:** Not run (feature not yet built) · **Automated tests:** `backend/tests/test_event_planning_info.py` (30 tests; all fail until the endpoint exists)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can view information for events they are authorised to manage. |
| AC2 | All recorded planning fields for the event are displayed, including fields not editable by this coordinator. |
| AC3 | If the event's information cannot be loaded, the coordinator is informed and can retry. |
| AC4 | Coordinators without authorisation for a given event cannot view its information. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Authorised to manage:** the event's current coordinator (`Event.coordinator_id`, set by SCRUM-33), and only while their role is still `coordinator`. This is checked against the database on every request, so a reassignment or role change applies immediately, even to a login token issued earlier. *(Q1, Q2)*
- **A2 — Other roles:** admins, organisers (including the event's own organiser), venue staff, technical support staff and attendees cannot use this view. Their access to event information belongs to other stories. *(Q1)*
- **A3 — Planning fields (16):** title, purpose, description, status, start date and time, end date and time, venue (name and location), expected attendance, venue requirements, accessibility needs, equipment requirements, whether attendee registration is required, organiser, coordinator, date the coordinator was assigned, and date the request was created. The request details (purpose to registration) come from the organiser's request (SCRUM-29). The decision note and draft timestamps (SCRUM-29/32) are not planning information. Fields added by later stories must be added to this list when they are built. *(Q4)*
- **A9 — Yes/no answers:** "registration not required" (`false`) is a recorded answer and is shown as "No", never as *not recorded*. Only a missing answer (`null`) is *not recorded*.
- **A4 — Not recorded:** a field that was never recorded, or holds only blank text, is shown as *not recorded*. It is never shown as blank, zero or "none", matching View Venue Details (SCRUM-35).
- **A5 — Editability:** this view shows every field whether or not the coordinator may edit it. Marking which fields are editable belongs to the edit story. *(Q5)*
- **A6 — Status:** a coordinator can still view an event they manage after it is cancelled. *(Q3)*
- **A7 — Dates and times:** shown exactly as recorded, with no time-zone conversion or rounding. All times are Singapore time (SGT, UTC+8).
- **A8 — Unknown event:** an event ID that does not exist gives "Event not found." (HTTP 404), which is checked before authorisation, as for the existing coordinator endpoints. *(Q6)*

## Seed data (EP-SEED)

Reset the database to this data before **every** test case, so that one test cannot affect the next. Users, the Charity Gala, Product Launch and Tech Summit come from `backend/tests/seed_data.py`. The other events are created in the test file.

**Users**

| Key | Email | Role | Coordinates |
|-----|-------|------|-------------|
| alice | alice.coordinator@connectsphere.test | coordinator | E1, E2, E5, E6 |
| ben | ben.coordinator@connectsphere.test | coordinator | E3 |
| chloe | chloe.coordinator@connectsphere.test | coordinator | *(none)* |
| admin | admin@connectsphere.test | admin | |
| dana | dana.organiser@connectsphere.test | organiser | *(organises E1, E2, E4, E5)* |
| evan | evan.organiser@connectsphere.test | organiser | *(organises E3, E6)* |
| farah | farah.attendee@connectsphere.test | attendee | |
| gus | gus.venue@connectsphere.test | venue_staff | |
| hana | hana.tech@connectsphere.test | tech_staff | |

**Venue:** Aurora Ballroom, Level 3, Marina Tower, 10 Bayfront Ave.

**Events**

| Ref | Title | Status | Coordinator (assigned) | Venue | Description | Start – End | Created |
|-----|-------|--------|------------------------|-------|-------------|-------------|---------|
| E1 | Harbour Lights Festival | submitted | alice (10 Sep 2026 09:30) | Aurora Ballroom | "Waterfront lantern festival with live music and food stalls." | Sat 12 Dec 2026 17:00 – 22:00 | 5 Sep 2026 14:00 |
| E2 | Charity Gala | submitted | alice (1 Sep 2026 10:00) | *not recorded* | *not recorded* | Sat 5 Dec 2026 18:00 – 23:00 | *(on insert)* |
| E3 | Product Launch | submitted | ben (2 Sep 2026 15:30) | *not recorded* | *not recorded* | Fri 20 Nov 2026 14:00 – 16:00 | *(on insert)* |
| E4 | Tech Summit 2026 | submitted | *none* | *not recorded* | *not recorded* | Tue 10 Nov 2026 09:00 – 17:00 | *(on insert)* |
| E5 | Winter Networking Night | cancelled | alice (3 Sep 2026 16:00) | *not recorded* | *not recorded* | Thu 1 Oct 2026 09:00 – 11:00 | *(on insert)* |
| E6 | Staff Retreat | submitted | alice (12 Sep 2026 11:00) | *not recorded* | `"   "` (blanks only) | Thu 1 Oct 2026 09:00 – 11:00 | *(on insert)* |

**Request details (SCRUM-29 fields).** E1 has all of them recorded: purpose "Celebrate the harbour's reopening with the local community.", expected attendance 350, venue requirements "Waterfront access and space for 20 food stalls.", accessibility needs "Step-free routes and a quiet area.", equipment requirements "Stage lighting and a PA system.", registration required Yes. E6 has accessibility needs `""` (empty) and registration required No. The other events have none recorded.

---

## AC1 — The coordinator can view events they are authorised to manage

**TC-34-01 · Assigned coordinator views a fully recorded event**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** 1. Open the event list. 2. Open Harbour Lights Festival (E1). 3. View its planning information.
- **Test data:** Event = E1.
- **Expected result:** All sixteen planning fields are shown with the values in the EP-SEED table and request details: title, purpose, description, expected attendance 350, venue requirements, accessibility needs, equipment requirements, registration required Yes, status "submitted", 12 Dec 2026 17:00 – 22:00, Aurora Ballroom with its location, organiser dana, coordinator alice, assigned 10 Sep 2026 09:30, created 5 Sep 2026 14:00. Nothing is marked *not recorded*.
- **Automated:** `test_assigned_coordinator_sees_the_events_planning_information`

**TC-34-02 · Coordinator views each of several events they manage**
- **Traces to:** AC1 · **Type:** Happy path
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View the planning information for E1, E2, E5 and E6 in turn.
- **Test data:** Events = E1, E2, E5, E6.
- **Expected result:** Each one opens and shows its own title. No event shows another event's information.
- **Automated:** `test_coordinator_can_view_every_event_they_manage`, `test_each_coordinator_sees_their_own_event` (ben views E3)

**TC-34-03 · Cancelled event remains viewable**
- **Traces to:** AC1 · **Type:** Boundary (business rule) · **Depends on:** Q3
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View Winter Networking Night (E5).
- **Test data:** Event = E5 (status cancelled).
- **Expected result:** The information is shown, with status "cancelled".
- **Automated:** `test_cancelled_event_remains_viewable_by_its_coordinator`

**TC-34-04 · Unknown event**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** EP-SEED loaded; logged in as `alice`; no event with ID 999999 exists.
- **Steps:** Request the planning information for event 999999.
- **Test data:** Event ID = 999999.
- **Expected result:** "Event not found." (HTTP 404). No event information is shown.
- **Automated:** `test_unknown_event_returns_not_found`

**TC-34-05 · Session required**
- **Traces to:** AC1, AC4 · **Type:** Negative (authentication)
- **Preconditions:** EP-SEED loaded; not logged in. Repeat with an expired token, and with a token for a user who has since been deleted.
- **Steps:** Request E1's planning information.
- **Test data:** Event = E1.
- **Expected result:** The user is asked to log in (HTTP 401). No event information is returned.
- **Automated:** `test_viewing_requires_authentication`, `test_expired_token_is_rejected`, `test_token_for_a_deleted_user_is_rejected`

**TC-34-06 · Viewing changes nothing**
- **Traces to:** AC1 · **Type:** Negative (side effect)
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** 1. Note every stored field of E1. 2. View E1's planning information. 3. Compare the stored fields again.
- **Test data:** Event = E1.
- **Expected result:** Every stored field is unchanged.
- **Automated:** `test_viewing_does_not_change_the_event`

## AC2 — All recorded planning fields are displayed, including fields the coordinator cannot edit

**TC-34-07 · Every planning field is always present**
- **Traces to:** AC2 · **Type:** Happy path
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View E1, E2, E5 and E6.
- **Test data:** Events = E1, E2, E5, E6.
- **Expected result:** Each view has all sixteen planning fields, either with a value or marked *not recorded*. No field is missing from the page.
- **Automated:** `test_every_planning_field_is_always_present`

**TC-34-08 · Fields the coordinator cannot edit are still shown**
- **Traces to:** AC2 · **Type:** Happy path · **Depends on:** Q5
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View E1.
- **Test data:** Event = E1.
- **Expected result:** Title, status, organiser, coordinator, date assigned and date created are shown with their recorded values, even though the coordinator cannot edit them here.
- **Automated:** `test_fields_the_coordinator_cannot_edit_are_still_shown`

**TC-34-09 · Venue shown by name and location**
- **Traces to:** AC2 · **Type:** Happy path
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View E1.
- **Test data:** Event = E1.
- **Expected result:** The venue is shown as "Aurora Ballroom, Level 3, Marina Tower, 10 Bayfront Ave", not as an ID.
- **Automated:** `test_venue_is_shown_by_name_and_location_not_just_an_id`

**TC-34-10 · Dates and times shown exactly as recorded**
- **Traces to:** AC2 · **Type:** Boundary
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View E1.
- **Test data:** Event = E1 (17:00 – 22:00 on 12 Dec 2026).
- **Expected result:** Start is 12 Dec 2026 17:00 and end is 12 Dec 2026 22:00, with no shift to UTC (09:00 – 14:00) or any other time zone.
- **Automated:** `test_dates_and_times_are_shown_exactly_as_recorded`

**TC-34-11 · Unrecorded fields are marked "not recorded"**
- **Traces to:** AC2 · **Type:** Negative
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View Charity Gala (E2).
- **Test data:** Event = E2 (only title, status, dates, organiser and coordinator recorded).
- **Expected result:** Purpose, description, venue, expected attendance, venue requirements, accessibility needs, equipment requirements and registration required are all shown as *not recorded*, not as blank, "none" or "TBC". The fields that are recorded (title, dates, organiser and so on) are shown normally.
- **Automated:** `test_unrecorded_fields_are_null_and_listed_as_not_recorded`, `test_recorded_fields_on_a_partly_recorded_event_are_still_shown`

**TC-34-12 · Blank text is treated as not recorded**
- **Traces to:** AC2 · **Type:** Boundary
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View Staff Retreat (E6).
- **Test data:** Event = E6 (description is three spaces; accessibility needs is empty).
- **Expected result:** Both are shown as *not recorded*, not as empty boxes.
- **Automated:** `test_blank_text_is_treated_as_not_recorded`

**TC-34-27 · "Registration not required" is a recorded answer**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** A9
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View Staff Retreat (E6).
- **Test data:** Event = E6 (registration required = No).
- **Expected result:** Registration required is shown as "No" (`false`), not as *not recorded*.
- **Automated:** `test_registration_not_required_is_a_recorded_answer`

**TC-34-13 · Fully recorded event has nothing marked "not recorded"**
- **Traces to:** AC2 · **Type:** Happy path
- **Preconditions:** EP-SEED loaded; logged in as `alice`.
- **Steps:** View E1.
- **Test data:** Event = E1.
- **Expected result:** No field is marked *not recorded*.
- **Automated:** `test_not_recorded_is_empty_when_everything_is_recorded`

**TC-34-14 · Saved changes appear the next time the event is viewed**
- **Traces to:** AC2 (story goal: "as arrangements develop") · **Type:** Happy path
- **Preconditions:** EP-SEED loaded; `alice` has E1's planning information open.
- **Steps:** 1. Change E1's description to "Now with a drone light show.", remove its venue, and move its start to 18:00, then save. 2. As `alice`, view E1 again.
- **Test data:** Event = E1.
- **Expected result:** The new description and start time are shown. The venue is now *not recorded*. No earlier values are shown.
- **Automated:** `test_saved_changes_are_shown_the_next_time_the_event_is_viewed`

## AC3 — If the information cannot be loaded, the coordinator is informed and can retry

**TC-34-15 · Database unavailable**
- **Traces to:** AC3 · **Type:** Negative (failure)
- **Preconditions:** EP-SEED loaded; logged in as `alice`; the database is made to fail (in automated tests, every query raises an `OperationalError`, as in `test_venue_details.py`).
- **Steps:** View E1.
- **Test data:** Event = E1.
- **Expected result:** A message says the event's information could not be loaded, and a Retry option is offered (HTTP 503, `retryable: true`). No event information is shown, not even partly.
- **Automated:** `test_failure_informs_the_coordinator_and_offers_retry`, `test_failure_does_not_return_any_event_information`

**TC-34-16 · Load failure is not reported as "not found" or "not allowed"**
- **Traces to:** AC3, AC4 · **Type:** Negative (failure)
- **Preconditions:** As TC-34-15.
- **Steps:** View E1.
- **Test data:** Event = E1.
- **Expected result:** The coordinator is not told the event does not exist (404), that they are not allowed to view it (403), or that they must log in again (401).
- **Automated:** `test_failure_is_not_reported_as_not_found_or_not_allowed`

**TC-34-17 · Partial failure is treated as a full failure**
- **Traces to:** AC2, AC3 · **Type:** Negative (failure)
- **Preconditions:** As TC-34-15, but only reading the venue fails; the event itself loads.
- **Steps:** View E1.
- **Test data:** Event = E1 (venue = Aurora Ballroom).
- **Expected result:** The same error as TC-34-15. The page must **not** show the event with its venue marked *not recorded*, because that would tell the coordinator no venue has been arranged.
- **Automated:** `test_venue_load_failure_is_not_shown_as_venue_not_recorded`

**TC-34-18 · Retry succeeds after recovery**
- **Traces to:** AC3 · **Type:** Happy path (recovery)
- **Preconditions:** TC-34-15 has just produced the error; the database is then restored.
- **Steps:** Click Retry.
- **Test data:** Event = E1.
- **Expected result:** The information loads and matches TC-34-01.
- **Automated:** `test_retrying_succeeds_once_the_database_recovers`

**TC-34-19 · Error and Retry on the page**
- **Traces to:** AC3 · **Type:** Negative (failure, UI) · **Manual** (no automated frontend test yet)
- **Preconditions:** `alice` has E1 open in the web app; the backend is then stopped.
- **Steps:** 1. Reload E1's planning page. 2. Restart the backend. 3. Click Retry.
- **Test data:** Event = E1.
- **Expected result:** (1) A readable error message and a Retry button are shown. The previously loaded values are not left on screen as if they were current. (3) The information loads without the coordinator having to navigate away or log in again.

## AC4 — Coordinators without authorisation cannot view the event

**TC-34-20 · Coordinator of a different event**
- **Traces to:** AC4 · **Type:** Negative (authorisation)
- **Preconditions:** EP-SEED loaded; logged in as `ben`.
- **Steps:** Request E1's planning information directly (e.g. by typing its URL).
- **Test data:** Event = E1 (coordinated by alice).
- **Expected result:** "You are not allowed to view this event's planning information." (HTTP 403). The response contains no title, description, venue or email addresses from E1.
- **Automated:** `test_coordinator_of_another_event_is_refused`

**TC-34-21 · Coordinator with no events**
- **Traces to:** AC4 · **Type:** Negative (authorisation)
- **Preconditions:** EP-SEED loaded; logged in as `chloe`.
- **Steps:** Request E1's planning information.
- **Test data:** Event = E1.
- **Expected result:** As TC-34-20.
- **Automated:** `test_coordinator_with_no_events_is_refused`

**TC-34-22 · Event with no coordinator**
- **Traces to:** AC4 · **Type:** Boundary (authorisation)
- **Preconditions:** EP-SEED loaded.
- **Steps:** As each of `alice`, `ben` and `chloe`, request Tech Summit 2026 (E4).
- **Test data:** Event = E4 (no coordinator).
- **Expected result:** Each is refused as in TC-34-20. Being a coordinator does not grant access to unassigned events.
- **Automated:** `test_no_coordinator_can_view_an_unassigned_event`

**TC-34-23 · Reassignment moves access immediately**
- **Traces to:** AC4 · **Type:** Boundary (authorisation) · **Depends on:** Q2
- **Preconditions:** EP-SEED loaded; `alice` and `ben` are both logged in; `alice` can view E1.
- **Steps:** 1. Reassign E1 from alice to ben. 2. Without logging in again, `alice` refreshes E1. 3. `ben` opens E1.
- **Test data:** Event = E1.
- **Expected result:** (2) `alice` is refused as in TC-34-20. (3) `ben` sees E1's information.
- **Automated:** `test_reassignment_moves_access_to_the_new_coordinator`

**TC-34-24 · Coordinator whose role changes loses access**
- **Traces to:** AC4 · **Type:** Boundary (authorisation)
- **Preconditions:** EP-SEED loaded; `alice` is logged in and can view E1.
- **Steps:** 1. Change alice's role to organiser. 2. Without logging in again, `alice` refreshes E1.
- **Test data:** Event = E1.
- **Expected result:** `alice` is refused as in TC-34-20.
- **Automated:** `test_coordinator_who_changes_role_loses_access_with_an_existing_token`

**TC-34-25 · Users who are not coordinators are refused**
- **Traces to:** AC4 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Preconditions:** EP-SEED loaded.
- **Steps:** For each of `admin`, `dana` (E1's own organiser), `evan`, `farah`, `gus` and `hana`: log in and request E1's planning information.
- **Test data:** Event = E1.
- **Expected result:** Each is refused as in TC-34-20.
- **Automated:** `test_users_who_are_not_coordinators_are_refused`

**TC-34-26 · Refused request changes nothing**
- **Traces to:** AC4 · **Type:** Negative (side effect)
- **Preconditions:** EP-SEED loaded; logged in as `ben`.
- **Steps:** 1. Note every stored field of E1. 2. Request E1's planning information. 3. Compare the stored fields again.
- **Test data:** Event = E1.
- **Expected result:** The request is refused and every stored field is unchanged.
- **Automated:** `test_refusal_does_not_change_the_event`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06 |
| AC2 | 01, 07, 08, 09, 10, 11, 12, 13, 14, 17, 27 |
| AC3 | 15, 16, 17, 18, 19 |
| AC4 | 05, 16, 20, 21, 22, 23, 24, 25, 26 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 07, 08, 09, 13, 14, 18 |
| Negative | 04, 05, 06, 11, 15, 16, 17, 19, 20, 21, 25, 26 |
| Boundary | 03, 10, 12, 22, 23, 24, 27 |
| Cross-cutting (authorisation) | 05, 20, 21, 22, 23, 24, 25, 26 |
| Manual only | 19 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Besides the assigned coordinator, who else should see this planning view? For example admins, the event's own organiser, or venue and technical staff working on the event? | A1, A2, TC-34-25 |
| Q2 | Does "authorised to manage" mean only the current main coordinator, or also supporting coordinators or a supervisor? Should a previous coordinator keep read-only access after reassignment? | A1, TC-34-20–23 |
| Q3 | Should coordinators still see events that are cancelled, rejected or completed? | A6, TC-34-03 |
| Q4 | Which fields make up "planning information"? Should related arrangements (venue booking status, equipment requests, registration numbers) appear on this view too? | A3, TC-34-01, 07 |
| Q5 | Should the view mark which fields the coordinator can edit, and which need a change request? | A5, TC-34-08 |
| Q6 | Should an event the coordinator is not authorised for look the same as one that does not exist (both 404), so that event IDs cannot be probed? | A8, TC-34-04, 20 |
