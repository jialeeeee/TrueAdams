# SCRUM-37 — Search for Available Venues: Test Cases

**User story:** As an Event Coordinator, I want to search for available venues using my event's requirements so that I can identify suitable booking options.

**Created:** 27 Sep 2026 · **Status of all cases:** Not run (feature not yet built)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can enter or select the requested date, start/end times, minimum capacity, location, accessibility needs, supported layout, and one or more required facilities. |
| AC2 | Each supported filter can be applied individually, and multiple filters can be combined. |
| AC3 | Results satisfy all selected filters. |
| AC4 | For a search with a date and time, venues with incompatible overlapping confirmed bookings or recorded periods of unavailability are excluded. |
| AC5 | Results show the venue's identity, location, capacity, and relevant matching characteristics, with access to further details. |
| AC6 | When no venues match, the coordinator is told that no matches were found and can revise the filters. |
| AC7 | If the search fails, an error is displayed rather than a misleading "no matching venues" result. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may search:** only coordinators. Venue staff, organisers, attendees and technical support staff may not. *(Q4)*
- **A2 — Matching text:** the location filter matches any venue whose location *contains* the entered text, ignoring case. Facilities, accessibility features and layouts must match a recorded value exactly, ignoring case, so "Stage" does not match "Covered stage". *(Q1)*
- **A3 — Several values:** when several facilities or accessibility needs are selected, a venue must have **all** of them.
- **A4 — Missing information:** a field that was never recorded (NULL or blank) never satisfies a filter on that field. Neither does a field recorded as "none" (an empty list). When no filter is applied to a field, its value does not affect the results. *(Q2)*
- **A5 — Date and time filter:** the date, start time and end time must be given together. The end must be after the start, on the same date. All times are Singapore time (SGT, UTC+8). *(Q6)*
- **A6 — Incompatible:** any time overlap with a *confirmed* booking or a recorded block at that venue, the same rule as SCRUM-36. Pending, rejected and cancelled bookings do not exclude a venue. A period runs up to but not including its end, so a booking ending at 12:00 does not clash with a request starting at 12:00. *(Q8)*
- **A7 — Operating hours:** in a date and time search, the requested times must also fall within the venue's operating hours. Venues whose hours are not recorded, or are "By appointment", are excluded from date and time searches. This matches SCRUM-36 A3. *(Q3)*
- **A8 — Not currently bookable:** venues marked as not currently bookable (`is_available = false`) never appear in search results. They can still be browsed through View Venue Details. *(Q7)*
- **A9 — No filters:** a search with no filters returns every bookable venue.
- **A10 — Capacity:** the minimum capacity is a whole number of at least 1. A venue matches when its capacity is **greater than or equal to** the minimum.
- **A11 — Order:** results are sorted by venue name.

## Seed data (SV-SEED)

Reset the database to this data before **every** test case. Users and the first five venues reuse `backend/tests/fixtures/venue_data.py`; Harbour Room and Summit Hall are new rows for this story.

**Users**

| Key | Email | Role |
|-----|-------|------|
| coordinator | alice.coordinator@connectsphere.test | coordinator |
| venue_staff | gus.venue@connectsphere.test | venue_staff |
| organiser | dana.organiser@connectsphere.test | organiser |
| attendee | farah.attendee@connectsphere.test | attendee |
| tech_staff | hana.tech@connectsphere.test | tech_staff |

**Venues**

| Venue | Location | Capacity | Facilities | Accessibility | Layouts | Operating hours | Bookable |
|-------|----------|----------|------------|---------------|---------|-----------------|----------|
| Aurora Ballroom | Level 3, Marina Tower, 10 Bayfront Ave | 400 | Stage, Projector, PA system, Wi-Fi, Green room | Wheelchair ramp, Accessible toilets, Hearing loop | theatre, banquet, cabaret, cocktail | Mon-Sun 08:00-23:00 | Yes |
| Bayfront Pavilion | Bayfront Park, East Lawn | *not recorded* | Covered stage | *not recorded* | *not recorded* | *not recorded* | Yes |
| Civic Hall | 12 Civic Road | 80 | *none (recorded)* | *none (recorded)* | theatre | Mon-Fri 09:00-18:00 | Yes |
| Dockside Studio | Pier 4, Harbourfront | 60 | Blackout blinds, Lighting rig | Step-free entrance | classroom, boardroom | By appointment | **No** |
| Evergreen Loft | *blank* | 50 | Kitchenette | *not recorded* | u_shape | *blank* | Yes |
| Harbour Room | Level 2, Marina Tower, 10 Bayfront Ave | 120 | Projector, Wi-Fi | Wheelchair ramp | theatre, classroom | Mon-Sun 08:00-22:00 | Yes |
| Summit Hall | 5 Orchard Link | 400 | Stage, Projector, PA system | Wheelchair ramp, Accessible toilets | theatre, banquet | Mon-Sat 08:00-23:00 | Yes |

