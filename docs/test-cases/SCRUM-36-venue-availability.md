# SCRUM-36 — View Venue Availability by Date and Time: Test Cases

**User story:** As an authorised internal user, I want to view a venue's availability for a selected period so that I can identify possible event times.

**Created:** 27 Sep 2026 · **Status of all cases:** Not run (feature not yet built)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The user can select a venue and date or date range to view its availability. |
| AC2 | Confirmed bookings and recorded periods of unavailability are displayed with their start and end dates and times. |
| AC3 | A period covered by an incompatible confirmed booking or recorded block is not displayed as available. |
| AC4 | Times outside those periods are assessed separately under the agreed scheduling rules rather than treating the entire day as unavailable. |
| AC5 | When a confirmed booking or recorded block changes, a refreshed calendar reflects the saved change. |
| AC6 | If availability cannot be loaded, the calendar displays an error rather than representing unknown periods as available. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may view:** coordinators and venue staff, the same roles as View Venue Details (SCRUM-35). Organisers, attendees and technical support staff may not. *(Q3)*
- **A2 — Incompatible:** any time overlap with a *confirmed* booking or a recorded block at the same venue. Pending, rejected and cancelled bookings do not make time unavailable and are not shown. *(Q2)*
- **A3 — Scheduling rules:** time is *available* when it falls within the venue's operating hours and is not covered by a confirmed booking or block. Time outside operating hours is shown as *outside operating hours*: it is neither booked nor available. *(Q1)*
- **A4 — Touching periods:** a period runs from its start up to, but not including, its end. A record ending at 16:00 and another starting at 16:00 do not overlap, and a record ending at exactly 00:00 does not appear on the following day.
- **A5 — Time zone:** all dates and times are Singapore time (SGT, UTC+8).
- **A6 — Display:** each displayed period shows its type (confirmed booking or recorded block), its full start date and time, and its full end date and time, even if it extends beyond the selected range.

## Seed data (AV-SEED)

Reset the database to this data before **every** test case, so that one test cannot affect the next. Users and venues reuse `backend/tests/fixtures/venue_data.py`.

**Users**

| Key | Email | Role |
|-----|-------|------|
| coordinator | alice.coordinator@connectsphere.test | coordinator |
| venue_staff | gus.venue@connectsphere.test | venue_staff |
| organiser | dana.organiser@connectsphere.test | organiser |
| attendee | farah.attendee@connectsphere.test | attendee |
| tech_staff | hana.tech@connectsphere.test | tech_staff |

**Venues**

| Venue | Operating hours |
|-------|-----------------|
| Aurora Ballroom | Mon-Sun 08:00-23:00 |
| Civic Hall | Mon-Fri 09:00-18:00 |
| Bayfront Pavilion | *not recorded* |

**Bookings and blocks** (Thu 15 Oct – Sat 17 Oct 2026)

| Ref | Venue | Kind | Status / reason | Start | End |
|-----|-------|------|-----------------|-------|-------|
| B1 | Aurora Ballroom | Booking | Confirmed | Thu 15 Oct 10:00 | Thu 15 Oct 12:00 |
| K3 | Aurora Ballroom | Block | AV rigging | Thu 15 Oct 11:00 | Thu 15 Oct 13:00 |
| B2 | Aurora Ballroom | Booking | Confirmed | Thu 15 Oct 14:00 | Thu 15 Oct 16:00 |
| K1 | Aurora Ballroom | Block | Floor polishing | Thu 15 Oct 16:00 | Thu 15 Oct 17:00 |
| B3 | Aurora Ballroom | Booking | Pending | Thu 15 Oct 18:00 | Thu 15 Oct 20:00 |
| B4 | Aurora Ballroom | Booking | Cancelled | Thu 15 Oct 20:00 | Thu 15 Oct 21:00 |
| K2 | Aurora Ballroom | Block | Electrical works | Fri 16 Oct 20:00 | Sat 17 Oct 12:00 |
| B6 | Civic Hall | Booking | Confirmed | Thu 15 Oct 09:00 | Thu 15 Oct 18:00 |

