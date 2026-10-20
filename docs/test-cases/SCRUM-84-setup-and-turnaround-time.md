# SCRUM-84 — Setup and turnaround time in availability and conflict checks: Test Cases

**User story:** Venues need time to be set up before an event and cleared after it, so availability, venue search and conflict checks should treat that time as occupied.

**Created:** 20 Oct 2026 · **Source of the cases:** the "Sprint 3 test cases" tab of the ConnectSphere Backlog to Feature Map sheet (IS212-US84-TC1 to TC12) · **Automated tests:** `backend/tests/test_venue_setup_turnaround.py`, `frontend/src/pages/VenueSetupTurnaround.test.jsx` · **Status:** automated cases pass locally (20 Oct 2026); browser walk-through still to be done by hand · **Related:** SCRUM-36/64 (calendar), SCRUM-37 (search), SCRUM-39 (request), SCRUM-40/41 (approval, conflicts), SCRUM-87 (holds)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | A booking occupies its start time minus setup, to its end time plus turnaround. A 10:00 to 12:00 event with 30 minutes setup and 45 minutes turnaround occupies 09:30 to 12:45. |
| AC2 | The availability calendar, venue search and the conflict check all use the occupied period. A booking that starts exactly when another occupied period ends is allowed. |
| AC3 | A conflict message shows the occupied period and which part is setup or turnaround. |
| AC4 | When Venue Staff review a booking request, they see the occupied period including setup and turnaround, and decide whether to approve it. |

## Working assumptions (to confirm)

- **A1 — Where setup and turnaround live:** on the booking (`VenueBooking.setup_minutes`, `turnaround_minutes`, whole minutes 0–1440, default 0). The database works out `occupied_start` and `occupied_end` (generated columns), so the "no overlapping confirmed bookings" rule can use them. **The Event table is not changed**, so SCRUM-52/53's editable/restricted field lists are untouched.
- **A2 — Who enters them:** the coordinator, as two optional fields on the venue request form (blank means 0). The sheet's data says the event "has" setup 30 / turnaround 45; this story stores them on the request instead. **Open question:** should they belong to the event or the venue (e.g. a default per venue)? Moving them later only changes where the request form gets its defaults.
- **A3 — What uses the occupied period:** the calendar (periods and slots), venue search, the approval and hold conflict checks, and the database rule. Blocks have no setup/turnaround. A hold uses its booking's occupied period. The event's own times are unchanged everywhere else (hold expiry must still be no later than the event start).
- **A4 — API shape:** a booking or hold period/conflict has `start`/`end` = the occupied period; when it has setup or turnaround it also has `event_start`, `event_end`, `setup`, `turnaround` (each `{start, end, minutes}`). With neither, the entry is exactly as before.
- **A5 — Conflict at request time (changes SCRUM-39):** the sheet (TC6–TC10) blocks a request whose occupied period clashes with a confirmed booking, block or unexpired hold, with `409 reason: "conflict"`, the conflicts, and the request's own `occupied` period. SCRUM-39 previously accepted such requests (TC-39-22, Q4/Q7 in its doc). **This needs the team's agreement**; the SCRUM-39 test was updated to match. Reverting means deleting the conflict check in `request_booking`.
- **A6 — Past midnight:** a turnaround running past midnight extends into the next day; the next day's calendar shows it from 00:00. Operating hours are not enforced on setup/turnaround.
- **A7 — The conflict message** also shows the new request's own occupied period (the sheet's open question on TC10).

## Test cases

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC1 | `test_tc1_occupied_period_includes_setup_and_turnaround` | 09:30–12:45 with setup/turnaround labelled |
| TC2 | `test_tc2_without_setup_or_turnaround_it_equals_the_event_time` (+ defaults) | No setup/turnaround: occupied = event time |
| TC3 | `test_tc3_turnaround_past_midnight_runs_into_the_next_day` | 22:00 to 00:15 next day; next day's calendar from 00:00 |
| TC4 | `test_tc4_calendar_shows_the_venue_occupied_for_the_whole_period`; frontend | 09:29 and 12:45 free, 09:30–12:44 occupied |
| TC5 | `test_tc5_search_treats_the_turnaround_as_unavailable` | 12:15–14:00 search: V-101 out, V-102 in |
| TC6 | `test_tc6_conflict_when_only_setup_and_turnaround_overlap`; frontend | Events don't overlap, occupied periods do: refused |
| TC7 | `test_tc7_starting_exactly_when_another_ends_is_allowed` | 12:45 start allowed (half-open) |
| TC8 | `test_tc8_one_minute_earlier_is_a_conflict` | 12:44 start refused |
| TC9 | `test_tc9_same_time_at_another_venue_is_not_a_conflict` | Other venue allowed |
| TC10 | `test_tc10_message_gives_the_occupied_period_and_labels_the_parts`; frontend | Occupied 09:30–12:45, setup 09:30–10:00, turnaround 12:00–12:45 |
| TC11 | `test_tc11_venue_staff_see_the_occupied_period_when_reviewing`; frontend | Review list has event time, occupied period, minutes |
| TC12 | `test_tc12_approving_confirms_the_booking_and_the_calendar_shows_it` | Approve, then calendar shows 09:30–12:45 |

Extra cases: minutes validation (negative, > 1440, 2.5, text, true, list) and edge values; pending bookings don't block; holds occupy their setup/turnaround; approval refused and review list flagging a conflict that exists only in the occupied periods; touching occupied periods are not a conflict; the database itself refuses overlapping occupied periods.

## Before merging

Run `backend/db/venue_setup_turnaround.sql` in the Supabase SQL editor as the project owner. It adds the columns, replaces the no-overlap constraint, and is safe to re-run. The CI `supabase-schema` job fails until it has been run. If SCRUM-63 is merged first, its script is independent.