**Bookings and blocks** (all on Thu 15 Oct 2026)

| Ref | Venue | Kind | Status / reason | Start | End |
|-----|-------|------|-----------------|-------|-----|
| B1 | Aurora Ballroom | Booking | Confirmed | 10:00 | 12:00 |
| K1 | Harbour Room | Block | Maintenance | 13:00 | 15:00 |
| B2 | Summit Hall | Booking | Pending | 10:00 | 12:00 |
| B3 | Summit Hall | Booking | Cancelled | 14:00 | 16:00 |
| B4 | Civic Hall | Booking | Confirmed | 09:00 | 18:00 |

---

## AC1 & AC2 — Enter filters, apply them individually or combined

**TC-37-01 · Search using every filter**
- **Traces to:** AC1, AC2, AC3, AC4, AC5 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Open venue search. 2. Enter every filter below. 3. Search.
- **Test data:** Date = 2026-10-15; Start = 18:00; End = 21:00; Minimum capacity = 100; Location = "Marina Tower"; Accessibility = Wheelchair ramp; Layout = theatre; Facilities = Projector, Wi-Fi.
- **Expected result:** Exactly two results, in this order: **Aurora Ballroom**, **Harbour Room**. Each shows its name, location, capacity, the matched characteristics (Projector, Wi-Fi, theatre, Wheelchair ramp) and a link to its details. Summit Hall is excluded on location.

**TC-37-02 · Search with no filters**
- **Traces to:** AC2 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Open venue search and search without entering any filter.
- **Test data:** *(none)*
- **Expected result:** Aurora Ballroom, Bayfront Pavilion, Civic Hall, Evergreen Loft, Harbour Room, Summit Hall. Dockside Studio is not listed (A8).

**TC-37-03 · Minimum capacity only**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with only a minimum capacity.
- **Test data:** Minimum capacity = 100.
- **Expected result:** Aurora Ballroom (400), Harbour Room (120), Summit Hall (400).

**TC-37-04 · Location only**
- **Traces to:** AC1, AC2 · **Type:** Happy path · **Depends on:** Q1
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each location below as the only filter.
- **Test data:** (a) "Marina Tower". (b) "marina tower". (c) "Bayfront".
- **Expected result:** (a) and (b) both return Aurora Ballroom and Harbour Room. (c) returns Aurora Ballroom, Bayfront Pavilion and Harbour Room, because "10 Bayfront Ave" also contains "Bayfront".

**TC-37-05 · Accessibility needs only**
- **Traces to:** AC1, AC2, AC3 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each accessibility selection below as the only filter.
- **Test data:** (a) Wheelchair ramp. (b) Accessible toilets. (c) Wheelchair ramp + Hearing loop.
- **Expected result:** (a) Aurora Ballroom, Harbour Room, Summit Hall. (b) Aurora Ballroom, Summit Hall. (c) Aurora Ballroom only.

**TC-37-06 · Supported layout only**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each layout below as the only filter.
- **Test data:** (a) theatre. (b) classroom.
- **Expected result:** (a) Aurora Ballroom, Civic Hall, Harbour Room, Summit Hall. (b) Harbour Room only; Dockside Studio also supports classroom but is not bookable.

**TC-37-07 · Required facilities only**
- **Traces to:** AC1, AC2, AC3 · **Type:** Happy path / Boundary
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each facility selection below as the only filter.
- **Test data:** (a) Stage. (b) projector *(lower case)*. (c) Stage + PA system + Wi-Fi.
- **Expected result:** (a) Aurora Ballroom, Summit Hall. Bayfront Pavilion's "Covered stage" does **not** match "Stage". (b) Aurora Ballroom, Harbour Room, Summit Hall. (c) Aurora Ballroom only; Summit Hall has no Wi-Fi.

**TC-37-08 · Date and time only**
- **Traces to:** AC1, AC2, AC4 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with only a date and times.
- **Test data:** Date = 2026-10-15; Start = 10:00; End = 12:00.
- **Expected result:** Harbour Room, Summit Hall. Aurora Ballroom (B1) and Civic Hall (B4) are excluded as booked. Bayfront Pavilion and Evergreen Loft are excluded because their operating hours are not recorded (A7). Dockside Studio is excluded as not bookable.