**Expected calendar for Aurora Ballroom on Thu 15 Oct** (used by several cases):

| Time | Shown as |
|------|----------|
| 00:00–08:00 | Outside operating hours |
| 08:00–10:00 | Available |
| 10:00–13:00 | Unavailable (B1 10:00–12:00, K3 11:00–13:00) |
| 13:00–14:00 | Available |
| 14:00–17:00 | Unavailable (B2 14:00–16:00, K1 16:00–17:00) |
| 17:00–23:00 | Available (pending B3 and cancelled B4 do not block) |
| 23:00–24:00 | Outside operating hours |

---

## AC1 — Select a venue and a date or date range

**TC-36-01 · Coordinator views one day with bookings and blocks**
- **Traces to:** AC1, AC2, AC3, AC4 · **Type:** Happy path
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Open Aurora Ballroom's availability calendar. 2. Select the date 15 Oct 2026. 3. View availability.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** The calendar matches the *Expected calendar for Aurora Ballroom on Thu 15 Oct* table exactly. It lists B1, K3, B2 and K1, each with its type and its start and end dates and times. B3 and B4 are not listed.

**TC-36-02 · Venue staff can view availability**
- **Traces to:** AC1 · **Type:** Cross-cutting (authorisation)
- **Preconditions:** AV-SEED loaded; logged in as `venue_staff`.
- **Steps:** As TC-36-01.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** Same calendar as TC-36-01.

**TC-36-03 · View a multi-day date range**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Open Aurora Ballroom's availability calendar. 2. Select the range 15 Oct 2026 to 17 Oct 2026. 3. View availability.
- **Test data:** Venue = Aurora Ballroom; From = 2026-10-15; To = 2026-10-17.
- **Expected result:** All three days are shown. Thu 15 Oct matches TC-36-01. K2 is shown once, from Fri 16 Oct 20:00 to Sat 17 Oct 12:00, covering both days. Fri 16 Oct 08:00–20:00 is available. Sat 17 Oct 12:00–23:00 is available. Sat 17 Oct 08:00–12:00 is unavailable.

**TC-36-04 · Users outside the authorised roles are refused**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q3
- **Preconditions:** AV-SEED loaded.
- **Steps:** For each of `organiser`, `attendee` and `tech_staff`: 1. Log in as that user. 2. Request Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** Each user sees "You are not allowed to view venues." (HTTP 403). No bookings, blocks or available times are returned.

**TC-36-05 · Session required**
- **Traces to:** AC1 · **Type:** Negative (authentication)
- **Preconditions:** AV-SEED loaded; not logged in. Repeat with an expired token, and with a token for a user who has since been deleted.
- **Steps:** Request Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** The user is asked to log in (HTTP 401). No availability data is returned.

**TC-36-06 · No venue selected**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. Open the availability calendar without choosing a venue. 2. Select 15 Oct 2026. 3. View availability.
- **Test data:** Venue = *(none)*; Date = 2026-10-15.
- **Expected result:** A validation message asks the user to select a venue. No calendar is shown.

