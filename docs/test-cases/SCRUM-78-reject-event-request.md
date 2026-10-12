# SCRUM-78 — Reject Event Request: Test Cases

**User story:** As an Event Coordinator, I want to reject a submitted event request with a reason so that the Event Organiser understands why the event cannot proceed.

**Created:** 12 Oct 2026 · **Status of all cases:** Automated cases pass (12 Oct 2026, Supabase + Vitest). · **Automated tests:** `backend/tests/test_reject_event_request.py` (new), plus the existing SCRUM-32/59/60 tests listed below · **Endpoints:** `POST /api/events/<id>/decision`, `GET /api/events/<id>/review`, `GET /api/events/requests`, `GET /api/events/mine` · **Related:** addresses SCRUM-32 (approve or reject), which built this; SCRUM-60 (blank reasons, who decided and when); SCRUM-59 (the organiser's combined list); SCRUM-77 (approve, the same checks for approving)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Only an event request with status Submitted can be rejected. |
| AC2 | Only an Event Coordinator can reject the request. |
| AC3 | A non-empty rejection reason is required. |
| AC4 | When rejected, the request status becomes Rejected. |
| AC5 | The rejection reason is saved with the request. |
| AC6 | The Event Organiser can view the rejected status and rejection reason. |

## Working assumptions

SCRUM-32 already implements rejecting, and SCRUM-60 tightened the reason rules. This story re-checks them against the ACs above and closes the gaps in their tests. The assumptions these ACs depend on are:

- **A1 — Submitted only:** every other status is refused with HTTP 409 and nothing changes. The other statuses are `draft`, `under_review`, `approved`, `rejected` and `cancelled`. "Under review" is refused because the AC says Submitted only. *(SCRUM-32 Q5, as in SCRUM-77)*
- **A2 — Which coordinator:** only the event's *assigned* coordinator, while their role is still `coordinator` (SCRUM-32 A1). This is stricter than the AC's wording. Permission is checked before the reason (401 → 404 → 403 → 400 → 409), so a user who may not reject is told so, not asked for a reason. *(Q1)*
- **A3 — Non-empty reason:** a reason with at least one visible character, at most 1,000 words. Empty text, spaces of any kind (including invisible ones) and a missing reason are refused with HTTP 400 and "A reason is required to reject this request." The page refuses a blank reason before sending it. *(SCRUM-32 A3, SCRUM-60 A3)*
- **A4 — Saved with the request:** the trimmed reason is stored in `Event.decision_note` together with the status, the decision time and who decided, in one commit. *(SCRUM-32 A4)*
- **A5 — Where the organiser sees it:** "Status: Rejected" with "Reason: …" on both of the organiser's lists ("My requests", SCRUM-32; "My event requests", SCRUM-59), plus the in-app notification and email, which include the reason (SCRUM-32 AC5).

## Seed data

DC-SEED from [SCRUM-32](SCRUM-32-approve-reject-event-request.md#seed-data-dc-seed) (R1–R7, E1), plus R8 "Spring Fair" (dana, alice, `under_review`), as in SCRUM-77. The reason used is "The proposed date clashes with the National Day Parade."

---

## Coverage of each AC

| AC | Already covered by (existing tests) | Gap closed here |
|----|-------------------------------------|-----------------|
| AC1 | TC-32-01 (draft, approved, rejected, cancelled refused), TC-32-09, TC-60 concurrent decisions, TC-77-07 (no Reject button unless Submitted) | `under_review` was never tested for rejecting → TC-78-01, 02 |
| AC2 | TC-32-02 and 03 tried **approving** only | Rejecting by every other role and by unassigned coordinators → TC-78-03; permission checked before the reason → TC-78-04 |
| AC3 | TC-32-10 (missing, empty, whitespace, null, not text), TC-32-11 (length), TC-60 blank-reason cases (non-breaking and zero-width spaces), TC-60-12 (page refuses a blank reason without sending it) | A refused rejection saves no reason → TC-78-06 |
| AC4 | TC-32-12 | All statuses side by side → TC-78-02 |
| AC5 | TC-32-12 (stored reason) | The reason read back through the API, trimmed → TC-78-05 |
| AC6 | TC-32-18 ("My requests" after a real rejection), TC-32-13 and 14 (notification and email include the reason), TC-32-21, TC-59-11 (pages show "Reason: …") | "My event requests" after a real rejection, and privacy from other organisers → TC-78-07, 08 |

## AC1 — Only a submitted request can be rejected

**TC-78-01 · A request under review cannot be rejected**
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** A1
- **Steps:** As alice, reject R8 with a reason.
- **Expected result:** HTTP 409 naming `under_review`. R8 is unchanged, and nobody is notified or emailed.
- **Automated:** `test_a_request_under_review_cannot_be_rejected`

**TC-78-02 · Of all the statuses, only Submitted becomes Rejected**
- **Traces to:** AC1, AC4 · **Type:** Boundary
- **Steps:** As alice, reject R1, R4, R5, R6, R7 and R8 with a reason.
- **Expected result:** R1 → HTTP 200 and `rejected`. Every other request → HTTP 409, with its status unchanged. R6 (already rejected) keeps its original reason.
- **Automated:** `test_only_a_submitted_request_becomes_rejected`

## AC2 — Only an Event Coordinator can reject

**TC-78-03 · No other role, and no other coordinator, can reject**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** A2
- **Steps:** Reject R1 with a reason as admin, dana (its own organiser), farah, gus, hana, ben (another event's coordinator) and chloe (a coordinator with no events).
- **Expected result:** HTTP 403 each time, with no event details in the message. R1 stays submitted, and nobody is notified.
- **Automated:** `test_no_one_else_can_reject`

**TC-78-04 · Permission is checked before the reason**
- **Traces to:** AC2, AC3 · **Type:** Negative (order of checks)
- **Steps:** As dana, reject R1 with an empty reason.
- **Expected result:** HTTP 403, not 400. Nothing changes.
- **Automated:** `test_permission_is_checked_before_the_reason`

## AC3 and AC5 — The reason is required and saved

**TC-78-05 · The reason is saved with the request**
- **Traces to:** AC4, AC5 · **Type:** Happy path
- **Steps:** As alice, reject R1 with the reason surrounded by spaces and a line break. Then open R1's review view.
- **Expected result:** The review view shows status `rejected` and the reason, trimmed. The stored `decision_note` is the same.
- **Automated:** `test_the_reason_is_saved_with_the_request`

**TC-78-06 · A refused rejection saves no reason**
- **Traces to:** AC3, AC5 · **Type:** Negative
- **Steps:** As alice, reject R1 with a reason of three spaces.
- **Expected result:** HTTP 400. R1 stays `submitted` with no reason saved.
- **Automated:** `test_a_refused_rejection_saves_no_reason`

## AC6 — The organiser can view the rejected status and reason

**TC-78-07 · After rejection, both of the organiser's lists show it**
- **Traces to:** AC4, AC6 · **Type:** Happy path
- **Steps:** As alice, reject R1. As dana, load "My requests" and "My event requests".
- **Expected result:** On both lists, R1 has status `rejected`, the reason, the saved decision time and `decided_by` alice.
- **Automated:** `test_organiser_sees_the_rejection_on_both_lists`

**TC-78-08 · Another organiser sees neither the rejection nor its reason**
- **Traces to:** AC6 · **Type:** Negative (privacy)
- **Steps:** Reject R1, then load evan's two lists.
- **Expected result:** R1 is in neither, and the reason appears nowhere in either response.
- **Automated:** `test_another_organiser_does_not_see_the_rejection`

## Frontend

No new frontend cases are needed. Each rejection-related behaviour of the pages is already tested, and the mutation check in the evidence confirms these tests catch breakage:

| Behaviour | Existing frontend test |
|-----------|------------------------|
| Rejecting sends the trimmed reason and shows "Status: Rejected" and "Reason: …" | TC-32-20, "rejects with the trimmed reason and shows it" |
| A blank reason (spaces, non-breaking or zero-width spaces) is refused on the page and never sent | TC-60-12, "says a reason is required when rejecting with only spaces" |
| The server's refusal of a reason is shown, and the typed text is kept | TC-60-13 |
| No Reject button unless Submitted | TC-77-07 |
| The organiser's pages show "Status: Rejected" and "Reason: …" | TC-32-21, TC-59-11 |

---

## Traceability matrix

| AC | New test cases | Existing test cases |
|----|----------------|---------------------|
| AC1 | 01, 02 | TC-32-01, 09; TC-77-07 |
| AC2 | 03, 04 | TC-32-04 (session) |
| AC3 | 04, 06 | TC-32-10, 11; TC-60-12, 13 |
| AC4 | 02, 05, 07 | TC-32-12, 20 |
| AC5 | 05, 06 | TC-32-12 |
| AC6 | 07, 08 | TC-32-13, 14, 18, 21; TC-59-11 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | The AC says "an Event Coordinator". Should any coordinator be able to reject, or only the one assigned to the event (as built)? | A2, TC-78-03 |
| Q2 | Should requests "under review" be rejectable too? Assumed not, as the AC says Submitted only. | A1, TC-78-01 |
| Q3 | Is 1,000 words the right limit for a reason? (SCRUM-32 Q3) | A3 |