**TC-37-09 · Combining filters narrows the results step by step**
- **Traces to:** AC2, AC3 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Search with minimum capacity and layout. 2. Add the facility and search again.
- **Test data:** (1) Minimum capacity = 100; Layout = banquet. (2) Add Facilities = Wi-Fi.
- **Expected result:** (1) Aurora Ballroom, Summit Hall. (2) Aurora Ballroom only.

**TC-37-10 · Only coordinators can search**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q4
- **Preconditions:** SV-SEED loaded.
- **Steps:** For each of `venue_staff`, `organiser`, `attendee` and `tech_staff`: log in and search with no filters.
- **Test data:** *(none)*
- **Expected result:** Each user sees a "not allowed" message (HTTP 403), and no venues are returned.

**TC-37-11 · Session required**
- **Traces to:** AC1 · **Type:** Negative (authentication)
- **Preconditions:** SV-SEED loaded; not logged in. Repeat with an expired token, and with a token for a user who has since been deleted.
- **Steps:** Search with no filters.
- **Test data:** *(none)*
- **Expected result:** The user is asked to log in (HTTP 401), and no venues are returned.

### Filter validation

**TC-37-12 · Invalid minimum capacity**
- **Traces to:** AC1 · **Type:** Negative / Boundary
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each value below as the minimum capacity.
- **Test data:** 0; -5; 12.5; "abc".
- **Expected result:** Each is rejected with a message asking for a whole number of at least 1 (HTTP 400). No results or "no matches" message is shown.

**TC-37-13 · Incomplete date and time filter**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each combination below.
- **Test data:** (a) Date = 2026-10-15 only. (b) Start = 10:00, End = 12:00, no date. (c) Date = 2026-10-15, Start = 10:00, no end.
- **Expected result:** Each is rejected with a message that the date, start time and end time must be entered together (HTTP 400).

**TC-37-14 · End time not after start time**
- **Traces to:** AC1 · **Type:** Negative / Boundary · **Depends on:** Q6
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each time range on 2026-10-15.
- **Test data:** (a) 14:00–14:00. (b) 14:00–13:00. (c) 14:00–14:01.
- **Expected result:** (a) and (b) are rejected with a message that the end time must be after the start time (HTTP 400). (c) is accepted.

**TC-37-15 · Invalid date**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with Start = 10:00, End = 12:00 and each date below.
- **Test data:** `2026-02-30`; `15/10/2026`; `tomorrow`.
- **Expected result:** Each is rejected with a message asking for a valid date (HTTP 400).