**TC-36-07 · Unknown venue**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`; no venue with ID 9999 exists.
- **Steps:** Request availability for venue 9999 on 15 Oct 2026.
- **Test data:** Venue ID = 9999; Date = 2026-10-15.
- **Expected result:** "Venue not found." (HTTP 404). No calendar is shown.

**TC-36-08 · End date before start date**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** Select Aurora Ballroom with From = 17 Oct 2026 and To = 15 Oct 2026, then view availability.
- **Test data:** From = 2026-10-17; To = 2026-10-15.
- **Expected result:** A validation message says the end date must be on or after the start date (HTTP 400). No calendar is shown.

**TC-36-09 · Invalid or missing dates**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** For each input, request Aurora Ballroom's availability.
- **Test data:** Date = `2026-02-30`; Date = `15/10/2026`; Date = `tomorrow`; Date = *(empty)*.
- **Expected result:** Each input is rejected with a validation message asking for a valid date (HTTP 400). No calendar is shown.

**TC-36-10 · Longest allowed date range**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q5 (**Blocked** until the customer confirms a maximum range; 31 days is a placeholder)
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** Request Aurora Ballroom's availability for each range.
- **Test data:** (a) From = To = 2026-10-15 (1 day). (b) 2026-10-01 to 2026-10-31 (31 days). (c) 2026-10-01 to 2026-11-01 (32 days).
- **Expected result:** (a) and (b) load successfully; (a) matches TC-36-01. (c) is rejected with a message stating the maximum range.

## AC2 — Bookings and blocks shown with start and end dates and times

**TC-36-11 · A period extending beyond the selected range shows its true start and end**
- **Traces to:** AC2 · **Type:** Boundary
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for Sat 17 Oct 2026 only.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-17.
- **Expected result:** K2 is listed with start **Fri 16 Oct 20:00** and end **Sat 17 Oct 12:00**; it is not cut off at midnight. 08:00–12:00 is unavailable and 12:00–23:00 is available.

**TC-36-12 · Records touching the edges of the range**
- **Traces to:** AC2, AC3 · **Type:** Boundary
- **Preconditions:** AV-SEED loaded, plus these Aurora Ballroom blocks: K4 Wed 14 Oct 22:00 – Thu 15 Oct 00:00; K5 Wed 14 Oct 23:00 – Thu 15 Oct 00:01; K6 Fri 16 Oct 00:00 – 01:00; K7 Thu 15 Oct 23:59 – Fri 16 Oct 00:30. Logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for Thu 15 Oct 2026 only.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** K4 (ends exactly at the start of the day) and K6 (starts exactly at the end of the day) are **not** listed. K5 (one minute into the day) and K7 (one minute before the day ends) **are** listed, with their full start and end dates and times.

## AC3 — Incompatible bookings and blocks are never shown as available

**TC-36-13 · Pending and cancelled bookings do not block time**
- **Traces to:** AC2, AC3 · **Type:** Negative (business rule) · **Depends on:** Q2
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** B3 (pending, 18:00–20:00) and B4 (cancelled, 20:00–21:00).
- **Expected result:** 18:00–21:00 is shown as available. Neither B3 nor B4 is listed.

**TC-36-14 · Overlapping booking and block**
- **Traces to:** AC2, AC3 · **Type:** Boundary
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** B1 (10:00–12:00) overlaps K3 (11:00–13:00).
- **Expected result:** Both B1 and K3 are listed with their own times. The whole of 10:00–13:00 is unavailable, and no part of 11:00–12:00 is listed twice or shown as available. Availability resumes at exactly 13:00.

**TC-36-15 · Back-to-back records leave no gap**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** B2 ends at 16:00; K1 starts at 16:00.
- **Expected result:** 14:00–17:00 is one continuous unavailable stretch, with no zero-length "available" slot at 16:00. 13:00–14:00 before it and 17:00 onward after it are available.

**TC-36-16 · Another venue's bookings do not affect this venue**
- **Traces to:** AC3 · **Type:** Negative
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** 1. View Civic Hall's availability for 15 Oct 2026. 2. View Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** B6 books Civic Hall 09:00–18:00.
- **Expected result:** (1) Civic Hall lists B6, and 09:00–18:00 is unavailable with no available time that day. (2) Aurora Ballroom matches TC-36-01; B6 does not appear.

**TC-36-17 · Venue with no bookings or blocks**
- **Traces to:** AC3, AC4 · **Type:** Happy path (empty state)
- **Preconditions:** AV-SEED loaded (Aurora Ballroom has nothing on Mon 19 Oct); logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for 19 Oct 2026.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-19.
- **Expected result:** 08:00–23:00 is available, and the calendar says no bookings or blocks are recorded for the period. This is not shown as an error.

## AC4 — Time outside bookings and blocks is assessed separately

**TC-36-18 · One booking does not make the whole day unavailable**
- **Traces to:** AC4 · **Type:** Happy path
- **Preconditions:** AV-SEED loaded, plus B8: Civic Hall, confirmed booking, Wed 14 Oct 12:00–13:00. Logged in as `coordinator`.
- **Steps:** View Civic Hall's availability for 14 Oct 2026.
- **Test data:** Venue = Civic Hall; Date = 2026-10-14.
- **Expected result:** 09:00–12:00 and 13:00–18:00 are available; 12:00–13:00 is unavailable (B8).

**TC-36-19 · Closed day is shown as outside operating hours, not as booked**
- **Traces to:** AC4 · **Type:** Negative (business rule) · **Depends on:** Q1
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Civic Hall's availability for Sat 17 Oct 2026.
- **Test data:** Civic Hall operating hours = Mon-Fri 09:00-18:00.
- **Expected result:** The whole day is shown as outside operating hours. No time is shown as available, and no booking or block is shown.

**TC-36-20 · Operating-hours edges**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** Q1
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Aurora Ballroom's availability for 19 Oct 2026.
- **Test data:** Aurora Ballroom operating hours = 08:00-23:00.
- **Expected result:** Available time begins at exactly 08:00 (07:59 is outside operating hours) and ends at exactly 23:00 (23:00 onward is outside operating hours).

**TC-36-21 · Venue with no recorded operating hours**
- **Traces to:** AC4, AC6 · **Type:** Negative · **Depends on:** Q4 (**Blocked** until answered)
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`.
- **Steps:** View Bayfront Pavilion's availability for 15 Oct 2026.
- **Test data:** Bayfront Pavilion operating hours = *not recorded*.
- **Expected result (proposed):** Time with no booking or block is shown as "operating hours not recorded — confirm with venue staff", not as available. Any bookings or blocks are still listed.

