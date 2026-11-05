# SCRUM-35 — View Venue Details: Test Cases

**User story:** As an Event Coordinator, I want to view detailed venue information so that I can assess potential locations for an event.

**Created:** 5 Nov 2026. The story was built in Sprint 1, before this template, with its backend cases written as automated tests. This document records those cases in the template (TC-35-01 to 12) and adds the frontend cases (TC-35-13 to 17), which were missing: the venue list showed only names, with no empty state, no load failure, no retry and no way to open a venue's details. · **Automated tests:** `backend/tests/test_venue_details.py`, `frontend/src/pages/VenuesPage.test.jsx` · **Status of all cases:** automated cases pass (5 Nov 2026, local PostgreSQL built by `ci/build_test_database.py` + Vitest) · **Related:** SCRUM-63 (Venue Staff add and edit venues), CF08/SCRUM-101 (deleting a venue hides it from the catalogue), SCRUM-37 (venue search opens the same details, TC-37-28)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Authorised Event Coordinators and Venue Staff can browse the recorded venues and open a venue's details. |
| AC2 | Details include location, capacity, facilities, accessibility features, supported room layouts, operating information, and other recorded planning characteristics. |
| AC3 | Missing information is identified as not recorded rather than presented as a confirmed capability. |
| AC4 | If there are no recorded venues, an empty-state message is displayed. |
| AC5 | If venue details cannot be loaded, the user is informed and can retry. |

## Working assumptions

- **A1 — Who (AC1):** coordinators and Venue Staff, as main or additional role. Organisers, attendees and Technical Support Staff are refused (403).
- **A2 — Not recorded (AC3, CF08):** a planning field that was never recorded is NULL, or a string of only spaces, and comes back as `null` with its name in `not_recorded`, in a fixed order. A recorded absence (`[]`, `false`, `0`) is a fact and is returned as it is. The screen shows a recorded absence as None, No or 0 and an unrecorded field as Not recorded, so the two never look alike (CF08: "missing information is distinguishable from a recorded absence of a facility").
- **A3 — Unavailable venues (AC1):** a venue marked not available is still listed and can be opened; deleted venues are not listed (CF08).
- **A4 — Failures (AC5):** a failed load is 503 with `retryable: true`, never an empty list or "not found". The screen offers Try again for a failure that can be retried (no response, or `retryable`), and not for a refusal.

There are no open customer questions: CF08 and G4 clarification #15 settled not-recorded information and deletion.

## Seed data (VD-SEED)

Users from `tests/seed_data.py`, one per role: coordinator **alice**, Venue Staff **gus**, organiser **dana**, attendee **farah**, Technical Support **hana**.

| Key | Venue | What is recorded |
|-----|-------|------------------|
| fully_recorded | Aurora Ballroom | Every planning field: capacity 400, 850 m², five facilities, three accessibility features, four layouts, hours, contacts, 120 parking spaces, catering, setup and turnaround 0 |
| partially_recorded | Bayfront Pavilion | Only location and facilities ("Covered stage") |
| recorded_as_none | Civic Hall | No facilities, no accessibility features, no parking (0), no catering (false): recorded absences |
| unavailable | Dockside Studio | Fully described but not available |
| blank_values | Evergreen Loft | Description, location, hours and contact email typed as blanks |

---

## AC1 — Browse the venues and open one

**TC-35-01 · Coordinators and Venue Staff can browse; others can't**
- **Traces to:** AC1 · **Type:** Positive and negative (authorisation) · **Depends on:** A1
- **Steps:** GET `/api/venues/` as alice and as gus; then as dana, farah and hana.
- **Expected result:** alice and gus get 200 listing every venue; the others get 403 with an error.
- **Automated:** `test_authorised_roles_can_browse_venues`, `test_other_roles_cannot_browse_venues`

**TC-35-02 · The list holds every venue, by name, with what's needed to pick one**
- **Traces to:** AC1, AC3 · **Type:** Happy path · **Depends on:** A3
- **Steps:** As alice, GET `/api/venues/`.
- **Expected result:** every venue, Dockside Studio included with `is_available: false`, sorted by name, `message: null`. Aurora's summary is exactly `{id, name, location, capacity: 400, is_available: true}`. Bayfront's capacity and Evergreen's location are `null`, not guessed. Every listed venue opens with 200 and the same name.
- **Automated:** `test_lists_every_recorded_venue_including_unavailable_ones`, `test_venues_are_sorted_by_name`, `test_summary_contains_the_fields_needed_to_pick_a_venue`, `test_summary_reports_availability`, `test_summary_leaves_unrecorded_values_empty_rather_than_guessing`, `test_every_listed_venue_can_be_opened`

