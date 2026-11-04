# CF09 — One calendar showing all events, for planning: Test Cases

**Requirement:** CF09 Venue availability calendar: "Coordinators and Venue and Technical Support Staff also need one calendar showing all events, for planning." SCRUM-36/64 cover each venue's availability calendar; this covers the calendar of all events. *No Jira story exists for it yet; add one to the backlog (for example "Staff see one calendar of all events") before marking it Done.*

**Created:** 4 Nov 2026 · **Status of all cases:** automated cases pass (4 Nov 2026, local PostgreSQL as in CI + Vitest) · **Automated tests:** `backend/tests/test_events_calendar.py`, `frontend/src/pages/EventsCalendarPage.test.jsx` (+ the nav link in `App.test.jsx`) · **Endpoint:** `GET /api/venues/calendar?from=YYYY-MM-DD[&to=YYYY-MM-DD]` · **Page:** `/events/calendar`, "Events calendar" in the navigation · **Related:** SCRUM-36/64 (a venue's calendar, whose range rules this shares), SCRUM-85 (several venues per event), SCRUM-34 (only the event's coordinator opens its planning view)

## Criteria (proposed, to agree)

| ID | Criterion |
|----|-----------|
| C1 | Coordinators, Venue Staff and Technical Support Staff can see one calendar of every event planned for the days they choose. Anyone else is denied. |
| C2 | Each event shows its name, date and time, status, coordinator and the venues booked or requested for it, grouped by day. |
| C3 | A coordinator can open the planning view of their own events from the calendar. |
| C4 | A failed load is shown as an error, never as an empty calendar. |

## Working assumptions (team decisions, 4 Nov 2026)

- **A1 — Who (C1):** the `coordinator`, `venue_staff` and `tech_staff` roles, as main or additional role (CF01). The Lead, Safety Officer, organisers, attendees and admin are not named by CF09 and get 403. *(Q1)*
- **A2 — Which events (C1):** `submitted`, `under_review`, `approved` and `confirmed` events whose time overlaps the chosen days (Singapore time, half-open, so an event ending at midnight as the range starts isn't in it). Drafts, rejected and cancelled events have no plan to show. Soonest first; the page groups them by the day they start. *(Q2)*
- **A3 — Venues (C2):** the event's pending, tentative (until the hold expires) and confirmed bookings, in time order, each with its status, so planners see what is requested as well as what is confirmed. Rejected, cancelled, replaced and expired ones are left out.
- **A4 — What is shown (C2, C3):** name, start and end, status, coordinator (or "Not assigned yet") and venues. Nothing else of the event's planning information, which stays with its coordinator. `managed` is true only for the caller's own events, which the page links to their planning view.
- **A5 — The range:** as a venue's calendar (SCRUM-36): `from` is required, `to` is optional (the same day), the end can't be before the start, and at most 31 days (`MAX_RANGE_DAYS`, still an open question there). Problems are 400 with a message.
- **A6 — Failures (C4):** any failed read is 503 `retryable`, with no partial list.

## Seed data (EC-SEED)

Coordinators **alice** and **ben**, Venue Staff **gus**, Technical Support **hana**, organiser **dana**, attendee **farah**, Lead **lena**, Safety Officer **sam**, **admin**; venues Calendar Hall, Annex and Garden. In 2027: E1 "Harbour Talk" approved (alice) 10 Jun 10:00–12:00, with a confirmed Hall booking, a tentative Annex hold, a pending Garden request and rejected, cancelled, replaced, expired and lapsed-hold bookings; E2 "Night Market" confirmed (ben) 11 Jun 22:00–12 Jun 02:00; E3 "Book Fair" submitted, no coordinator, 12 Jun; E4 "Film Night" under review (ben) 12 Jun; and, left out, a draft, a rejected and a cancelled event on 10 Jun, an event on 20 Jun, one ending at 00:00 on 10 Jun and one starting at 00:00 on 13 Jun. "Now" is 2027-05-01 09:00.

## Test cases

| ID | Traces to | What it checks | Automated |
|----|-----------|----------------|-----------|
| TC-CF09-01 | C1, C2 | 10–12 Jun lists E1, E2, E3, E4 in that order with their times, status and coordinator (none for E3); the others are left out | `test_tc_cf09_01_every_event_with_a_plan_in_the_range_soonest_first` |
| TC-CF09-02 | C2 | E1's venues: Annex (tentative), Hall (confirmed), Garden (pending), in time order; no dead bookings | `test_tc_cf09_02_each_event_lists_the_venues_booked_or_requested_for_it` |
| TC-CF09-03 | C1 | 12 Jun alone includes E2, which runs into it | `test_tc_cf09_03_an_event_running_into_the_range_is_shown` |
| TC-CF09-04 | C3 | `managed` is true only for alice's own E1; never for Venue Staff | `test_tc_cf09_04_only_the_events_own_coordinator_may_open_it` |
| TC-CF09-05 | C1 | Days with no events: an empty list with "No events are planned for these dates." | `test_tc_cf09_05_no_events_says_so` |
| TC-CF09-06 | C1 | alice, gus and hana may; dana, farah, lena, sam and admin get 403 without events; no token is 401; the role as an additional one is enough | `test_tc_cf09_06_coordinators_venue_and_tech_staff_only`, `test_tc_cf09_06_the_role_may_be_an_additional_one` |
| TC-CF09-07 | A5 | No start, a bad date, an end before the start, 32 days: 400; 31 days: 200 | `test_tc_cf09_07_the_range_follows_the_venue_calendars_rules` |
| TC-CF09-08 | C4 | A failed read: 503 `retryable`, no events | `test_tc_cf09_08_a_failed_load_is_an_error_not_an_empty_calendar` |
| TC-CF09-09 | C2, C3 | The page groups events by day, shows times, status, coordinator and venues with their status, links only the coordinator's own events | frontend "shows every event by day, with its venues, status and coordinator" |
| TC-CF09-10 | C1, A5 | A start date is required; only `from` is sent without an end; the empty message is shown | frontend "asks for a start date, sends only it when there is no end, and says when nothing is planned" |
| TC-CF09-11 | C4, A5 | A refused range is explained without Retry; a failed load is explained with Retry, which works | frontend "explains a refused range or a failed load, and offers Retry only when it can help" |

**Navigation:** "Events calendar" is in the menu for coordinators, Venue Staff and Technical Support Staff. **Test baseline change (Definition of Done 5):** `App.test.jsx`'s list of the links Venue Staff see now includes it, and a Technical Support case was added; nothing else in that test changed.

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should the Event Coordinator Lead and the Safety Officer see the events calendar too? | A1 |
| Q2 | Should submitted and under-review events, which have no approved plan yet, appear (as built: yes, so planners see what is coming)? | A2 |