## AC5 — A refreshed calendar reflects saved changes

**TC-36-22 · Newly confirmed booking appears after refresh**
- **Traces to:** AC5 · **Type:** Happy path
- **Preconditions:** AV-SEED loaded; `coordinator` has Aurora Ballroom's calendar for 15 Oct 2026 open (18:00–20:00 is available).
- **Steps:** 1. As `venue_staff`, approve B3 so that it becomes a confirmed booking. 2. As `coordinator`, refresh the calendar.
- **Test data:** B3, 18:00–20:00.
- **Expected result:** B3 is listed as a confirmed booking, and 18:00–20:00 is unavailable. 17:00–18:00 and 20:00–23:00 remain available.

**TC-36-23 · Cancelled booking is freed after refresh**
- **Traces to:** AC5 · **Type:** Happy path
- **Preconditions:** As TC-36-22.
- **Steps:** 1. Cancel B2 and save. 2. Refresh the calendar.
- **Test data:** B2, 14:00–16:00.
- **Expected result:** B2 is no longer listed, and 13:00–16:00 is available. K1 (16:00–17:00) is still unavailable.

**TC-36-24 · Edited block moves after refresh**
- **Traces to:** AC5 · **Type:** Happy path
- **Preconditions:** As TC-36-22.
- **Steps:** 1. Change K1 from 16:00–17:00 to 21:00–22:00 and save. 2. Refresh the calendar.
- **Test data:** K1 new times = 21:00–22:00.
- **Expected result:** 16:00–17:00 is available, and K1 is listed at 21:00–22:00, which is unavailable.

