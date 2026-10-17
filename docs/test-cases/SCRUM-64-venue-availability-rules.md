# SCRUM-64 — Define Availability Rules on the Venue Calendar (addressing SCRUM-36): Test Cases

**User story:** As an Event Coordinator, I want the venue calendar to follow clear availability rules so that I can trust which times a venue can be requested.

**Created:** 17 Oct 2026 · **Status of all cases:** Automated cases pass (17 Oct 2026, local PostgreSQL + Vitest; no schema change); TC-64-16 and 17 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_venue_availability_rules.py`, `backend/tests/test_scrum36_venue_availability.py` (updated expectations), `frontend/src/pages/VenueAvailabilityPage.test.jsx` · **Addresses:** SCRUM-36 (venue availability calendar), whose assumption A3 and expected calendars this story replaces · **Endpoint:** `GET /api/venues/<id>/availability` (SCRUM-36)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | A confirmed booking or recorded period of unavailability makes the venue unavailable only from its start time to its end time; other times within the venue's operating hours are shown as available. |
| AC2 | Times outside the venue's operating hours are shown as unavailable. |
| AC3 | A booking that ends at the same time another begins is not treated as overlapping. |
| AC4 | Each unavailable period on the calendar shows whether it is a booking or a recorded period of unavailability. |

## What changes from SCRUM-36

SCRUM-36 already does the following, and this story keeps it:
- it makes only a record's own period unavailable (AC1);
- it treats periods as half-open, so touching periods don't overlap (AC3);
- it lists each booking and block with its type (AC4).

It differs from these acceptance criteria in two ways:
- **Outside operating hours** was its own status, "outside operating hours", meaning neither booked nor available (SCRUM-36 A3). AC2 says that time is **unavailable**.
- **The day's slots** said only "unavailable". They didn't say what made the time unavailable, so a booking and a block that overlapped were merged into one slot (AC4).

Following the Week 7 *Guide to Managing Changes*, SCRUM-36's affected test cases (TC-36-01, 03, 11, 12, 14–20) keep their IDs, with expected results updated to these rules. Its document notes the change.

## Working assumptions

These are the team's current reading of the story, agreed with the scrum lead on 17 Oct 2026. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Statuses and causes:** each slot of the day has one of three statuses.
  - **available:** within operating hours and not covered by a confirmed booking or a block.
  - **unavailable:** the venue can't be requested at that time. The slot's `causes` list says why, in this order:
    - `booking`: a confirmed booking;
    - `block`: a recorded period of unavailability;
    - `outside_operating_hours`: outside the venue's operating hours.
  - **hours_not_recorded:** see A5.

  Available and hours-not-recorded slots have no causes.
- **A2 — Slots split where the cause changes:** neighbouring slots are merged only when their status and causes are both the same. So a booking from 10:00 to 12:00 and a block from 11:00 to 13:00 give three slots:
  - 10:00–11:00, booking;
  - 11:00–12:00, booking and block;
  - 12:00–13:00, block.

  Two back-to-back bookings give one "booking" slot, while the list of periods still shows each booking separately.
- **A3 — Every cause is listed:** time covered by a booking or block *and* outside operating hours lists both causes. *(Q2)*
- **A4 — What counts (unchanged from SCRUM-36):**
  - Only confirmed bookings and recorded blocks at the same venue make time unavailable. Pending, rejected and cancelled bookings don't, and aren't listed. *(SCRUM-36 Q2)*
  - Periods run from their start up to, but not including, their end (SCRUM-36 A4).
- **A5 — Operating hours not recorded:**
  - For a venue whose hours aren't recorded or can't be read, free time is shown as "Operating hours not recorded — confirm with venue staff". It is never shown as available, and never claimed to be outside operating hours.
  - Bookings and blocks there are still unavailable, with their cause. *(Q1)*
- **A6 — Out of scope:**
  - **Setup and turnaround time** (Week 7 customer change 1) is a separate story. Until it is built, a booking blocks exactly its own start and end, as AC1 says.
  - **The "not currently bookable" flag** is unchanged. *(Q3)*
  - **Venue booking requests** are still accepted at times the calendar shows as unavailable (SCRUM-39 TC-39-22). Venue Staff check conflicts when approving (SCRUM-40/41). *(Q4)*

## Endpoint under test

`GET /api/venues/<id>/availability?from=YYYY-MM-DD[&to=YYYY-MM-DD]` (SCRUM-36). Everything else in the reply is unchanged. Only the slots change:
- each slot is `{"start", "end", "status", "causes"}`;
- `status` is `"available"`, `"unavailable"` or `"hours_not_recorded"`, and no longer `"outside_operating_hours"`;
- `causes` is an ordered subset of `["booking", "block", "outside_operating_hours"]`. It is non-empty exactly when the status is `"unavailable"`.

## Seed data (AV-SEED)

SCRUM-36's AV-SEED, reset before **every** test case:
- **users:** alice (coordinator) and gus (venue staff);
- **venues:**
  - Aurora Ballroom, Mon–Sun 08:00–23:00;
  - Civic Hall, Mon–Fri 09:00–18:00;
  - Bayfront Pavilion, hours not recorded;
- **records** (Thu 15 – Sat 17 Oct 2026, Singapore time):

| Ref | Venue | Kind | Status / reason | Start | End |
|-----|-------|------|-----------------|-------|-----|
| B1 | Aurora Ballroom | Booking | Confirmed | Thu 15 Oct 10:00 | Thu 15 Oct 12:00 |
| K3 | Aurora Ballroom | Block | AV rigging | Thu 15 Oct 11:00 | Thu 15 Oct 13:00 |
| B2 | Aurora Ballroom | Booking | Confirmed | Thu 15 Oct 14:00 | Thu 15 Oct 16:00 |
| K1 | Aurora Ballroom | Block | Floor polishing | Thu 15 Oct 16:00 | Thu 15 Oct 17:00 |
| B3 | Aurora Ballroom | Booking | Pending | Thu 15 Oct 18:00 | Thu 15 Oct 20:00 |
| B4 | Aurora Ballroom | Booking | Cancelled | Thu 15 Oct 20:00 | Thu 15 Oct 21:00 |
| K2 | Aurora Ballroom | Block | Electrical works | Fri 16 Oct 20:00 | Sat 17 Oct 12:00 |
| B6 | Civic Hall | Booking | Confirmed | Thu 15 Oct 09:00 | Thu 15 Oct 18:00 |

**Expected calendar for Aurora Ballroom on Thu 15 Oct** (replaces SCRUM-36's table):

| Time | Shown as |
|------|----------|
| 00:00–08:00 | Unavailable — outside operating hours |
| 08:00–10:00 | Available |
| 10:00–11:00 | Unavailable — confirmed booking (B1) |
| 11:00–12:00 | Unavailable — confirmed booking, recorded block (B1, K3) |
| 12:00–13:00 | Unavailable — recorded block (K3) |
| 13:00–14:00 | Available |
| 14:00–16:00 | Unavailable — confirmed booking (B2) |
| 16:00–17:00 | Unavailable — recorded block (K1) |
| 17:00–23:00 | Available (pending B3 and cancelled B4 do not count) |
| 23:00–24:00 | Unavailable — outside operating hours |

---

## AC1 — A record makes only its own period unavailable

**TC-64-01 · A booking makes only its own period unavailable**
- **Traces to:** AC1, AC4 · **Type:** Happy path
- **Preconditions:** AV-SEED, plus B8: a confirmed booking at Civic Hall, Wed 14 Oct 12:00–13:00.
- **Steps:** As `alice`, view Civic Hall for 14 Oct 2026.
- **Expected result:**
  - 09:00–12:00 is available.
  - 12:00–13:00 is unavailable (booking).
  - 13:00–18:00 is available.
- **Automated:** `test_booking_makes_only_its_own_period_unavailable`; also TC-36-18 (updated).

**TC-64-02 · A recorded block makes only its own period unavailable**
- **Traces to:** AC1, AC4 · **Type:** Happy path
- **Preconditions:** AV-SEED, plus a block "Fire drill" at Aurora Ballroom, Mon 19 Oct 15:00–16:00.
- **Expected result:**
  - 08:00–15:00 is available.
  - 15:00–16:00 is unavailable (block).
  - 16:00–23:00 is available.
- **Automated:** `test_block_makes_only_its_own_period_unavailable`

**TC-64-03 · The expected calendar for Aurora Ballroom on 15 Oct**
- **Traces to:** AC1, AC2, AC4 · **Type:** Happy path
- **Steps:** As `alice`, view Aurora Ballroom for 15 Oct 2026.
- **Expected result:** the slots match *Expected calendar for Aurora Ballroom on Thu 15 Oct* exactly. B1, K3, B2 and K1 are listed, each with its type.
- **Automated:** TC-36-01 (`test_coordinator_views_one_day_with_bookings_and_blocks`, updated); also TC-36-02, 26 and 29, which compare against the same calendar.

**TC-64-04 · Bookings that are not confirmed do not make time unavailable**
- **Traces to:** AC1 · **Type:** Negative (regression)
- **Expected result:** 18:00–21:00 on 15 Oct is available. Pending B3 and cancelled B4 aren't listed.
- **Automated:** TC-36-13 (`test_pending_and_cancelled_bookings_do_not_block_time`); TC-36-22 and 23 (refresh after confirming or cancelling).

**TC-64-05 · Another venue's records do not affect this venue**
- **Traces to:** AC1 · **Type:** Negative (regression)
- **Expected result:**
  - Civic Hall on 15 Oct: 00:00–09:00 is unavailable (outside operating hours), 09:00–18:00 is unavailable (booking B6), and 18:00–24:00 is unavailable (outside operating hours).
  - Aurora Ballroom matches TC-64-03.
- **Automated:** TC-36-16 (`test_other_venues_bookings_do_not_affect_this_venue`, updated).

## AC2 — Outside operating hours is unavailable

**TC-64-06 · Time outside operating hours is unavailable, at exactly the hours' edges**
- **Traces to:** AC2, AC4 · **Type:** Boundary
- **Steps:** As `alice`, view Aurora Ballroom for Mon 19 Oct 2026, which has nothing recorded.
- **Expected result:**
  - 00:00–08:00 is unavailable (outside operating hours).
  - 08:00–23:00 is available.
  - 23:00–24:00 is unavailable (outside operating hours).
  - 07:59 is unavailable, 08:00 is available, 22:59 is available and 23:00 is unavailable.
  - The empty-state message is still shown.
- **Automated:** `test_time_outside_operating_hours_is_unavailable`; also TC-36-17 and 20 (updated).

**TC-64-07 · A day the venue is closed is unavailable all day**
- **Traces to:** AC2 · **Type:** Negative (business rule)
- **Steps:** As `alice`, view Civic Hall (Mon–Fri 09:00–18:00) for Sat 17 Oct 2026.
- **Expected result:** One slot, 00:00–24:00, unavailable (outside operating hours). No time is available, and nothing is listed.
- **Automated:** `test_closed_day_is_unavailable_all_day`; also TC-36-19 (updated).

**TC-64-08 · A record that runs outside operating hours lists both causes**
- **Traces to:** AC2, AC4 · **Type:** Boundary · **Depends on:** Q2
- **Steps:** As `alice`, view Aurora Ballroom for 16–17 Oct 2026. K2 is a block from Fri 20:00 to Sat 12:00.
- **Expected result:**
  - **Fri 16 Oct:**
    - 08:00–20:00 is available;
    - 20:00–23:00 is unavailable (block);
    - 23:00–24:00 is unavailable (block, outside operating hours).
  - **Sat 17 Oct:**
    - 00:00–08:00 is unavailable (block, outside operating hours);
    - 08:00–12:00 is unavailable (block);
    - 12:00–23:00 is available.
- **Automated:** `test_record_outside_operating_hours_lists_both_causes`; also TC-36-03 and 11.

**TC-64-09 · Free time at a venue without recorded hours is neither available nor unavailable**
- **Traces to:** AC1, AC2 · **Type:** Negative · **Depends on:** Q1
- **Preconditions:** AV-SEED, plus a confirmed booking at Bayfront Pavilion (hours not recorded), 15 Oct 10:00–12:00.
- **Expected result:**
  - 00:00–10:00 and 12:00–24:00 are "hours not recorded", with no causes.
  - 10:00–12:00 is unavailable (booking).
  - No time is available, and none is marked as outside operating hours.
- **Automated:** `test_unrecorded_hours_are_neither_available_nor_unavailable`

## AC3 — Touching periods do not overlap

**TC-64-10 · A booking that ends as a block begins**
- **Traces to:** AC3, AC4 · **Type:** Boundary
- **Steps:** View Aurora Ballroom for 15 Oct 2026. B2 ends at 16:00 and K1 starts at 16:00.
- **Expected result:**
  - 14:00–16:00 is unavailable (booking), and 16:00–17:00 is unavailable (block).
  - Nothing is both at 16:00, and there is no zero-length slot.
  - 13:00–14:00 and 17:00 onward are available.
- **Automated:** `test_booking_ending_as_a_block_begins_does_not_overlap`; also TC-36-15 (updated).

**TC-64-11 · A booking that ends as another booking begins**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:** AV-SEED, plus two confirmed bookings at Aurora Ballroom on Mon 19 Oct: 10:00–12:00 and 12:00–14:00.
- **Expected result:**
  - Both bookings can be saved: the database rule from SCRUM-41 doesn't treat them as overlapping.
  - Both are listed, separately, with their own times.
  - 10:00–14:00 is one unavailable (booking) slot.
  - 09:59 and 14:00 are available.
- **Automated:** `test_booking_ending_as_another_begins_does_not_overlap`

**TC-64-12 · Records touching the edges of the selected range**
- **Traces to:** AC3 · **Type:** Boundary (regression)
- **Expected result:**
  - A block ending exactly at 00:00 on 15 Oct isn't listed for 15 Oct.
  - One that starts exactly at the next midnight isn't listed either.
  - Ones that cross into the day by a minute are listed, and their minute is unavailable.
- **Automated:** TC-36-12 (`test_records_touching_the_range_edges`, updated).

**TC-64-13 · Approval and the database rule treat touching periods as not overlapping**
- **Traces to:** AC3 · **Type:** Boundary (regression)
- **Automated:** SCRUM-40 TC-40-11 (`test_periods_that_only_touch_do_not_conflict`), SCRUM-41 TC-41-04 and TC-41-13.

## AC4 — Each unavailable period says what it is

**TC-64-14 · Each unavailable slot names its cause, split where the cause changes**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** View Aurora Ballroom for 15 Oct 2026. B1 (booking, 10:00–12:00) overlaps K3 (block, 11:00–13:00).
- **Expected result:**
  - 10:00–11:00 is unavailable (booking).
  - 11:00–12:00 is unavailable (booking, block).
  - 12:00–13:00 is unavailable (block).
  - Available slots have no causes.
- **Automated:** `test_each_unavailable_slot_names_its_cause`; also TC-36-14 (updated).

**TC-64-15 · Each listed period shows its type and full times**
- **Traces to:** AC4 · **Type:** Happy path (regression)
- **Automated:** TC-36-01 (`test_each_period_shows_its_type_start_and_end`).

**TC-64-16 · Frontend: each slot shows its status and why it is unavailable**
- **Traces to:** AC2, AC4 · **Type:** Happy path (frontend)
- **Steps:** Open the calendar for Aurora Ballroom on 15 Oct.
- **Expected result:** The day shows, in order:
  - "00:00–08:00 Unavailable — outside operating hours"
  - "08:00–10:00 Available"
  - "10:00–11:00 Unavailable — confirmed booking"
  - "11:00–12:00 Unavailable — confirmed booking, recorded block"
  - "12:00–13:00 Unavailable — recorded block"
  - and so on to "23:00–24:00 Unavailable — outside operating hours".

  No time outside 08:00–23:00 is shown as available.
- **Automated:** "shows why each unavailable slot is unavailable" (`VenueAvailabilityPage.test.jsx`); the TC-36-01 frontend test (updated).

**TC-64-17 · Frontend: unrecorded hours keep their own label**
- **Traces to:** AC2 · **Type:** Negative (frontend, regression) · **Depends on:** Q1
- **Expected result:** Free time shows "Operating hours not recorded — confirm with venue staff", never "Available".
- **Automated:** TC-36-21's frontend test ("labels time with unrecorded operating hours").

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 09 |
| AC2 | 03, 06, 07, 08, 09, 16, 17 |
| AC3 | 10, 11, 12, 13 |
| AC4 | 01, 02, 03, 06, 08, 10, 14, 15, 16 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 14, 15, 16 |
| Negative | 04, 05, 07, 09, 17 |
| Boundary | 06, 08, 10, 11, 12, 13 |
| Frontend | 16, 17 |
| Regression (earlier stories' tests) | 04, 05, 12, 13, 15, 17 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | How should free time be shown for a venue whose operating hours are not recorded? Assumed: "Operating hours not recorded — confirm with venue staff", neither available nor unavailable. (SCRUM-36 Q4) | A5, TC-64-09, 17 |
| Q2 | When a booking or block runs outside operating hours, should the calendar give both reasons (assumed) or only the booking or block? | A3, TC-64-08 |
| Q3 | Should a venue marked "not currently bookable" show all its time as unavailable? (SCRUM-36 Q6) | A6 |
| Q4 | Should coordinators be stopped from requesting a venue for times the calendar shows as unavailable? Assumed not: Venue Staff check conflicts when approving. | A6 |
