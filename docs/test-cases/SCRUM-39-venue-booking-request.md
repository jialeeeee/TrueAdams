# SCRUM-39 — Submit a Venue Booking Request: Test Cases

**User story:** As an Event Coordinator, I want to request a venue for an event so that Venue Staff can assess the proposed booking.

**Created:** 14 Oct 2026 · **Status of all cases:** Automated cases pass (14 Oct 2026, local PostgreSQL with db/venue_booking_requests.sql applied + Vitest); frontend cases 11, 15, 19, 20 and 28 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_venue_booking_request.py`, `frontend/src/pages/VenueBookingRequestPage.test.jsx`, `frontend/src/pages/VenueBookingRequestsPage.test.jsx`

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can select an event they are authorised to coordinate and the venue being requested. |
| AC2 | The request includes the event reference, requested date and start/end times, and relevant venue requirements. |
| AC3 | Missing or invalid required information prevents submission and is identified for correction. |
| AC4 | Successful submission saves the request against the event and venue with status Pending, displays confirmation, and makes it visible to authorised Venue Staff. |
| AC5 | Submitting a request does not itself confirm the venue booking. |
| AC6 | If submission fails, the coordinator is informed, no successful request is reported, and entered information remains available for retry. |

## Working assumptions

These are the team's current reading of the story, agreed with the scrum lead on 14 Oct 2026. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may request:** only the event's current coordinator (`Event.coordinator_id`, role `coordinator`), checked against the database on every request, as in SCRUM-31/32/34. *(Q1)*
- **A2 — Which events:** only `approved` events, since only feasible events proceed to further planning (SCRUM-32). Drafts and submitted, rejected or cancelled events are refused. *(Q2)*
- **A3 — Times:** the requested start and end are prefilled from the event's proposed times, and the coordinator may change them, for example to add setup or teardown time. They are Singapore time without a time zone, like the event's own times. The end must be after the start, and the start must not be in the past. *(Q3, Q5)*
- **A4 — Venue requirements:** required. They are prefilled from the event's venue requirements and may be edited. Text is trimmed, and is at most 5,000 characters (the editing limit from SCRUM-53).
- **A5 — Conflicts and suitability are not checked here:** a request is accepted even if the period overlaps a confirmed booking or a block, falls outside the venue's operating hours, or the event is larger than the venue's capacity, and even for a venue marked as not currently bookable. Venue Staff decide (venue booking approval). Conflict detection and suitability checking are separate core features. *(Q4, Q7)*
- **A6 — One pending request per event:** an event can have at most one `pending` venue request, for any venue. A new request is allowed once the earlier one is no longer pending (for example rejected). The database enforces this with a unique index, so two simultaneous submissions cannot both succeed. *(Q6)* **Replaced by [SCRUM-85](SCRUM-85-several-venues-for-one-event.md) A1–A2** (Week 7 customer change 3): an event can have several pending requests, one per venue and time; the index was dropped (`db/several_venues_per_event.sql`).
- **A7 — Not a confirmed booking:** a request is saved with status `pending`. It does not set the event's venue, and it does not block the venue's time: availability (SCRUM-36) and search (SCRUM-37) count only `confirmed` bookings.
- **A8 — Venue Staff:** every user with the role `venue_staff` can see every pending request, since venues are not yet assigned to staff. They are not notified; they see the requests in their list. *(Q8)*
- **A9 — All problems at once:** every missing or invalid field is reported together under `fields`, so the coordinator can correct them in one go.
- **A10 — Order of checks:**
  1. not logged in (401);
  2. not a coordinator (403);
  3. missing or malformed event reference (400);
  4. unknown event (404);
  5. not this event's coordinator (403);
  6. missing or invalid details, including the venue reference, all reported together (400);
  7. unknown venue (404);
  8. event not approved (409);
  9. a request already pending (409).

  This follows the team's convention (401, then 404/403, then 400, then 409), with one deviation: the venue is looked up after the field check, so that A9 can report every problem at once.

## Endpoints under test

- **`POST /api/venues/bookings`**
  - Body: `{"event_id", "venue_id", "start_time": "YYYY-MM-DDTHH:MM", "end_time", "venue_requirements"}`.
  - **201** `{"message", "booking": booking}`.
  - **400** `{"error", "fields": {field: problem}}`.
  - **503** `{"error", "retryable": true}` if saving fails.
- **`GET /api/venues/bookings`** → **200** `{"bookings": [booking, ...], "message": str | null}`.
  - Lists the pending requests, oldest first, for Venue Staff.
  - `message` holds the empty-state text.
- **A booking** is `{"id", "status", "event": {"id", "title", "expected_attendance"}, "venue": {"id", "name", "location"}, "start_time", "end_time", "venue_requirements", "requested_by": {"id", "email"}, "requested_at"}`.

## Seed data (VB-SEED)

Reset the database to this data before **every** test case.
- Users and venues come from `backend/tests/seed_data.py`: alice, ben, chloe (coordinators), dana and evan (organisers), gus (venue staff), hana (tech staff), farah (attendee) and admin; Aurora Ballroom and Civic Hall, among others.
- The events below are created in the test file.

| Ref | Event | Organiser | Coordinator | Status | Proposed time | Venue requirements |
|-----|-------|-----------|-------------|--------|---------------|--------------------|
| E1 | Harbour Lights Festival | dana | alice | approved | 12 Mar 2027 17:00–22:00 | "Open-air waterfront space for 250" (attendance 250) |
| E2 | Winter Networking Night | dana | ben | approved | 3 Apr 2027 18:00–21:00 | "Theatre layout for 80" |
| E3 | Spring Garden Party | dana | alice | submitted | 20 Mar 2027 15:00–18:00 | |
| E4 | Tech Summit Draft | dana | alice | draft | — | |
| E5 | Rooftop Cinema | dana | alice | rejected | 5 Mar 2027 19:00–22:00 | |
| E6 | Cancelled Meetup | dana | alice | cancelled | 6 Mar 2027 19:00–21:00 | |

A **valid request** for E1 is: Aurora Ballroom, 12 Mar 2027 16:00–22:30 (setup and teardown added), requirements "Open-air waterfront space for 250, stage power".

---

## AC1 — Select an event you coordinate and a venue

**TC-39-01 · Coordinator requests a venue for an approved event**
- **Traces to:** AC1, AC2, AC4 · **Type:** Happy path
- **Steps:** As `alice`, submit the valid request for E1.
- **Expected result:** HTTP 201. One booking request is saved:
  - status `pending`, with E1, Aurora Ballroom, 2027-03-12 16:00–22:30 and the requirements;
  - `requested_by` alice, and a request time between just before and just after the call.

  The confirmation message names the venue and the event, and says the request is pending Venue Staff's decision.

**TC-39-02 · A coordinator who does not coordinate the event is refused**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Submit the valid request for E1 as `ben` (E2's coordinator) and as `chloe` (coordinates nothing).
- **Expected result:** HTTP 403. Nothing is saved, and E1's title and requirements do not appear in the response.

**TC-39-03 · Other roles are refused**
- **Traces to:** AC1 · **Type:** Negative (authorisation)
- **Steps:** Submit the valid request for E1 as dana (its organiser), gus, hana, farah and admin.
- **Expected result:** HTTP 403 for each. Nothing is saved.

**TC-39-04 · A valid session is required**
- **Traces to:** AC1 · **Type:** Negative (authentication)
- **Steps:** Submit the valid request, and list requests, with no token, an expired token, and a deleted user's token.
- **Expected result:** HTTP 401 each time. Nothing is saved.

**TC-39-05 · Unknown event or venue**
- **Traces to:** AC1, AC3 · **Type:** Negative
- **Steps:** As `alice`, submit the valid request with an event ID that does not exist, then with a venue ID that does not exist.
- **Expected result:** HTTP 404 ("Event not found." / "Venue not found."). Nothing is saved.

**TC-39-06 · Only approved events can have a venue requested**
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** Q2
- **Steps:** As `alice`, submit an otherwise valid request for E3 (submitted), E4 (draft), E5 (rejected) and E6 (cancelled).
- **Expected result:** HTTP 409 naming the event's status. Nothing is saved.

**TC-39-07 · Access follows reassignment and role changes**
- **Traces to:** AC1 · **Type:** Boundary (authorisation)
- **Steps:**
  1. Reassign E1 to ben, then submit with alice's earlier token.
  2. Change ben's role to organiser, then submit with ben's earlier token.
- **Expected result:** HTTP 403 both times. Nothing is saved.

## AC2 — What the request contains

**TC-39-08 · The request records the event, venue, times and requirements**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** Submit the valid request, then read the saved request and the response.
- **Expected result:**
  - The saved row references E1 and Aurora Ballroom and has the requested times and requirements.
  - The response's `booking` gives the event (ID, title, expected attendance), the venue (ID, name, location), the times as `2027-03-12T16:00:00` and `2027-03-12T22:30:00`, the requirements, and the requester.

**TC-39-09 · Requested times may differ from the event's proposed times**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** Q3
- **Steps:** Submit the valid request (it starts an hour before E1 and ends 30 minutes after).
- **Expected result:** HTTP 201 with the requested times saved as sent. E1's own start and end are unchanged.

**TC-39-10 · Requirements are trimmed**
- **Traces to:** AC2 · **Type:** Boundary
- **Test data:** requirements = `"  Stage power and a loading bay \n"`.
- **Expected result:** Saved as "Stage power and a loading bay".

**TC-39-11 · Coordinator page prefills from the event**
- **Traces to:** AC1, AC2 · **Type:** Happy path (frontend)
- **Expected result:**
  - The page loads the event's planning information and the venue list.
  - Start and end are prefilled with the event's times, and requirements with its venue requirements.
  - All three can be edited, and the venue is chosen from the list.

## AC3 — Missing or invalid information prevents submission

**TC-39-12 · Missing required information is identified**
- **Traces to:** AC3 · **Type:** Negative
- **Steps:** Submit a request with only the event ID. Then submit with each required field missing in turn: venue, start, end, requirements. Then submit with requirements `""` and `"   "`.
- **Expected result:** HTTP 400. `fields` names every missing field with a message saying what to enter (all of them together for the first request). Nothing is saved.

**TC-39-13 · Invalid values are identified**
- **Traces to:** AC3 · **Type:** Negative / boundary
- **Test data:**
  - start = `"tomorrow"`, `"12/03/2027 16:00"`, `"2027-02-30T10:00"`;
  - end equal to start; end one minute before start;
  - start in the past;
  - requirements = 42, or 5,001 characters;
  - event ID or venue ID = `"7"`, `true`, `1.5`;
  - a field that does not exist (`"budget"`);
  - a body that is not JSON.
- **Expected result:** HTTP 400 naming the field where there is one (the end time for order problems). Nothing is saved.

**TC-39-14 · Boundary values that are accepted**
- **Traces to:** AC3 · **Type:** Boundary
- **Test data:** end exactly one minute after start; requirements of exactly 5,000 characters.
- **Expected result:** HTTP 201 for each. They use separate approved events, since one event can have only one pending request.

**TC-39-15 · Frontend identifies missing information without sending**
- **Traces to:** AC3, AC6 · **Type:** Negative (frontend)
- **Steps:**
  1. Clear the requirements and choose no venue, then click Submit request.
  2. Separately, have the server return 400 with `fields`.
- **Expected result:**
  1. Each missing field is named next to its input and no request is sent.
  2. Each problem is shown next to its field. The inputs keep their values.

## AC4 — Saved as Pending, confirmed, and visible to Venue Staff

**TC-39-16 · Saved against the event and venue as Pending**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** Submit the valid request, then reload it and E1.
- **Expected result:** The row is linked to E1 and Aurora Ballroom with status `pending`. E1 is still `approved`.

**TC-39-17 · Venue Staff see pending requests**
- **Traces to:** AC4 · **Type:** Happy path · **Depends on:** Q8
- **Preconditions:** alice has requested Aurora for E1, then ben has requested Civic Hall for E2. A rejected and a confirmed booking also exist for other events.
- **Steps:** As `gus`, list venue booking requests.
- **Expected result:**
  - Both pending requests appear, oldest first, each with the event (title, expected attendance), venue, times, requirements, requester and request time.
  - The rejected and confirmed bookings are not listed.

**TC-39-18 · Only Venue Staff can list requests; empty state**
- **Traces to:** AC4 · **Type:** Negative / empty state
- **Expected result:**
  - alice, dana, hana, farah and admin get HTTP 403.
  - With no pending requests among the seeded ones, gus's list has none of them, and with none at all, the message says there are no pending venue requests.

**TC-39-19 · Frontend confirms the submission**
- **Traces to:** AC4 · **Type:** Happy path (frontend)
- **Expected result:**
  - After a successful submission, a confirmation shows the server's message and a summary: venue, times and status Pending.
  - The submit button is no longer offered for that request.

**TC-39-20 · Venue Staff page lists pending requests**
- **Traces to:** AC4 · **Type:** Happy path (frontend)
- **Expected result:**
  - Each request shows the event, venue, requested times (as recorded, Singapore time), requirements and requester.
  - There is an empty state, and a retryable error if loading fails.

## AC5 — Submitting does not confirm the booking

**TC-39-21 · A pending request does not block the venue or set the event's venue**
- **Traces to:** AC5 · **Type:** Negative (business rule)
- **Steps:** Submit the valid request. Then, as `alice`:
  - open Aurora Ballroom's availability for 12 Mar 2027;
  - search for venues on 12 Mar 2027 18:00–20:00;
  - reload E1.
- **Expected result:**
  - The request is not listed as a period, and 16:00–22:30 is not shown as unavailable because of it.
  - Aurora Ballroom still appears in the search.
  - E1's venue is still not set.

**TC-39-22 · A request is accepted even where the venue looks unavailable or unsuitable**
- **Traces to:** AC5 · **Type:** Boundary · **Depends on:** Q4, Q7
- **Preconditions:** Aurora Ballroom has a confirmed booking and a block on 12 Mar 2027.
- **Steps:** Request Aurora for E1 over that period. With a fresh seed, request Civic Hall (capacity 80) for E1 (attendance 250), and request Dockside Studio (not currently bookable).
- **Expected result:** HTTP 201 each time. The decision is left to Venue Staff.

## One pending request per event

**TC-39-23 · A second request while one is pending is refused** — *replaced by [SCRUM-85](SCRUM-85-several-venues-for-one-event.md) TC-85-01 and 03: another venue is accepted; only the same venue at an overlapping time is refused.*

**TC-39-24 · A new request is allowed once the earlier one is no longer pending**
- **Traces to:** AC1 · **Type:** Happy path
- **Preconditions:** E1 has a rejected request for Civic Hall.
- **Expected result:** Requesting Aurora for E1 gives HTTP 201.

**TC-39-25 · The database allows only one pending request per event** — *replaced by [SCRUM-85](SCRUM-85-several-venues-for-one-event.md) TC-85-05: the database allows several.*

## AC6 — Failures

**TC-39-26 · A failed save reports nothing as sent**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Expected result:**
  - HTTP 503 with `retryable: true`, and an error saying the request was not sent and to try again.
  - No `booking` is in the response, and nothing is saved.

**TC-39-27 · Retry succeeds after recovery**
- **Traces to:** AC6 · **Type:** Happy path (recovery)
- **Expected result:** Submitting again with the database working gives HTTP 201, and exactly one pending request exists.

**TC-39-29 · Venue Staff's list fails to load**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** Reading venue bookings fails (in automated tests, queries on `venue_bookings` raise `OperationalError`).
- **Expected result:** HTTP 503 with `retryable: true`. No `bookings` list is returned, so the failure is never shown as "no pending requests".

**TC-39-30 · A save the database refuses is reported as not sent** (changed by [SCRUM-85](SCRUM-85-several-venues-for-one-event.md), which removed the one-pending-request index)
- **Traces to:** AC4, AC6 · **Type:** Negative (failure)
- **Preconditions:** The database refuses the save (in automated tests, the commit raises `IntegrityError`).
- **Expected result:** HTTP 503 with `retryable: true`, saying the request was not sent. Nothing from this submission is saved.
- **Automated:** `test_save_refused_by_the_database_is_reported_as_not_sent`

**TC-39-28 · Frontend keeps the entered information after a failure**
- **Traces to:** AC6 · **Type:** Negative (frontend)
- **Steps:** Submit when the server returns 503, 409 or 403, and when there is no network. Then submit again.
- **Expected result:**
  - The error is shown: the server's explanation, or a message to check the connection and try again.
  - No confirmation appears, every input keeps its value, and the retry succeeds.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 11, 23, 24 |
| AC2 | 01, 08, 09, 10, 11 |
| AC3 | 05, 12, 13, 14, 15 |
| AC4 | 01, 16, 17, 18, 19, 20, 23, 25, 29, 30 |
| AC5 | 21, 22 |
| AC6 | 15, 26, 27, 28, 30 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 08, 11, 16, 17, 19, 20, 24, 27 |
| Negative | 02, 03, 04, 05, 06, 12, 13, 15, 18, 21, 23, 26, 28, 29, 30 |
| Boundary | 07, 09, 10, 13, 14, 22, 25 |
| Cross-cutting (authorisation) | 02, 03, 04, 07, 18 |
| Frontend | 11, 15, 19, 20, 28 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | May only the event's assigned coordinator request a venue (assumed), or any coordinator? | A1, TC-39-02 |
| Q2 | Can a venue be requested only for approved events (assumed), or also while the request is under review? | A2, TC-39-06 |
| Q3 | May the requested times differ from the event's proposed times, e.g. for setup and teardown (assumed yes)? Should there be a limit? | A3, TC-39-09 |
| Q4 | Should a request be refused when the venue already has a confirmed booking or block at that time, or is too small, or is that left to Venue Staff (assumed)? | A5, TC-39-22 |
| Q5 | Must the requested start be in the future (assumed), or some days ahead? | A3, TC-39-13 |
| Q6 | Can a coordinator ask several venues at once for the same event? Assumed not: one pending request per event. **Answered: yes** (Week 7 customer change 3, [SCRUM-85](SCRUM-85-several-venues-for-one-event.md)). | A6, TC-39-23 |
| Q7 | Should venues marked as not currently bookable be requestable (assumed yes, Venue Staff decide)? | A5, TC-39-22 |
| Q8 | Are venues assigned to particular Venue Staff, and should staff be notified of new requests? Assumed: all staff see all requests, no notification. | A8, TC-39-17 |