**TC-36-25 · New block appears after refresh**
- **Traces to:** AC5 · **Type:** Happy path
- **Preconditions:** As TC-36-22.
- **Steps:** 1. Record a new block, K8 "Fire drill", on Aurora Ballroom from 08:00 to 09:00, and save. 2. Refresh the calendar.
- **Test data:** K8, 08:00–09:00.
- **Expected result:** K8 is listed with its times. 08:00–09:00 is unavailable; 09:00–10:00 is still available.

**TC-36-26 · A change that fails to save is not shown**
- **Traces to:** AC5 · **Type:** Negative
- **Preconditions:** As TC-36-22.
- **Steps:** 1. Try to change K1 to end before it starts (start 17:00, end 16:00). 2. Confirm the save is rejected. 3. Refresh the calendar.
- **Test data:** K1 start = 17:00; end = 16:00.
- **Expected result:** The save is rejected with a validation message. After refresh, K1 is still 16:00–17:00 and the calendar matches TC-36-01.

## AC6 — Load failures are shown as errors, never as availability

**TC-36-27 · Database unavailable when loading**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** AV-SEED loaded; logged in as `coordinator`; the database is made to fail on the availability query (in automated tests, force an `OperationalError`, as `test_venue_details.py` does).
- **Steps:** View Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** An error says availability could not be loaded and offers a retry (HTTP 503, `retryable: true`). No time is shown as available, and no empty calendar or "no bookings recorded" message appears.

**TC-36-28 · Partial failure is treated as a full failure**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** As TC-36-27, but only the query for recorded blocks fails; bookings load normally.
- **Steps:** View Aurora Ballroom's availability for 15 Oct 2026.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** The same error as TC-36-27. The calendar does not show bookings alone with 11:00–13:00 or 16:00–17:00 wrongly shown as available.

**TC-36-29 · Retry succeeds after recovery**
- **Traces to:** AC6 · **Type:** Happy path (recovery)
- **Preconditions:** TC-36-27 has just produced the error; the database is then restored.
- **Steps:** Click Retry.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** The calendar loads and matches TC-36-01.

**TC-36-30 · Refresh fails after a successful load**
- **Traces to:** AC5, AC6 · **Type:** Negative (failure)
- **Preconditions:** `coordinator` has Aurora Ballroom's calendar for 15 Oct 2026 loaded successfully; the database is then made to fail.
- **Steps:** Refresh the calendar.
- **Test data:** Venue = Aurora Ballroom; Date = 2026-10-15.
- **Expected result:** The error from TC-36-27 is shown. The previously loaded calendar is not presented as current.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10 |
| AC2 | 01, 03, 11, 12, 13, 14 |
| AC3 | 01, 12, 13, 14, 15, 16, 17 |
| AC4 | 01, 17, 18, 19, 20, 21 |
| AC5 | 22, 23, 24, 25, 26, 30 |
| AC6 | 21, 27, 28, 29, 30 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 03, 17, 18, 22, 23, 24, 25, 29 |
| Negative | 04, 05, 06, 07, 08, 09, 13, 16, 19, 21, 26, 27, 28, 30 |
| Boundary | 10, 11, 12, 14, 15, 20 |
| Cross-cutting (authorisation) | 02, 04, 05 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | What are "the agreed scheduling rules"? Is it only the venue's operating hours, or also turnaround gaps between bookings, a minimum bookable slot, or public holidays? | A3, TC-36-01, 17–20 |
| Q2 | Is "incompatible" any time overlap? Should pending booking requests be shown (e.g. as tentative), or ignored as assumed here? | A2, TC-36-13, 22 |
| Q3 | Which roles count as "authorised internal users"? Should technical support staff see venue availability? | A1, TC-36-02, 04 |
| Q4 | How should free time be shown for a venue with no recorded operating hours? | TC-36-21 |
| Q5 | Is there a maximum date range the calendar should accept? | TC-36-10 |
| Q6 | How should a venue marked as not currently bookable (e.g. Dockside Studio, `is_available = false`) appear? As a block covering the whole period, or with a banner? | New case needed once answered |