**TC-35-03 · Opening details needs an authorised role, a valid session and an existing venue**
- **Traces to:** AC1 · **Type:** Negative (authorisation, authentication)
- **Steps:** GET `/api/venues/<Aurora>` as alice and gus; as dana, farah and hana; with no token; with the token of a deleted user (list and details); for a venue ID that doesn't exist.
- **Expected result:** 200; 403; 401; 401; 404.
- **Automated:** `test_authorised_roles_can_open_venue_details`, `test_other_roles_cannot_open_venue_details`, `test_opening_details_requires_authentication`, `test_browsing_requires_authentication`, `test_token_for_a_deleted_user_is_rejected`, `test_unknown_venue_returns_not_found`

**TC-35-04 · An unavailable venue can still be opened**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** A3
- **Steps:** Open Dockside Studio.
- **Expected result:** 200 with `is_available: false` and its recorded layouts (classroom, boardroom).
- **Automated:** `test_unavailable_venue_details_can_still_be_opened`

## AC2 — Every planning characteristic

**TC-35-05 · A fully recorded venue shows every characteristic**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** Open Aurora Ballroom.
- **Expected result:** exactly: description, location, capacity 400, area 850, the five facilities, three accessibility features and four layouts in their recorded order, "Mon-Sun 08:00-23:00", contact email and phone, 120 parking spaces, catering true, setup and turnaround 0, and `not_recorded: []`.
- **Automated:** `test_fully_recorded_venue_shows_every_planning_characteristic`, `test_list_fields_keep_their_recorded_order`, `test_not_recorded_is_empty_when_everything_is_recorded`

**TC-35-06 · Every venue's details have every field**
- **Traces to:** AC2, AC3 · **Type:** Business rule
- **Steps:** Open each seed venue.
- **Expected result:** each reply has `id`, `name`, `is_available`, `not_recorded` and all 14 planning fields, whether recorded or not.
- **Automated:** `test_details_always_include_every_planning_field`

## AC3 — Not recorded is never shown as a capability

**TC-35-07 · Unrecorded fields are null and listed; recorded ones still show**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** A2
- **Steps:** Open Bayfront Pavilion.
- **Expected result:** every field except location and facilities is `null` and listed in `not_recorded`, in the fixed order; location and facilities show their values. Unrecorded values are never `false`, `0` or `[]`.
- **Automated:** `test_unrecorded_fields_are_null_and_listed_as_not_recorded`, `test_recorded_fields_on_a_partial_venue_are_still_shown`, `test_unrecorded_values_are_not_presented_as_false_zero_or_empty`

**TC-35-08 · Recorded absences are facts, not missing data**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** A2
- **Steps:** Open Civic Hall.
- **Expected result:** facilities `[]`, accessibility features `[]`, catering `false`, parking `0`, and `not_recorded: []`.
- **Automated:** `test_recorded_absences_are_confirmed_not_missing`

**TC-35-09 · Blank text counts as not recorded**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** A2
- **Steps:** Open Evergreen Loft.
- **Expected result:** description, location, operating hours and contact email are `null` and listed; `not_recorded` is exactly description, location, area, accessibility features, operating hours, contact email, contact phone, parking spaces, catering, setup and turnaround, in that order.
- **Automated:** `test_blank_text_is_treated_as_not_recorded`, `test_not_recorded_lists_fields_in_a_stable_order`

**TC-35-10 · A venue with only a name reports every field as not recorded**
- **Traces to:** AC3 · **Type:** Boundary
- **Steps:** Add a venue with only the name "Placeholder Venue" and open it.
- **Expected result:** `not_recorded` lists all 14 planning fields; the name is shown.
- **Automated:** `test_every_field_can_be_reported_as_not_recorded`, with the model checks `test_planning_fields_default_to_not_recorded`, `test_planning_columns_are_nullable`, `test_list_fields_round_trip_through_the_database`, `test_unset_list_fields_are_stored_as_sql_null`, `test_recorded_absences_are_stored_distinctly_from_not_recorded`

## AC4 — Empty catalogue

