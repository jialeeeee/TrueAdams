# SCRUM-84 — Setup and turnaround time in availability and conflict checks: Test Cases

> **Latest execution (5 Nov 2026):** every automated case in this document passes: the full backend suite on a PostgreSQL database built by `backend/ci/build_test_database.py` (1,496 tests, 100% of statements and branches), the full frontend suite with Vitest (100% coverage), and CI. The main journey of every role is also covered end to end by `e2e/test_journeys.py` (CI job `e2e`); browser checks this document names for individual screens remain manual. Execution notes further down record earlier runs and are kept as history; where they say a case was not run, pending or blocked, this line is the current status.

**User story:** Venues need time to be set up before an event and cleared after it, so availability, venue search and conflict checks should treat that time as occupied.

**Created:** 20 Oct 2026 · **Reopened:** 23 Oct 2026 (AC1 changed, AC5 added) · **Source of the cases:** the "Sprint 3 test cases" tab (IS212-US84-TC1 to TC12) and the "Sprint 4 test cases" tab (IS212-US84-TC13 to TC26) of the ConnectSphere Backlog to Feature Map sheet · **Automated tests:** `backend/tests/test_venue_setup_turnaround.py`, `frontend/src/pages/VenueSetupTurnaround.test.jsx`, `frontend/src/pages/FlaggedBookingsPage.test.jsx` · **Status:** automated cases pass locally; browser walk-through still to be done by hand · **Related:** SCRUM-63 AC9 (the venue's setup and turnaround time), SCRUM-36/64 (calendar), SCRUM-37 (search), SCRUM-39 (request), SCRUM-40/41 (approval, conflicts), SCRUM-87 (holds)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | A booking occupies its start time minus the **venue's** setup time, to its end time plus the **venue's** turnaround time. A 10:00 to 12:00 event at a venue with 30 minutes setup and 45 minutes turnaround occupies 09:30 to 12:45. (Reopened: it used to be the booking's own setup and turnaround.) |
| AC2 | The availability calendar, venue search and the conflict check all use the occupied period. A booking that starts exactly when another occupied period ends is allowed. |
| AC3 | A conflict message shows the occupied period and which part is setup or turnaround. |
| AC4 | When Venue Staff review a booking request, they see the occupied period including setup and turnaround, and decide whether to approve it. |
| AC5 | When a venue's setup or turnaround time is changed, every pending, tentative or confirmed booking whose occupied period now overlaps another is flagged "Setup or turnaround conflict" and listed for Venue Staff. No booking is cancelled or changed. (New in the reopen.) |

## Working assumptions (to confirm)

- **A1 — Where setup and turnaround live (changed in the reopen):** on the venue (`Venue.setup_minutes`, `turnaround_minutes`, SCRUM-63 AC9; NULL means none set and counts as 0). A booking stores none of its own, so its occupied period is worked out whenever it is read and changes when the venue's values change (TC16). The old `venue_bookings.setup_minutes`/`turnaround_minutes` columns are no longer read or written (the SQL script leaves them in place, defaulting to 0, so no data is dropped). **The Event table is not changed.**
- **A2 — Who enters them:** Venue Staff, on the venue form (SCRUM-63 AC9). The coordinator's request form no longer asks for them, and a request that sends them is refused (400, "not part of a venue request"). **This changes the SCRUM-39/84 request contract** — the team should agree.
- **A3 — What uses the occupied period:** the calendar (periods and slots), venue search, the approval and hold conflict checks and the request-time check. Blocks have no setup/turnaround. A hold uses its venue's values. The event's own times are unchanged everywhere else (hold expiry must still be no later than the event start).
- **A4 — API shape:** a booking or hold period/conflict has `start`/`end` = the occupied period; when the venue has setup or turnaround it also has `event_start`, `event_end`, `setup`, `turnaround` (each `{start, end, minutes}`). With neither, the entry is exactly as before.
- **A5 — Conflict at request time (changes SCRUM-39):** a request whose occupied period clashes with a confirmed booking, block or unexpired hold is refused with `409 reason: "conflict"`, the conflicts, and the request's own `occupied` period. Reverting means deleting the conflict check in `request_booking`.
- **A6 — Past midnight:** a turnaround running past midnight extends into the next day; the next day's calendar shows it from 00:00. Operating hours are not enforced on setup/turnaround.
- **A7 — The conflict message** also shows the new request's own occupied period.
- **A8 — The database no longer enforces occupied periods (reopen):** AC5 allows a venue change to leave bookings overlapping, and a database rule cannot read the venue's values, so the "no overlapping confirmed bookings" constraint compares the event times again. The occupied-period check is made in the application at request and approval time.
- **A9 — What AC5 flags:** after a change to a venue's setup or turnaround, the venue's pending, tentative (unexpired) and confirmed bookings whose occupied periods overlap another such booking's occupied period **while their event times do not overlap** (an overlap that exists without the setup and turnaround is not a setup or turnaround conflict). Occupied periods that only touch are not flagged. The flags are recomputed from scratch for that venue on every change of setup or turnaround, so a flag disappears once the overlap does or the booking is decided/cancelled/expired. Blocks are not counted.
- **A10 — Where the flags live:** a new table `venue_booking_flags` (one row per flagged booking), so the booking row itself is never touched. Venue Staff list them at `GET /api/venues/flagged-bookings` (optional `venue_id`). The venue save and the flag refresh happen in one transaction.
- **A11 — Not sent:** no notification is sent when a booking is flagged (the criterion only asks for the flag and the list).