**TC-37-16 · Date in the past**
- **Traces to:** AC1 · **Type:** Negative / Boundary · **Depends on:** Q5 (**Blocked** until answered)
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`; test run on 27 Sep 2026 (or with today's date fixed to it).
- **Steps:** Search with Start = 10:00, End = 12:00 and each date below.
- **Test data:** (a) 2026-09-26 (yesterday). (b) 2026-09-27 (today). (c) 2026-09-28 (tomorrow).
- **Expected result (proposed):** (a) is rejected with a message that the date cannot be in the past. (b) and (c) are accepted.

**TC-37-17 · Unsupported layout value**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Send a search whose layout is not one of the supported options, e.g. by editing the request.
- **Test data:** Layout = "igloo".
- **Expected result:** Rejected with a message listing the supported layouts (HTTP 400).

## AC3 — Results satisfy all selected filters

**TC-37-18 · A venue meeting most but not all filters is excluded**
- **Traces to:** AC3 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with the filters below.
- **Test data:** Minimum capacity = 100; Layout = banquet; Accessibility = Hearing loop.
- **Expected result:** Aurora Ballroom only. Summit Hall meets capacity and layout but has no hearing loop, so it is excluded.

**TC-37-19 · Information that was never recorded does not satisfy a filter**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** Q2
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each filter below as the only filter.
- **Test data:** (a) Minimum capacity = 1. (b) Accessibility = Wheelchair ramp. (c) Location = "a".
- **Expected result:** (a) Aurora Ballroom, Civic Hall, Evergreen Loft, Harbour Room, Summit Hall; Bayfront Pavilion (capacity not recorded) is excluded. (b) Bayfront Pavilion and Evergreen Loft (accessibility not recorded) are excluded. (c) Evergreen Loft (blank location) is excluded.

**TC-37-20 · Recorded "none" is excluded only when that filter is used**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Search with Layout = theatre. 2. Add Facilities = Projector and search again.
- **Test data:** Civic Hall facilities = *none (recorded)*.
- **Expected result:** (1) Civic Hall is included. (2) Civic Hall is excluded; results are Aurora Ballroom, Harbour Room, Summit Hall.

**TC-37-21 · Minimum capacity boundaries**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each minimum capacity as the only filter.
- **Test data:** 399; 400; 401; 80; 81.
- **Expected result:**
  - 399 and 400: Aurora Ballroom, Summit Hall.
  - 401: no matches (see TC-37-30).
  - 80: Aurora Ballroom, Civic Hall, Harbour Room, Summit Hall.
  - 81: Aurora Ballroom, Harbour Room, Summit Hall.

**TC-37-22 · Venues that are not currently bookable never appear**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** Q7
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each filter below.
- **Test data:** (a) Accessibility = Step-free entrance. (b) Facilities = Lighting rig. (c) Location = "Pier 4".
- **Expected result:** Each search reports no matches. Dockside Studio, the only venue with these characteristics, is not listed.

## AC4 — Venues with incompatible bookings or blocks are excluded

**TC-37-23 · Overlap boundaries against a confirmed booking**
- **Traces to:** AC4 · **Type:** Boundary
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search on 2026-10-15 with each time range below as the only filter, and check whether Aurora Ballroom is listed.
- **Test data:** B1 books Aurora Ballroom 10:00–12:00.

| Request | Relationship to B1 | Aurora Ballroom listed? |
|---------|--------------------|-------------------------|
| 08:00–10:00 | Ends exactly when B1 starts | **Yes** |
| 12:00–14:00 | Starts exactly when B1 ends | **Yes** |
| 09:00–10:01 | Overlaps B1's first minute | No |
| 11:59–13:00 | Overlaps B1's last minute | No |
| 10:30–11:30 | Inside B1 | No |
| 09:00–13:00 | Contains B1 | No |

- **Expected result:** As shown in the table.

**TC-37-24 · A recorded block excludes the venue**
- **Traces to:** AC4 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with a date and times only.
- **Test data:** Date = 2026-10-15; Start = 14:00; End = 16:00. K1 blocks Harbour Room 13:00–15:00.
- **Expected result:** Aurora Ballroom, Summit Hall. Harbour Room is excluded (K1) and Civic Hall is excluded (B4).

**TC-37-25 · Pending and cancelled bookings do not exclude a venue**
- **Traces to:** AC4 · **Type:** Negative (business rule) · **Depends on:** Q8
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search on 2026-10-15 with each time range and check whether Summit Hall is listed.
- **Test data:** (a) 10:00–12:00 (pending B2). (b) 14:00–16:00 (cancelled B3).
- **Expected result:** Summit Hall is listed in both searches.

**TC-37-26 · A booking on another date does not exclude the venue**
- **Traces to:** AC4 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with a date and times only.
- **Test data:** Date = 2026-10-16 (Fri); Start = 10:00; End = 12:00.
- **Expected result:** Aurora Ballroom, Civic Hall, Harbour Room, Summit Hall. B1 and B4 are on 15 Oct and do not affect this date.

**TC-37-27 · Requested time outside operating hours**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** Q3
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with each date and time range below, and check the named venue.

| Request | Venue | Listed? |
|---------|-------|---------|
| Thu 15 Oct 20:00–22:00 | Harbour Room (closes 22:00) | **Yes** |
| Thu 15 Oct 21:00–23:00 | Harbour Room | No |
| Thu 15 Oct 07:00–09:00 | Aurora Ballroom (opens 08:00) | No |
| Sat 17 Oct 10:00–12:00 | Civic Hall (Mon–Fri only) | No |
| Sun 18 Oct 10:00–12:00 | Summit Hall (Mon–Sat only) | No |
| Mon 19 Oct 10:00–12:00 | Summit Hall | **Yes** |

- **Expected result:** As shown in the table.

## AC5 — Result content and access to details

**TC-37-28 · Each result shows identity, location, capacity and matching characteristics**
- **Traces to:** AC5 · **Type:** Happy path
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Search with the filters below. 2. Open the details link for Summit Hall.
- **Test data:** Minimum capacity = 300; Facilities = Stage.
- **Expected result:** (1) Two results: Aurora Ballroom and Summit Hall. Each shows its name, location, capacity (400) and the matched facility (Stage). Characteristics that were not filtered on are not shown as matches. (2) The link opens Summit Hall's venue details page (SCRUM-35), not another venue's.

**TC-37-29 · Missing location is shown as "not recorded"**
- **Traces to:** AC5 · **Type:** Boundary
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with the filter below.
- **Test data:** Layout = u_shape.
- **Expected result:** Evergreen Loft is listed, and its location is shown as "Not recorded", not as an empty space.

## AC6 — No matches

**TC-37-30 · No matches, then revise the filters**
- **Traces to:** AC6 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Search with minimum capacity 1000. 2. Change the minimum capacity to 300 and search again.
- **Test data:** (1) Minimum capacity = 1000. (2) Minimum capacity = 300.
- **Expected result:** (1) A message says no venues match the filters. The entered filters stay filled in so they can be edited. This is not shown as an error. (2) Aurora Ballroom, Summit Hall.

**TC-37-31 · Unknown facility gives no matches, not an error**
- **Traces to:** AC6 · **Type:** Negative
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`.
- **Steps:** Search with a facility no venue has.
- **Test data:** Facilities = Helipad.
- **Expected result:** The "no venues match" message from TC-37-30 is shown.