**TC-35-11 · No venues: an empty-state message**
- **Traces to:** AC4 · **Type:** Empty state
- **Preconditions:** every venue hidden for the test (rolled back after).
- **Steps:** GET `/api/venues/` as alice and as gus.
- **Expected result:** 200 with `venues: []` and a non-blank `message`, the same for both roles.
- **Automated:** `test_shows_an_empty_state_message_when_no_venues_are_recorded`, `test_empty_state_is_the_same_for_every_authorised_role`

## AC5 — A failed load is reported and can be retried

**TC-35-12 · A database failure is an error, not an empty list or "not found", and a retry works**
- **Traces to:** AC5 · **Type:** Negative (failure) · **Depends on:** A4
- **Steps:** Make every query fail and GET the list, then Aurora's details; let the database recover and repeat both.
- **Expected result:** during the failure 503 with `retryable: true`, no `venues` key and never 404; afterwards 200 with every venue, and Aurora's details.
- **Automated:** `test_list_failure_informs_the_user_and_offers_retry`, `test_list_failure_is_not_shown_as_an_empty_venue_list`, `test_detail_failure_informs_the_user_and_offers_retry`, `test_detail_failure_is_not_reported_as_venue_not_found`, `test_retrying_the_list_succeeds_once_the_database_recovers`, `test_retrying_details_succeeds_once_the_database_recovers`

## Frontend (the Venues page)

**TC-35-13 · Each venue is listed with its location and capacity**
- **Traces to:** AC1, AC3 · **Type:** Frontend
- **Steps:** Open Venues with Aurora and Bayfront listed.
- **Expected result:** "Location: Level 3, Marina Tower, 10 Bayfront Ave" and "Capacity: 400" for Aurora; "Capacity: Not recorded" for Bayfront; no empty-state text.
- **Automated:** `VenuesPage.test.jsx` "lists each venue with its location and capacity, saying when one isn't recorded"

**TC-35-14 · The empty-state message is shown**
- **Traces to:** AC4 · **Type:** Frontend, empty state
- **Steps:** Open Venues when the server returns no venues and its message.
- **Expected result:** the server's message, and no list items.
- **Automated:** "shows the server's empty-state message when no venues are recorded"

**TC-35-15 · A failed list says so and can be retried; a refusal can't**
- **Traces to:** AC5 · **Type:** Frontend, failure · **Depends on:** A4
- **Steps:** Open Venues when the list fails with 503 (retryable), then select Try again once it recovers. Separately, with no response at all, and with a 403.
- **Expected result:** the server's message as an alert, never the empty-state text; Try again loads the venues and clears the alert. With no response: "Venues could not be loaded. Check your connection and try again." and Try again. With a 403: the server's refusal and no Try again.
- **Automated:** "says the list could not be loaded, never that there are no venues, and retries"; "explains a network failure with its own words, and a refusal without offering a retry"

**TC-35-16 · Details show every characteristic, and tell recorded absences from unrecorded fields**
- **Traces to:** AC1, AC2, AC3 · **Type:** Frontend, boundary · **Depends on:** A2
- **Steps:** Select View details for Civic Hall; separately for Bayfront Pavilion.
- **Expected result:** Civic Hall: description, area 150, Facilities None, Accessibility None, Layouts theatre, hours, contact "hire@civichall.test, +65 6000 1111", Parking spaces 0, Catering No, setup and turnaround "0 min", and no "Not recorded". Bayfront: Facilities "Covered stage" and every other characteristic "Not recorded", never "None".
- **Automated:** "shows every planning characteristic, and recorded absences as None, No or 0"; "marks every field the server says wasn't recorded as Not recorded, never as None"

**TC-35-17 · Details that fail to load are explained and can be loaded again**
- **Traces to:** AC5 · **Type:** Frontend, failure
- **Steps:** Select View details for Aurora while the details fail with 503 and a blank message; select it again once they load.
- **Expected result:** "Venue details could not be loaded. Please try again." beside Aurora and no details; then the details (Catering Yes) and no alert.
- **Automated:** "explains details that could not be loaded and loads them on another try"

## Traceability matrix

| AC | Backend | Frontend |
|----|---------|----------|
| AC1 | TC-35-01 to 04 | TC-35-13, 16 |
| AC2 | TC-35-05, 06 | TC-35-16 |
| AC3 | TC-35-02, 06 to 10 | TC-35-13, 16 |
| AC4 | TC-35-11 | TC-35-14 |
| AC5 | TC-35-12 | TC-35-15, 17 |

## Open questions for the customer

None open.
