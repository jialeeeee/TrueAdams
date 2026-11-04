# SCRUM-99 — Coordinator is reminded about incomplete arrangements: Test Cases

**User story:** As an Event Coordinator, I want to be reminded about my approved events that still have incomplete arrangements so that nothing is left unfinished before the event.

**Created:** 4 Nov 2026 · **Status of all cases:** automated cases pass (4 Nov 2026, local PostgreSQL as in CI) · **Automated tests:** `backend/tests/test_incomplete_arrangement_reminders.py` · **Background job:** `tasks.remind_incomplete_arrangements` (Celery beat `remind-incomplete-arrangements`), in `backend/app/events/reminders.py` · **Related:** SCRUM-93 (confirmation's checks, reused), SCRUM-86 (the hold expiry job, the same pattern), CF20

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | A scheduled job checks every approved event for a missing arrangement: confirmed venue bookings covering the whole event period, full equipment reservations, or an approved safety check. |
| AC2 | For each event with something missing, its assigned coordinator receives one reminder per run that names the event and lists what is missing. |
| AC3 | An event with nothing missing produces no reminder. |
| AC4 | Reminders stop once the event is confirmed, cancelled or rejected. |
| AC5 | How often the job runs is a configuration setting, every 24 hours by default. |
| AC6 | Reminders go only to the event's assigned coordinator. |
| AC7 | If the reminder email cannot be queued, the in-app reminder is still recorded and the failure is logged. |

## Working assumptions (to confirm)

- **A1 — The checks are confirmation's (AC1):** the job lists what `POST /api/events/<id>/confirm` would list as missing (SCRUM-93 AC2, `_missing_for_confirmation`), in its order and words: "Confirmed venue booking" (or "Replacement for an unavailable venue", SCRUM-88 A11), "Reserved equipment", "Approved safety check". If confirmation gains a check, the reminders do too. An event whose equipment note is empty or "None" needs no equipment (SCRUM-90 A1).
- **A2 — Which events (AC1, AC4):** status `approved`, with a coordinator, and not started yet (no start recorded, or a start after now, Singapore time). The story is about finishing arrangements *before* the event, so an event that has started gets no more reminders. Confirmed, cancelled, rejected and earlier statuses get none. *(Q1)*
- **A3 — Who (AC6):** the event's current coordinator: the assigned user while they hold the `coordinator` role, as main or additional role (CF01). Nobody else is told, and an event without one is skipped.
- **A4 — The reminder (AC2):** one in-app notification per event per run, kind `arrangements_incomplete`, linked to the event: `Reminder: "<title>" (<start>, Singapore time) is approved but can't be confirmed yet. Still missing: <list>.` ("date not recorded" when there is no start), then an email with the same text. Reminders are not deduplicated across runs: each run reminds again until the event is ready, which is the point of a reminder. *(Q2)*
- **A5 — How often (AC5):** `REMINDER_INTERVAL_HOURS` in `backend/.env` (any positive number of hours, fractions allowed), 24 when unset or blank. A value that isn't a positive number stops the app starting, so a typo can't silently change the frequency. Release 1 has no administrator role, so whoever deploys the system sets it (story conversation).
- **A6 — Failures (AC7):** the reminders of one run are saved in one commit; emails are queued afterwards. If an email can't be queued, the in-app reminder stays, the failure is logged and the other emails are still tried. If the run itself fails to save, nothing is saved, the failure is logged, and the next run tries again.

## Seed data (RM-SEED)

Each test creates its own rows: an organiser, coordinators **alice** and **ben**, a Safety Officer, venue **Hall A**, and events "Harbour Talk" (approved, alice, 2027-06-10 10:00–12:00, equipment note "Two microphones") as each case needs. "Ready" means a confirmed Hall A booking covering the event, equipment note "None" and an approved safety check. "Now" is 2027-05-01 09:00.

## Test cases

| ID | Traces to | What it checks | Automated |
|----|-----------|----------------|-----------|
| TC-99-01 | AC1, AC2 | Nothing arranged: one reminder to alice naming the event and listing all three; emailed | `test_tc_99_01_the_coordinator_is_told_everything_still_missing` |
| TC-99-02 | AC1, AC2 | Only the safety check missing: only that is listed | `test_tc_99_02_only_what_is_missing_is_listed` |
| TC-99-03 | AC2 | Two runs, two events: one reminder per event per run, each to its own coordinator | `test_tc_99_03_each_run_sends_one_reminder_per_event` |
| TC-99-04 | AC2 | No start recorded: still reminded, "date not recorded" | `test_tc_99_04_an_event_without_a_date_is_still_reminded` |
| TC-99-05 | AC3 | Ready event: no reminder, no email | `test_tc_99_05_an_event_with_nothing_missing_gets_no_reminder` |
| TC-99-06 | AC4 | Confirmed, cancelled, rejected, draft, submitted, under review: none | `test_tc_99_06_confirmed_cancelled_rejected_and_unapproved_events_get_none` |
| TC-99-07 | A2 | Starting at now: none; starting a minute later: reminded | `test_tc_99_07_an_event_that_has_started_gets_none` |
| TC-99-08 | AC6 | Only alice; not ben, the organiser or the Safety Officer | `test_tc_99_08_only_the_events_coordinator_is_reminded` |
| TC-99-09 | AC6, A3 | No coordinator, or one who lost the role: none; the role as an additional role: reminded | `test_tc_99_09_no_coordinator_or_one_without_the_role_gets_none`, `test_tc_99_09_a_coordinator_as_an_additional_role_is_reminded` |
| TC-99-10 | AC7 | Queue down: both reminders saved, both emails tried, both failures logged | `test_tc_99_10_a_queue_outage_keeps_the_reminders_and_is_logged` |
| TC-99-11 | AC7, A6 | Saving fails: nothing saved, no email, logged; the next run works | `test_tc_99_11_a_failed_run_saves_nothing_and_is_logged` |
| TC-99-12 | AC5 | Celery beat runs the task every 86,400 s by default | `test_tc_99_12_the_job_runs_every_24_hours_by_default` |
| TC-99-13 | AC5, A5 | The setting: unset or blank is 24; 12 and 0.5 are taken; 0, -3, "daily", nan, inf refused; the schedule follows it | `test_tc_99_13_the_frequency_is_a_setting`, `test_tc_99_13_the_schedule_follows_the_setting` |

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02 |
| AC2 | 01, 02, 03, 04 |
| AC3 | 05 |
| AC4 | 06, 07 |
| AC5 | 12, 13 |
| AC6 | 08, 09 |
| AC7 | 10, 11 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should a coordinator still be reminded about an approved event once it has started (as built: no)? | A2, TC-99-07 |
| Q2 | Should a reminder be sent only when something has changed since the last one, rather than every run (as built: every run, as AC2 says)? | A4, TC-99-03 |
