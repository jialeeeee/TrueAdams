# SCRUM-29 — Save and Resume a Draft Event Request: Test Cases

**User story:** As an Event Organiser, I want to save an unfinished event request and resume it later so that I can prepare the request without losing my progress.

**Created:** 28 Sep 2026 · **Status of all cases:** Automated cases pass (28 Sep 2026, local PostgreSQL with db/event_drafts.sql applied + Vitest); frontend cases 10, 15, 19, 23, 29 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_event_drafts.py`, `frontend/src/pages/DraftEventPage.test.jsx`, `frontend/src/pages/MyDraftsPage.test.jsx`

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The organiser can save a request with incomplete information without submitting it for review. |
| AC2 | A successfully saved request has status Draft and displays its last-saved date and time. |
| AC3 | Reopening a saved draft displays its previously saved information, which the organiser can continue editing. |
| AC4 | Saving changes updates the existing draft rather than creating another request. |
| AC5 | If saving fails, an error is displayed, the previously saved draft remains unchanged, and the current edits remain available for retry. |
| AC6 | A draft becomes Submitted only after successful submission; saving alone does not change it to Submitted. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Fields:** an event request has the fields in the customer brief: event name (`title`), purpose, description, proposed start and end date and time, expected attendance, venue requirements, accessibility needs, equipment requirements, and whether attendee registration is needed. *(Q1)*
- **A2 — Minimum to save:** a draft needs only an event name. Every other field may be left empty.
- **A3 — Who:** only users with the `organiser` role can create drafts, and only a draft's own organiser can open, save or submit it. This is checked against the database on every request. *(Q2)*
- **A4 — Values accepted when saving:** each field that is filled in must be of the right kind: text for text fields, a whole number of at least 1 for expected attendance, a date and time (`YYYY-MM-DDTHH:MM`) for start and end, and yes/no for registration. Wrong kinds are refused. Checks that compare fields (end after start) happen only on submission, so an unfinished draft can always be saved.
- **A5 — Blank text:** text that is empty or only whitespace is saved as *not filled in*. Other text is trimmed.
- **A6 — Saving:** a save sends the fields being changed. Fields not sent keep their saved values; a field sent as empty is cleared. Each successful save sets the last-saved time.
- **A7 — Required to submit:** event name, purpose, description, start, end, expected attendance, venue requirements, and the registration yes/no. Accessibility needs and equipment requirements are optional ("where relevant" in the brief). The end must be after the start. *(Q3, Q4)*
- **A8 — After submission:** a submitted request is no longer a draft. It cannot be saved or submitted again through the draft endpoints, and it leaves the organiser's drafts list. Changes after submission belong to the Event Change Requests story.
- **A9 — Time zones:** proposed start and end are Singapore time without a time zone, like venue bookings. Last-saved and submitted times are stored as naive UTC and shown in the user's local time.
- **A10 — Order of checks:** not logged in (401), unknown request (404), not allowed (403), not a draft (409), invalid values (400).

## Endpoints under test

- `POST /api/events/drafts` → **201** draft. Creates a new draft.
- `GET /api/events/drafts` → **200** `{"drafts": [{"id", "title", "status", "last_saved_at"}, ...], "message": str | null}`. Lists the caller's own drafts, most recently saved first. `message` holds the empty-state text.
- `GET /api/events/drafts/<id>` → **200** draft.
- `PUT /api/events/drafts/<id>` → **200** draft. Saves changes to this draft.
- `POST /api/events/drafts/<id>/submit` → **200** the request, with status `submitted`.
- A draft is `{"id", "status", "title", "purpose", "description", "start_time", "end_time", "expected_attendance", "venue_requirements", "accessibility_needs", "equipment_requirements", "registration_required", "created_at", "last_saved_at", "submitted_at", "missing_for_submission": [...]}`.
- Errors are `{"error": str}`. A field error adds `"field"`, and a submission refused for missing information adds `"missing": [...]`. Save or submit failures are **503** with `"retryable": true`.

## Seed data (DR-SEED)

Reset the database to this data before **every** test case. Users come from `backend/tests/seed_data.py`: dana and evan (organisers), alice (coordinator), admin, farah (attendee), gus (venue staff), hana (tech staff).

| Ref | Title | Organiser | Status | Filled in |
|-----|-------|-----------|--------|-----------|
| D1 | Harbour Lights Festival | dana | draft | title, purpose, start 12 Dec 2026 17:00, attendance 250 |
| D2 | Winter Networking Night | dana | draft | every field (complete) |
| D3 | Product Launch Planning | evan | draft | title only |
| S1 | Charity Gala | dana | submitted | every field |

---

## AC1 — Save a request with incomplete information

**TC-29-01 · Save a new draft with only an event name**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Preconditions:** DR-SEED loaded; logged in as `dana`.
- **Steps:** 1. Start a new event request. 2. Enter only the event name. 3. Click Save draft.
- **Test data:** Event name = "Spring Garden Party".
- **Expected result:** HTTP 201. The request is saved with status Draft, dana as organiser and a last-saved time. Every other field is empty. It is not submitted for review.

**TC-29-02 · Save a partly completed draft**
- **Traces to:** AC1 · **Type:** Happy path
- **Test data:** Event name = "Spring Garden Party"; purpose = "Annual staff social"; expected attendance = 120; start = 2027-03-20T15:00. Nothing else.
- **Expected result:** HTTP 201 with status Draft. The four entered values are saved exactly; the rest are empty.

**TC-29-03 · An event name is required**
- **Traces to:** AC1, AC5 · **Type:** Negative
- **Test data:** Name missing; `""`; `"   "`; `null`. Also, saving D1 with its name changed to `""`.
- **Expected result:** HTTP 400 naming the event name field. No draft is created, and D1 keeps its saved name.

**TC-29-04 · Values of the wrong kind are refused**
- **Traces to:** AC1, AC5 · **Type:** Negative / boundary
- **Test data:** expected attendance = 0, -5, 12.5, "many", `true`; start = "tomorrow", "2027-02-30T10:00"; registration = "yes"; purpose = 42; a field that does not exist (`"budget"`); a body that is not JSON.
- **Expected result:** HTTP 400, naming the field where there is one. Nothing is created or changed. Attendance = 1 is accepted.

**TC-29-05 · Only organisers can create drafts**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q2
- **Steps:** Create a draft as alice, admin, farah, gus and hana.
- **Expected result:** HTTP 403 for each. Nothing is created.

**TC-29-06 · A valid session is required**
- **Traces to:** AC1–AC6 · **Type:** Negative (authentication)
- **Steps:** With no token, an expired token, and a token for a deleted user: create a draft, list drafts, open D1, save D1, submit D1.
- **Expected result:** HTTP 401 each time. D1 is unchanged.

## AC2 — Status Draft and last-saved date and time

**TC-29-07 · A saved request is a Draft with its last-saved time**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As `dana`, save a new draft, then open it and list drafts.
- **Expected result:** Status is "draft" everywhere. `last_saved_at` is the time of the save (between just before and just after the request) and is the same in the save response, when opened, and in the list.

**TC-29-08 · The last-saved time moves forward with each save**
- **Traces to:** AC2, AC4 · **Type:** Boundary
- **Steps:** Save D1, then save it again.
- **Expected result:** Both are later than D1's seeded last-saved time, and the second is not earlier than the first. (Two saves made within one tick of the server clock can share a time.) The stored value is the second.

**TC-29-09 · The drafts list**
- **Traces to:** AC2, AC3 · **Type:** Happy path / negative
- **Steps:** List drafts as `dana`, then as `evan`, then as an organiser with no drafts.
- **Expected result:** dana sees D2 and D1 (most recently saved first), not S1 (submitted) and not D3 (evan's). evan sees only D3. The organiser with none gets an empty list and a message saying there are no drafts. Other roles get HTTP 403.

**TC-29-10 · Frontend shows Draft and the last-saved time**
- **Traces to:** AC2 · **Type:** Happy path (frontend)
- **Expected result:** After saving, the page shows "Status: Draft" and "Last saved" with the date and time in local time. Before the first save it shows "Not saved yet".

## AC3 — Reopen and continue editing

**TC-29-11 · Reopening shows everything previously saved**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** As `dana`, open D2.
- **Expected result:** HTTP 200 with every seeded value, the same last-saved time, and an empty `missing_for_submission`. Opening D1 lists the fields it still needs before submission.

**TC-29-12 · Another organiser's draft cannot be opened, saved or submitted**
- **Traces to:** AC3 · **Type:** Negative (authorisation)
- **Steps:** As `evan`, and as `alice`, open, save and submit D1.
- **Expected result:** HTTP 403 each time. D1's title and purpose do not appear in the response. D1 is unchanged.

**TC-29-13 · Unknown draft**
- **Traces to:** AC3 · **Type:** Negative
- **Expected result:** Opening, saving or submitting an ID that does not exist gives HTTP 404.

**TC-29-14 · A submitted request cannot be reopened as a draft**
- **Traces to:** AC3, AC6 · **Type:** Negative (business rule)
- **Steps:** As `dana`, open, save and submit S1 through the draft endpoints.
- **Expected result:** HTTP 409 saying the request has already been submitted. S1 is unchanged.

**TC-29-15 · Frontend reopens a draft for editing**
- **Traces to:** AC3 · **Type:** Happy path (frontend)
- **Expected result:** Opening a draft fills the form with its saved values, which can be changed and saved again.

## AC4 — Saving updates the existing draft

**TC-29-16 · Saving changes updates the same draft**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** As `dana`, change D1's description and attendance and save; then save again.
- **Expected result:** HTTP 200 with the same ID. dana still has exactly the same number of event requests. The new values are saved.

**TC-29-17 · Only the fields sent are changed; empty clears a field**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** A6
- **Steps:** Save D1 with only a description. Then save D1 with purpose = `null`, and then with purpose = `"   "`.
- **Expected result:** The first save leaves D1's other fields unchanged. The second and third clear the purpose.

**TC-29-18 · Text is trimmed**
- **Traces to:** AC4 · **Type:** Boundary
- **Test data:** Event name = `"  Spring Garden Party \n"`.
- **Expected result:** Saved as "Spring Garden Party".

**TC-29-19 · Frontend saves to the same draft**
- **Traces to:** AC4 · **Type:** Happy path (frontend)
- **Expected result:** The first save of a new request creates it. Later saves update the same draft, and no second draft is created.

## AC5 — Save failures

**TC-29-20 · A failed save leaves the saved draft unchanged**
- **Traces to:** AC5 · **Type:** Negative (failure)
- **Preconditions:** Saving to the database fails (in automated tests, the commit raises `SQLAlchemyError`).
- **Steps:** As `dana`, change D1's description and save.
- **Expected result:** HTTP 503 with `retryable: true` and an error saying the draft was not saved and to try again. D1's saved values and last-saved time are unchanged.

**TC-29-21 · A failed first save creates nothing**
- **Traces to:** AC5 · **Type:** Negative (failure)
- **Expected result:** HTTP 503 with `retryable: true`. No draft is created.

**TC-29-22 · Retry succeeds after recovery**
- **Traces to:** AC5 · **Type:** Happy path (recovery)
- **Expected result:** Repeating TC-29-20's save with the database working succeeds, and D1 has the new description.

**TC-29-23 · Frontend keeps the edits and allows retry**
- **Traces to:** AC5 · **Type:** Negative (frontend)
- **Steps:** Edit a draft and save when the server returns 400 or 503, or there is no network. Then click Save draft again when the server is back.
- **Expected result:** The error is shown (the server's explanation, or a message to check the connection and try again). Every edit stays in the form, the last-saved time does not change, and the retry saves.

## AC6 — Only submission makes a draft Submitted

**TC-29-24 · Saving never submits**
- **Traces to:** AC6 · **Type:** Negative (business rule)
- **Steps:** Save D2 (complete) three times.
- **Expected result:** It stays "draft", with no submitted time, and is still in the drafts list.

**TC-29-25 · Submitting a complete draft**
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As `dana`, submit D2.
- **Expected result:** HTTP 200 with status "submitted" and a submitted time. D2 leaves dana's drafts list, and its saved values are unchanged.

**TC-29-26 · An incomplete draft cannot be submitted**
- **Traces to:** AC6 · **Type:** Negative · **Depends on:** Q3
- **Steps:** As `dana`, submit D1.
- **Expected result:** HTTP 400 listing exactly the missing fields (description, end, venue requirements, registration). D1 stays a draft, unchanged.

**TC-29-27 · End must be after start to submit**
- **Traces to:** AC6 · **Type:** Boundary
- **Test data:** D2 with end equal to start; D2 with end one minute before start. Saving these is allowed (A4).
- **Expected result:** Both saves succeed. Both submissions are refused with HTTP 400 naming the end time, and D2 stays a draft.

**TC-29-28 · A failed submission leaves the draft as a draft**
- **Traces to:** AC6, AC5 · **Type:** Negative (failure)
- **Expected result:** When the commit fails, HTTP 503 with `retryable: true`. D2 is still a draft with no submitted time.

**TC-29-29 · Frontend submits the current edits**
- **Traces to:** AC6 · **Type:** Happy path / negative (frontend)
- **Steps:** Edit a draft and click Submit for review.
- **Expected result:** The edits are saved, then the request is submitted, and "Status: Submitted" is shown with the form no longer editable. If submission is refused, the missing fields are listed, the status stays Draft, and the edits remain.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06 |
| AC2 | 01, 07, 08, 09, 10 |
| AC3 | 09, 11, 12, 13, 14, 15 |
| AC4 | 08, 16, 17, 18, 19 |
| AC5 | 03, 04, 20, 21, 22, 23, 28 |
| AC6 | 14, 24, 25, 26, 27, 28, 29 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 07, 09, 11, 16, 22, 25 |
| Negative | 03, 04, 05, 06, 09, 12, 13, 14, 20, 21, 24, 26, 28 |
| Boundary | 04, 08, 17, 18, 27 |
| Cross-cutting (authorisation) | 05, 06, 09, 12 |
| Frontend | 10, 15, 19, 23, 29 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Are these the right fields for an event request? Should venue requirements, accessibility needs and equipment be free text (assumed) or chosen from lists? | A1 |
| Q2 | Can anyone other than the organiser (e.g. a colleague or an admin) create or edit a draft on their behalf? | A3, TC-29-05, 12 |
| Q3 | Which fields must be completed before submission? Are accessibility needs and equipment requirements optional (assumed)? | A7, TC-29-26 |
| Q4 | Must the proposed date be in the future, or at least some days ahead, to submit? | A7, TC-29-27 |
| Q5 | Can an organiser delete a draft they no longer need? | New story if yes |
| Q6 | Should an organiser be warned when leaving the page with unsaved changes? | Frontend |
