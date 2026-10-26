# SCRUM-77 — Approve Event Request: Test Cases

**User story:** As an Event Coordinator, I want to approve a submitted event request so that a feasible event can proceed to further planning.

**Created:** 12 Oct 2026 · **Status of all cases:** Automated cases pass (12 Oct 2026, Supabase + Vitest). · **Automated tests:** `backend/tests/test_approve_event_request.py` (new), `frontend/src/pages/ReviewRequestPage.test.jsx` (SCRUM-77 block), plus the existing SCRUM-32/59/60 tests listed below · **Endpoints:** `POST /api/events/<id>/decision`, `GET /api/events/requests`, `GET /api/events/mine` · **Related:** addresses SCRUM-32 (approve or reject), which built this; SCRUM-60 (who decided and when); SCRUM-59 (the organiser's combined list)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Only an event request with status Submitted can be approved. |
| AC2 | Only an Event Coordinator can approve the request. |
| AC3 | When approved, the request status becomes Approved. |
| AC4 | The Event Organiser can view the approved status. |

## Working assumptions

SCRUM-32 already implements approving. This story re-checks it against the ACs above and closes the gaps in its tests. The SCRUM-32 assumptions still apply. The ones these ACs depend on are:

- **A1 — Submitted or under review:** a request that is Submitted or Under Review can be approved. Every other status (`draft`, `approved`, `rejected`, `cancelled`) is refused with HTTP 409, and nothing changes. Until SCRUM-31 was reopened, "under review" was refused too, because the AC says Submitted only. *Changed by SCRUM-31's reopening (26 Oct 2026): starting a review moves a request to Under Review, so the team decided it can still be decided (SCRUM-31 A13, Q7).* *(SCRUM-32 Q5)*
- **A2 — Which coordinator:** only the event's *assigned* coordinator, while their role is still `coordinator` (SCRUM-32 A1). This is stricter than the AC's wording: every other role is refused, and so is a coordinator who is not assigned to the event. *(Q1)*
- **A3 — Where the organiser sees it:** the status shows on both of the organiser's lists, "My requests" (SCRUM-32) and "My event requests" (SCRUM-59). It comes with the decision time and who decided (SCRUM-60), and the approval note if there is one. The organiser is also notified in-app and by email (SCRUM-32 AC5).

## Seed data

DC-SEED from [SCRUM-32](SCRUM-32-approve-reject-event-request.md#seed-data-dc-seed) (R1–R7, E1), plus:

| Ref | Title | Organiser | Coordinator | Status |
|-----|-------|-----------|-------------|--------|
| R8 | Spring Fair | dana | alice | under_review |

---

## Coverage of each AC

| AC | Already covered by (existing tests) | Gap closed here |
|----|-------------------------------------|-----------------|
| AC1 | TC-32-01 (draft, approved, rejected, cancelled refused), TC-32-09 (cannot approve twice), TC-60 concurrent decisions | `under_review` was never tested → TC-77-01, 02; review page buttons per status → TC-77-07, 08 |
| AC2 | TC-32-02 (other roles and other coordinators refused), TC-32-03 (reassignment and role change), TC-32-04 (session) | Every non-coordinator role, with no event details leaked → TC-77-03 |
| AC3 | TC-32-07 (status becomes approved, decision time and decider saved), TC-32-08 (optional note) | All statuses side by side → TC-77-02 |
| AC4 | TC-32-17, TC-59-04 (lists show approved rows that were seeded), TC-32-21, TC-59-11 (pages show "Approved") | No test approved a request and then read the organiser's lists → TC-77-04, 05, 06 |

## AC1 — Only a submitted request can be approved

**TC-77-01 · A request under review can be approved** (changed by SCRUM-31)
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** A1
- **Steps:** As alice, approve R8.
- **Expected result:** HTTP 200. R8 becomes `approved`, with the decision recorded, and the organiser is notified. (Before SCRUM-31's reopening: HTTP 409.)
- **Automated:** `test_a_request_under_review_cannot_be_approved`

**TC-77-02 · Of all the statuses, only Submitted and Under Review become Approved** (changed by SCRUM-31)
- **Traces to:** AC1, AC3 · **Type:** Boundary
- **Steps:** As alice, approve R1 (submitted), R4 (draft), R5 (approved), R6 (rejected), R7 (cancelled) and R8 (under review).
- **Expected result:** R1 and R8 → HTTP 200 and status `approved`. Every other request → HTTP 409, with its status unchanged.
- **Automated:** `test_only_a_submitted_request_becomes_approved`

## AC2 — Only an Event Coordinator can approve

**TC-77-03 · No other role can approve**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** A2
- **Steps:** Approve R1 as admin, dana (its own organiser), farah (attendee), gus (venue staff) and hana (tech staff).
- **Expected result:** HTTP 403 each time, with no event details in the message. R1 stays submitted, and nobody is notified.
- **Automated:** `test_no_other_role_can_approve`

## AC4 — The organiser can view the approved status

**TC-77-04 · After approval, both of the organiser's lists show Approved**
- **Traces to:** AC3, AC4 · **Type:** Happy path
- **Steps:** As alice, approve R1. As dana, load "My requests" (`/api/events/requests`) and "My event requests" (`/api/events/mine`).
- **Expected result:** On both lists, R1 has status `approved`, the saved decision time, `decided_by` alice and no note.
- **Automated:** `test_organiser_sees_the_approval_on_both_lists`

**TC-77-05 · An approval note is shown with the status**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** Approve R1 with the note "Please book the venue by 1 Nov.", then load dana's "My event requests".
- **Expected result:** R1 is `approved`, with that note.
- **Automated:** `test_organiser_sees_the_approval_note`

**TC-77-06 · Another organiser does not see the approval**
- **Traces to:** AC4 · **Type:** Negative
- **Steps:** Approve R1, then load evan's two lists.
- **Expected result:** R1 is in neither.
- **Automated:** `test_another_organiser_does_not_see_the_approval`

## Frontend

**TC-77-07 · No Approve button unless the request is Submitted or Under Review** (changed by SCRUM-31)
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** The review page for a request that is approved, a draft or cancelled shows its status and no Approve or Reject button. A request under review offers both (SCRUM-31 TC-31-42).
- **Automated:** `ReviewRequestPage.test.jsx`, "offers no Approve button for a … request"

**TC-77-08 · A refusal from the server is shown**
- **Traces to:** AC1 · **Type:** Frontend
- **Steps:** The page shows a submitted request, but the server refuses the approval with HTTP 409 (e.g. another tab decided it first).
- **Expected result:** The server's message is shown as an alert. The page still says Submitted.
- **Automated:** `ReviewRequestPage.test.jsx`, "shows the server's refusal when the request is no longer submitted"

---

## Traceability matrix

| AC | New test cases | Existing test cases |
|----|----------------|---------------------|
| AC1 | 01, 02, 07, 08 | TC-32-01, 09, 20 |
| AC2 | 03 | TC-32-02, 03, 04 |
| AC3 | 02, 04 | TC-32-07, 08 |
| AC4 | 04, 05, 06 | TC-32-13, 17, 21; TC-59-04, 11; TC-60 (who decided) |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | The AC says "an Event Coordinator". Should any coordinator be able to approve, or only the one assigned to the event (as built)? | A2, TC-77-03, TC-32-02 |
| Q2 | Should requests "under review" be approvable too? Assumed not at first, as the AC says Submitted only. The team decided yes when SCRUM-31 was reopened (26 Oct 2026); still to be confirmed with the customer. | A1, TC-77-01 |