## AC7 — Failures are shown as errors, not as "no matches"

**TC-37-32 · Database unavailable during search**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Preconditions:** SV-SEED loaded; logged in as `coordinator`; the database is made to fail on the venue query (in automated tests, force an `OperationalError`, as `test_venue_details.py` does).
- **Steps:** Search with Minimum capacity = 100.
- **Test data:** Minimum capacity = 100.
- **Expected result:** An error says the search could not be completed and offers a retry (HTTP 503, `retryable: true`). The "no venues match" message is **not** shown, and no results are listed.

**TC-37-33 · Availability check fails during a date and time search**
- **Traces to:** AC4, AC7 · **Type:** Negative (failure)
- **Preconditions:** As TC-37-32, but only the query for bookings and blocks fails; the venue query succeeds.
- **Steps:** Search with Date = 2026-10-15, Start = 10:00, End = 12:00.
- **Test data:** As above.
- **Expected result:** The same error as TC-37-32. The venues are **not** listed without the availability check, so Aurora Ballroom and Civic Hall never appear as available.

**TC-37-34 · Retry succeeds after recovery**
- **Traces to:** AC7 · **Type:** Happy path (recovery)
- **Preconditions:** TC-37-32 has just produced the error; the database is then restored.
- **Steps:** Click Retry.
- **Test data:** Minimum capacity = 100 (still filled in).
- **Expected result:** The filters are unchanged, and the results match TC-37-03: Aurora Ballroom, Harbour Room, Summit Hall.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 03, 04, 05, 06, 07, 08, 10, 11, 12, 13, 14, 15, 16, 17 |
| AC2 | 01, 02, 03, 04, 05, 06, 07, 08, 09 |
| AC3 | 01, 05, 07, 09, 18, 19, 20, 21, 22 |
| AC4 | 01, 08, 23, 24, 25, 26, 27, 33 |
| AC5 | 01, 28, 29 |
| AC6 | 30, 31 |
| AC7 | 32, 33, 34 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 04, 05, 06, 07, 08, 09, 28, 34 |
| Negative | 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 22, 24, 25, 26, 30, 31, 32, 33 |
| Boundary | 07, 12, 14, 16, 20, 21, 23, 27, 29 |
| Cross-cutting (authorisation) | 10, 11 |

## Relationship to SCRUM-36

SCRUM-37's date and time filter must use the **same** overlap rule and booking data as SCRUM-36 (View Venue Availability). A venue shown as available for a slot on the SCRUM-36 calendar should appear in a SCRUM-37 search for that slot, and the reverse. Build SCRUM-36 first and reuse its overlap check.

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | How should location be searched: free text contained in the address (assumed), or a fixed list of areas? | A2, TC-37-04 |
| Q2 | Should venues whose information for a filter was never recorded be excluded (assumed), or shown separately as "possible matches — details not recorded"? | A4, TC-37-19 |
| Q3 | In a date and time search, must the venue also be open at the requested time? How should venues with unrecorded or "By appointment" hours be treated? (Same as SCRUM-36 Q1.) | A7, TC-37-08, 27 |
| Q4 | Can anyone besides Event Coordinators, e.g. Venue Staff, search venues? | A1, TC-37-10 |
| Q5 | Should searches for past dates be rejected? | TC-37-16 |
| Q6 | Can a requested event run past midnight into the next day? | A5, TC-37-14 |
| Q7 | Should venues marked as not currently bookable be hidden from search (assumed), or shown as unavailable? | A8, TC-37-06, 22 |
| Q8 | Should pending booking requests exclude a venue or show a warning? (Same as SCRUM-36 Q2.) | A6, TC-37-25 |