## Test cases

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC1 · TC13 | `test_tc13_occupied_period_uses_the_setup_and_turnaround_set_on_the_venue` (+ booking reports it) | V-101 (30/45): 09:30–12:45 with setup/turnaround labelled |
| TC2 · TC14 | `test_tc14_a_venue_with_none_set_occupies_only_the_event_time` (+ zero values) | V-102 none set: occupied = event time |
| TC15 | `test_tc15_two_venues_give_different_occupied_periods_for_the_same_event_time` | Same event time, different venues, different periods |
| TC16 | `test_tc16_changing_the_venues_turnaround_changes_an_existing_bookings_period` | Venue edit changes an existing booking's period |
| TC3 | `test_tc3_turnaround_past_midnight_runs_into_the_next_day` | 22:00 to 00:15 next day; next day's calendar from 00:00 |
| TC4 | `test_tc4_calendar_shows_the_venue_occupied_for_the_whole_period`; frontend | 09:29 and 12:45 free, 09:30–12:44 occupied |
| TC5 | `test_tc5_search_treats_the_turnaround_as_unavailable` | 12:15–14:00 search: V-101 out, V-102 in |
| TC6 | `test_tc6_conflict_when_only_setup_and_turnaround_overlap`; frontend | Events don't overlap, occupied periods do: refused |
| TC7 | `test_tc7_starting_exactly_when_another_ends_is_allowed` | 13:15 start (12:45 occupied) allowed (half-open) |
| TC8 | `test_tc8_one_minute_earlier_is_a_conflict` | One minute earlier refused |
| TC9 | `test_tc9_same_time_at_another_venue_is_not_a_conflict` | Other venue allowed |
| TC10 | `test_tc10_message_gives_the_occupied_period_and_labels_the_parts`; frontend | Occupied 09:30–12:45, setup 09:30–10:00, turnaround 12:00–12:45 |
| TC11 | `test_tc11_venue_staff_see_the_occupied_period_when_reviewing`; frontend | Review list has event time, occupied period, minutes |
| TC12 | `test_tc12_approving_confirms_the_booking_and_the_calendar_shows_it` | Approve, then calendar shows 09:30–12:45 |
| TC17 | `test_tc17_raising_the_turnaround_so_two_bookings_overlap_flags_both` | V-101 15/15, turnaround to 60: B-501 and B-502 flagged |
| TC18 | `test_tc18_flagged_bookings_are_listed_for_venue_staff`; `FlaggedBookingsPage.test.jsx` | The list shows the flag, booking, occupied period and what it overlaps |
| TC19 | `test_tc19_a_change_that_creates_no_overlap_flags_nothing` | Turnaround to 30: nothing flagged |
| TC20 | `test_tc20_occupied_periods_that_only_touch_are_not_flagged` | Turnaround to 45 (touching at 12:45): nothing |
| TC21 | `test_tc21_occupied_periods_that_overlap_by_one_minute_are_flagged` | Turnaround to 46: both flagged |
| TC22 | `test_tc22_raising_the_setup_so_two_bookings_overlap_flags_both` | Setup raised: both flagged |
| TC23 | `test_tc23_pending_and_tentative_bookings_are_flagged_as_well` | Pending and tentative bookings flagged |
| TC24 | `test_tc24_a_cancelled_booking_is_not_flagged` | Cancelled B-502: nothing flagged |
| TC25 | `test_tc25_no_booking_is_cancelled_or_changed_by_the_flag` | Status, times, venue, event unchanged |
| TC26 | `test_tc26_bookings_at_other_venues_are_not_flagged` | V-102 bookings not flagged; `venue_id` filter |

Extra cases: a request can no longer send setup or turnaround minutes; pending bookings don't block; holds occupy the venue's setup/turnaround; approval refused and the review list flagging a conflict that exists only in the occupied periods; touching occupied periods are not a conflict. For AC5: an edit that leaves setup and turnaround alone flags nothing; a later change that removes the overlap clears the flags; bookings whose events themselves overlap are not a setup conflict; an expired hold is not flagged; the venue save fails (503) without flagging when the flags cannot be saved; only Venue Staff can list flagged bookings (401/403); the list reports 503 when it cannot be read; a bad `venue_id` filter is refused (400).

## Before merging

Run `backend/db/venue_setup_turnaround_venue_level.sql` in the Supabase SQL editor as the project owner (after `venue_setup_turnaround.sql` and SCRUM-63's `venue_setup_turnaround_minutes.sql`). It drops the booking-level occupied columns and the occupied-period constraint, restores the event-time constraint, and adds the `venue_booking_flags` table with row-level security. It is safe to re-run. The CI `supabase-schema` job fails until it has been run. SCRUM-63's AC9 script must be run first, because the flags are worked out from the venue's values.
