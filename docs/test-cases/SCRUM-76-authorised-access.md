# SCRUM-76 - Access Only Authorised Information and Functions: Test Cases

**Phase:** focused GREEN verification complete, 21 Oct 2026 (Singapore), branch `feature/SCRUM-76-authorised-access`, baseline `536a537`. **Result: READY FOR PR** for the confirmed compatibility scope: 25 GREEN methods passed, 0 failures/errors/skips. Earlier RED: 9 methods passed without a demonstrated defect. Production code is unchanged. This document uses the user's confirmed sprint boundary.

## Original Jira requirements (verbatim)

**Title:** Access Only Authorised Information and Functions

**Description:**

As a signed-in system user, I want access to be limited according to my role and involvement in an event so that protected information and functions are available based on my level of privilege

**Acceptance criteria:**

- Access follows the agreed permissions for Event Organisers, Event Coordinators, Venue Staff, Technical Support Staff, and Attendees, Event Coordinator Lead, Safety Officer
- Where access depends on involvement in an event, a user can access only events and information permitted by that relationship.
- A user attempting to access restricted information is denied access.
- A user attempting to modify restricted information is denied access and the information remains unchanged.
- Restrictions are enforced even when access is attempted through a direct link or request.

**Original Jira note:**

Prior to this, Event Coordinator Lead and Safety Officers were not implemented, as it was a new client change. If it is not implemented, implement it here

The five bullets are AC1–AC5 in order. The wording above is preserved from the user's GREEN request; no additional ACs are introduced. No Jira URLs were supplied.

## Confirmed scope and dependencies

The user confirmed that the following stories are planned for the **next sprint**:

| Story | Responsibility |
|---|---|
| SCRUM-90 | Safety Officer sees events awaiting a safety check. |
| SCRUM-91 | Safety Officer approves an event. |
| SCRUM-92 | Safety Officer rejects an event or requests changes. |

SCRUM-76 covers legitimate stored-role recognition and compatibility with existing permission boundaries, including denial of unrelated reads/writes through direct requests. The absence of the future Operational Safety Check is **not a SCRUM-76 defect or GREEN blocker** under this confirmed split. No speculative workflow tests, endpoints, pages, states, schema or preparation/confirmation changes are included. Safety-review scope and transitions belong to SCRUM-90/91/92.

## Existing rules and implementation audit

Sources: [AGENTS.md](../../AGENTS.md), [SCRUM-27](SCRUM-27-authentication-authorization.md), [SCRUM-75](SCRUM-75-test-cases.md), [SCRUM-80](SCRUM-80-test-cases.md), [SCRUM-81 assignment](SCRUM-81-lead-assigns-coordinator.md), [queue](SCRUM-81-unassigned-queue.md), [SCRUM-82](SCRUM-82-lead-reassigns-coordinator.md), [SCRUM-83](SCRUM-83-lead-assigned-events.md), [SCRUM-74](SCRUM-74-view-event-details.md), [event permission helpers](../../backend/app/events/permissions.py), [event routes](../../backend/app/events/routes.py), [venue routes](../../backend/app/venues/routes.py), [registration routes](../../backend/app/registrations/routes.py).

- **Original roles:** organiser ownership requires the stored `organiser` role and `organiser_id`; coordinator management requires stored `coordinator` and current `coordinator_id`. Venue Staff retain catalogue/booking/hold functions. Technical Support retain all-event equipment reads/arrangement updates, without an invented staff-event assignment. Attendee registration/withdrawal remains role- and owner-restricted.
- **Lead:** stored `coordinator_lead` can use the shared waiting queue, assign eligible waiting events and reassign eligible assigned events. Any Lead may reassign another Lead's event (SCRUM-82); the supervised list only includes active events whose **latest** assignment was made by that Lead (`coordinator_assigned_by_id`). Supervision does not confer coordinator planning/history/edit rights or venue/technical privileges.
- **Safety Officer:** `User.role` is a string; generic hashed-password login recognises stored `safety_officer` without a new model or role framework. Existing positive role guards deny unrelated internal functions. SCRUM-75 already tests its frontend fallback landing; future review rights belong to the dependencies above.
- **Stored role:** JWT identity identifies the caller; protected routes reload `User`. Token role claims are not authority. A matching event relationship without the required current role does not grant coordinator privileges.
- **Direct access:** JWT/backend guards protect delivered operations independently of shared signed-in navigation/page shells. Ordinary unpublished event details deliberately use the same masked 404 as a missing event; most internal endpoints use 403. No broad role-menu redesign is required.

| AC | Current status in confirmed SCRUM-76 scope | Evidence / remaining limitation |
|---|---|---|
| AC1 | **PASS** for confirmed compatibility scope | TC-76-01/02/03/04 plus 11 existing Lead and representative original-role database tests pass. Future safety functionality remains with SCRUM-90/91/92. |
| AC2 | **PASS** for established relationships | Matching-ID/stored-role isolated checks and persisted assignment/privilege-transfer/supervision tests pass. Q2/Q4 remain policy ambiguities, not established defects. |
| AC3 | **PASS** for selected read boundaries | New-role isolated refusals and persisted organiser/attendee/non-Lead refusals pass without protected payloads. No exhaustive endpoint matrix is claimed. |
| AC4 | **PASS**, including persisted event checks | TC-76-02/03 now include a local database case: denied Lead/Safety Officer planning PATCH leaves every reloaded Event field and notification count unchanged, with no email. Existing persisted original-role reassignment/privilege-transfer checks also pass. |
| AC5 | **PASS** for selected direct requests | Both isolated and database-backed tests use direct Flask/JWT HTTP requests. Frontend refusal/direct-link tests remain reused source evidence, not a new browser execution claim. |

No production permission gap was demonstrated by the focused execution. These statuses describe the tested compatibility slice and existing contracts, not execution of every historical test or sign-off on unresolved policy.

## Existing coverage reused

All references were reviewed; only the selections explicitly recorded in the RED/GREEN execution sections were run. A reference to a file does not imply its full suite passed.

| Key | Existing tests / documentation | Reuse instead of duplication |
|---|---|---|
| R1 | [test_authorization_http_unit.py](../../backend/tests/test_authorization_http_unit.py): `test_lead_can_reassign_and_lock_is_requested`, `test_admin_and_current_coordinator_cannot_reassign`, `test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them`; [test_authorization_unit.py](../../backend/tests/test_authorization_unit.py): `test_only_leads_can_reassign`, `test_new_role_preserves_its_legitimate_coordinator_information_access` | Executed unchanged: positive Lead reassignment, original-role denial, event privilege transfer and existing staff information access. |
| R2 | [test_lead_assign_coordinator.py](../../backend/tests/test_lead_assign_coordinator.py), [test_lead_reassign_coordinator.py](../../backend/tests/test_lead_reassign_coordinator.py), [test_unassigned_queue.py](../../backend/tests/test_unassigned_queue.py), [test_lead_assigned_events.py](../../backend/tests/test_lead_assigned_events.py) | **11 selected existing methods PASS in GREEN**: queue, assignment/details, reassignment/audit/scope, supervision and non-Lead refusals. Exact methods below; no workflow reimplementation. |
| R3 | [test_authorization.py](../../backend/tests/test_authorization.py), [test_equipment_requirements.py](../../backend/tests/test_equipment_requirements.py), [test_venue_catalogue.py](../../backend/tests/test_venue_catalogue.py) | **6 existing methods plus 1 new persisted case PASS in GREEN**, listed below. Other previously inspected staff cases were not rerun; no whole-file pass claim. |
| R4 | [LoginPage.test.jsx](../../frontend/src/pages/LoginPage.test.jsx): `takes %s to its existing home page`; [App.test.jsx](../../frontend/src/App.test.jsx): `refuses signed-out direct navigation to %s before loading protected data`; [EventPlanningPage.test.jsx](../../frontend/src/pages/EventPlanningPage.test.jsx): `shows a refusal without a Retry button or any event information`; [AssignCoordinatorPage.test.jsx](../../frontend/src/pages/AssignCoordinatorPage.test.jsx): `denies anyone else without showing the event, a form or a retry` | Existing landing/direct-link/refusal rendering tests inspected, **not run**. Merely adding a role label to an identical mocked 403 would not add permission evidence; no frontend changes. |

## Working assumptions and questions

- **A1 / Q1 - Resolved by user:** SCRUM-90/91/92 own the Operational Safety Check next sprint. SCRUM-76 uses existing `safety_officer` recognition and restricts unrelated functions; no speculative review tests or workflow implementation.
- **A2 / Q2:** preserve SCRUM-81/82/83's explicit queue, any-Lead reassignment and own-supervision contracts. Week 7's broader assignment-visibility wording does not authorise changing another story. Confirm any separate global-assignment-list requirement with its owner before expanding functionality.
- **A3 / Q3 - Deferred to SCRUM-90/91/92:** officer-specific event scope/readiness/decision transitions are not assumed or tested here. Their absence is not a current compatibility failure.
- **A4 / Q4:** `_can_view_event` permits an unpublished detail read whenever `organiser_id` matches, even after the stored role changes. Other owner helpers require the current organiser role, but SCRUM-74 AC4 grants access to event **creators and approvers** and does not settle post-role-change creator rights. This is not a demonstrable contradiction sufficient to invent a failing test. Confirm whether that creator privilege survives role changes before changing its expectation/helper.

## Seed data (AA76-SEED, isolated)

Reuse the existing isolated fixtures in `AuthorizationHttpUnitTests` and `AuthHttpUnitTests`, without `AppTestCase` or a database. Users 1/2/3 are organiser/current/replacement coordinator; user 4 is switched between stored Lead and Safety Officer. Event 7 is submitted; new boundary tests deliberately set both `coordinator_id` and `coordinator_assigned_by_id` to 4. The write test also supplies mocked venue 8 (capacity 80) and equipment requirement 9 (`requested`), with state snapshots. The role-change test uses an unassigned event and retains the original JWT. Login uses user 75 and the existing real password hash.

Fixtures register real blueprints on a minimal Flask app and mock only persistence/email collaborators, not permission predicates. Existing `Engine.connect`, `Engine.raw_connection` and socket-connect guards fail on accidental database/network access. The application factory and SQLAlchemy engine are not initialised. No test uses `tests.base`, Supabase or a second application connection. Production configuration imports may load environment settings; they do not establish a connection.

During **RED**, no database-dependent test was necessary and no database was contacted. During **GREEN**, the user authorised local persistence verification: the environment, effective configuration and live database/user/schema were verified before executing the selected database tests. Those fixtures use `tests.base.AppTestCase`: test-owned rows inside rolled-back transactions, route commits inside savepoints. No independent remote connection was found in the selected fixture/test sources. The exact guarded command is below.

## Test cases

Automation keys: **AUTH** = `tests.test_auth_unit.AuthHttpUnitTests`; **HTTP** = `tests.test_authorization_http_unit.AuthorizationHttpUnitTests`. New tests share the existing fixture/helpers; no duplicate fixture module or production changes.

### AC1 - Stored role recognition

**TC-76-01 - Login recognises the two Week 7 roles**

- **Traces to:** AC1. **Type:** isolated HTTP/password/JWT.
- **Preconditions:** AA76-SEED hashed credentials for user 75.
- **Steps:** Execute existing successful-login test for coordinator, Lead and Safety Officer stored roles.
- **Expected:** Each returns 200, the exact stored role and a JWT with string user-ID subject. No role-specific login implementation is needed.
- **Automated:** AUTH `test_success_returns_token_and_stored_role`, extended with Lead/Safety Officer subcases; original coordinator assertions retained.
- **Actual:** **PASS** (three role subcases in one method). Mocked lookup, not persisted-account integration. Existing frontend landing test is R4, not rerun.

### AC2 / AC3 / AC4 / AC5 - Role, involvement and direct requests

**TC-76-02 - Lead involvement grants no unrelated domain privileges**

- **Traces to:** AC1-AC5. **Type:** isolated direct HTTP and state/side-effect assertions.
- **Preconditions:** User 4 is stored Lead and matches both event 7's coordinator and latest assigning Lead IDs.
- **Steps:** Directly GET planning/history/equipment requirements/venue details; attempt valid planning PATCH, equipment-arrangement PATCH and venue PUT. Reuse R1's positive Lead reassignment and event-transfer tests.
- **Expected:** All unrelated operations return 403 with error-only payloads and no private title/user data. Event/venue/equipment snapshots remain unchanged; no commit/add/flush/delete or email. Matching IDs cannot substitute for the coordinator or staff role. Existing unrelated-Lead equipment coverage is R3; these subcases additionally exercise the matching coordinator/supervisor-ID boundary.
- **Automated:** HTTP `test_new_roles_cannot_read_unrelated_protected_information`, `test_new_roles_denied_writes_leave_state_and_side_effects_unchanged`, Lead subcases; R1 reused unchanged for allowed access.
- **Actual:** **PASS**. In-memory snapshots and persistence-call checks only, not a database durability claim.
- **GREEN persistence addition:** `tests.test_authorization.AuthorizationEvidenceTests.test_new_roles_cannot_modify_persisted_planning_information` adds one small database-backed case for both new roles. It directly PATCHes planning, reloads every Event column and checks notification count/no email. **PASS**; the matching coordinator/supervisor-ID variation remains isolated evidence.

**TC-76-03 - Safety Officer cannot read or modify unrelated protected information**

- **Traces to:** AC1-AC5. **Type:** isolated direct HTTP and state/side-effect assertions.
- **Preconditions:** Same matching-ID fixtures, with user 4 stored as Safety Officer.
- **Steps:** Repeat the four representative reads and three writes from TC-76-02, sharing its test methods rather than duplicating tests.
- **Expected:** 403/error-only response; no private data, object mutation, persistence calls or email. Existing coordinator/Venue Staff/Technical Support functions are not Safety Officer privileges.
- **Automated:** Same two HTTP methods as TC-76-02, Safety Officer subcases.
- **Actual:** **PASS**. No safety queue, review, decision or preparation workflow is exercised.
- **GREEN persistence:** the same new database-backed case as TC-76-02 verifies Safety Officer planning-write refusal and unchanged persisted Event fields/notifications. **PASS**; no future safety workflow is exercised.

**TC-76-04 - Existing JWT permissions follow the stored Safety Officer/Lead role**

- **Traces to:** AC1-AC5. **Type:** isolated HTTP with real JWTs and mocked stored-user changes.
- **Preconditions:** User 4 stored Safety Officer, event 7 waiting, original JWT claiming Safety Officer and another JWT with a forged Lead claim.
- **Steps:** Request assignment details with both tokens and queue with original token; promote stored role to Lead and reuse original token for queue/assignment reads; restore Safety Officer and repeat queue GET and valid assignment POST.
- **Expected:** Both initial assignment attempts are denied before candidate lookup, regardless of claim. Promotion permits existing Lead reads with the unchanged original token and returns the existing assignment/candidate payload. Revocation immediately denies queue/write; event and side effects remain unchanged.
- **Automated:** HTTP `test_safety_officer_lead_access_follows_stored_role_with_original_token`.
- **Actual:** **PASS**. This fills new-role compatibility evidence; existing full Lead workflow tests stay with their stories.

### Conditional / reused / excluded cases

**TC-76-05 - Former organiser ordinary-detail access:** traces to AC2/AC3/AC5; **Not run**, no automated test added. Q4 must establish the expected result before a failing assertion is legitimate. The static ownership observation remains; no defect or customer answer is invented.

**TC-76-06 - Direct-link refusal rendering:** traces to AC3/AC5; reuse R4's existing frontend tests. **Not run** in this phase; no new frontend tests or browser results. Executed TC-76-02/03/04 supply role-specific backend direct-request evidence.

**TC-76-07 - Operational Safety Check:** **outside this sprint's SCRUM-76 testing scope**, assigned to SCRUM-90/91/92 by the user. No speculative executable case, endpoint, lifecycle expectation or failing test is added. This replaces the initial audit's deferred workflow proposal, not an additional AC.

## Traceability matrix

| Original AC | Targeted cases | Existing evidence reused | Execution qualification |
|---|---|---|---|
| AC1 | TC-76-01/02/03/04 | R1/R2/R3; R4 role landing | Selected isolated and local database tests PASS; R4 not rerun. |
| AC2 | TC-76-02/03/04; conditional 05 | R1 privilege transfer, R2 supervision | Selected isolated and persisted relationship tests PASS; 05 not run pending policy. |
| AC3 | TC-76-02/03/04; reused 06 | R1/R2/R3 guards, R4 rendering | Selected isolated and persisted refusals PASS; R4 not rerun. |
| AC4 | TC-76-02/03/04 | R1/R3 snapshots and persisted denials | New-role mock snapshots **and** new-role/all-original-role persisted event refusal checks PASS. |
| AC5 | TC-76-02/03/04; reused 06 | R1/R2/R3 direct HTTP; R4 navigation | Selected isolated/database HTTP tests PASS; browser/end-to-end not rerun. |

## RED execution record (historical)

RED commands ran from `backend/`, using the existing virtual environment and `-B` (no bytecode output). No database connections occurred in RED. GREEN is recorded separately below; historical counts are not added to its totals.

**1. Targeted SCRUM-76 checks:**

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_auth_unit.AuthHttpUnitTests.test_success_returns_token_and_stored_role tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_new_roles_cannot_read_unrelated_protected_information tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_new_roles_denied_writes_leave_state_and_side_effects_unchanged tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_safety_officer_lead_access_follows_stored_role_with_original_token
```

**Actual:** 4 methods passed, 0 failures/errors/skips, exit 0, unittest elapsed 0.383 seconds. Three methods are new; the existing successful-login method was extended for the two roles. Each method's subcases passed; method counts are not subcase counts.

**2. Small unchanged authorisation/Lead regression selection:**

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_lead_can_reassign_and_lock_is_requested tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_admin_and_current_coordinator_cannot_reassign tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_old_coordinator_loses_reads_and_writes_new_coordinator_gains_them tests.test_authorization_unit.EventPermissionTests.test_only_leads_can_reassign tests.test_authorization_unit.EventPermissionTests.test_new_role_preserves_its_legitimate_coordinator_information_access
```

**Actual:** 5 methods passed, 0 failures/errors/skips, exit 0, unittest elapsed 0.062 seconds. Existing `datetime.utcnow()` deprecation warnings appeared in successful assignment/decision routes; no unrelated fix was made.

| Classification | Actual result |
|---|---|
| PASS - behaviour already works | 9 distinct methods across the two commands. |
| Expected RED - missing SCRUM-76 functionality | None demonstrated; no artificial failure introduced. |
| Unexpected failure / defective setup | None. |
| Not run | Database-dependent integration/baseline, full suites, frontend/browser checks and conditional TC-76-05. Safety workflow tests are excluded, not a current RED failure. |

## GREEN verification and actual results

Executed 21 Oct 2026 (Singapore). Only the two commands below execute tests in this phase. **25 distinct methods passed, 0 failures, 0 errors, 0 skips**: 5 isolated and 20 local database-backed (including 2 baseline methods). No full suite or frontend tests ran. Existing short test JWT-key warnings appeared in the database run; no warning-related production changes were made.

### 1. Isolated new-role checks and original-role direct reads

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest -v tests.test_auth_unit.AuthHttpUnitTests.test_success_returns_token_and_stored_role tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_new_roles_cannot_read_unrelated_protected_information tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_new_roles_denied_writes_leave_state_and_side_effects_unchanged tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_safety_officer_lead_access_follows_stored_role_with_original_token tests.test_authorization_http_unit.AuthorizationHttpUnitTests.test_unrelated_organiser_and_attendee_direct_reads_are_denied
```

**Actual:** 5 passed, exit 0, unittest elapsed 0.394 seconds. Safety Officer/Lead login recognition, unrelated reads/writes, forged/stale role claims and stored-role changes pass. The last existing method verifies attendee/unrelated organiser/staff direct internal-read refusal.

### 2. Verified local database, existing Lead functions and persisted refusals

Before tests, a read-only probe verified effective target `('127.0.0.1', 5433, 'postgres', 'connectsphere_test')` and live `('postgres', 'connectsphere_test', 'public')`. The command below repeats both checks **in the same PowerShell/Python session as the database tests**, then guards every SQLAlchemy engine connection against a different target. It stops on verification failure or a failed group. The owner URL/password variables are set as requested; no owner connection is made.

The initial read-only `docker ps` attempt lacked Docker API permissions. Direct local PostgreSQL verification succeeded independently; no Docker configuration/reset or escalation was needed. Only the loopback test target was accessed. Model-column inspection is read-only; it does not migrate/rebuild the database or verify Supabase.

Exact command, from `backend/`:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://connectsphere_test:ci-only@127.0.0.1:5433/postgres'
$env:OWNER_DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:5433/postgres'
$env:TEST_ROLE_PASSWORD = 'ci-only'
@'
import sys
import unittest
from unittest import mock
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from app.config import TestConfig

expected = ('127.0.0.1', 5433, 'postgres', 'connectsphere_test')
def verify_url(url):
    url = make_url(url)
    assert (url.host, url.port, url.database, url.username) == expected, 'Non-local test engine refused'

verify_url(TestConfig.SQLALCHEMY_DATABASE_URI)
print('Effective test target:', expected, flush=True)
probe = create_engine(TestConfig.SQLALCHEMY_DATABASE_URI, connect_args={'connect_timeout': 5})
try:
    with probe.connect() as connection:
        actual = tuple(connection.execute(text('select current_database(), current_user, current_schema()')).one())
        print('Connected database/role/schema:', actual, flush=True)
        assert actual == ('postgres', 'connectsphere_test', 'public')
finally:
    probe.dispose()

original_connect, original_raw = Engine.connect, Engine.raw_connection
def local_connect(engine, *args, **kwargs):
    verify_url(engine.url)
    return original_connect(engine, *args, **kwargs)
def local_raw(engine, *args, **kwargs):
    verify_url(engine.url)
    return original_raw(engine, *args, **kwargs)

groups = {
    'Local baseline': [
        'tests.test_app_factory.AppFactoryTests.test_tests_run_as_the_restricted_role',
        'tests.test_app_factory.AppFactoryTests.test_database_tables_match_the_models',
    ],
    'Existing Lead functionality and boundaries': [
        'tests.test_unassigned_queue.QueueListTests.test_lead_sees_each_waiting_event_with_basic_information',
        'tests.test_unassigned_queue.AccessTests.test_only_leads_can_view_the_queue',
        'tests.test_lead_assign_coordinator.AssigningTests.test_lead_sees_the_waiting_event_and_eligible_coordinators',
        'tests.test_lead_assign_coordinator.AssigningTests.test_assignment_records_the_coordinator_the_lead_and_the_time',
        'tests.test_lead_assign_coordinator.AccessTests.test_only_leads_can_assign',
        'tests.test_lead_reassign_coordinator.ReassigningTests.test_reassignment_replaces_the_coordinator_and_records_the_lead_and_time',
        'tests.test_lead_reassign_coordinator.ReassigningTests.test_another_lead_can_reassign_and_the_event_moves_to_their_list',
        'tests.test_lead_reassign_coordinator.AccessTests.test_only_leads_can_reassign',
        'tests.test_lead_assigned_events.AssignedListTests.test_lead_sees_the_active_events_they_assigned',
        'tests.test_lead_assigned_events.OtherAssignersTests.test_filtering_never_reveals_another_leads_events',
        'tests.test_lead_assigned_events.AccessTests.test_only_leads_can_open_the_view',
    ],
    'Original-role regressions and persisted write refusals': [
        'tests.test_authorization.AuthorizationEvidenceTests.test_organiser_can_read_own_coordinator_but_not_unrelated_event_details',
        'tests.test_authorization.AuthorizationEvidenceTests.test_reassignment_moves_event_specific_read_and_write_privileges',
        'tests.test_authorization.AuthorizationEvidenceTests.test_unauthorized_reassignment_preserves_every_persisted_event_field',
        'tests.test_authorization.AuthorizationEvidenceTests.test_new_roles_cannot_modify_persisted_planning_information',
        'tests.test_authorization.AuthorizationEvidenceTests.test_attendee_direct_reads_do_not_disclose_internal_information',
        'tests.test_venue_catalogue.AddVenueTests.test_tc1_add_venue_with_every_detail',
        'tests.test_equipment_requirements.TechnicalSupportTests.test_tc_42_21_technical_support_update_the_arrangement',
    ],
}
with mock.patch.object(Engine, 'connect', local_connect), mock.patch.object(Engine, 'raw_connection', local_raw):
    for label, names in groups.items():
        print('\nGROUP:', label, flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        print('RESULT:', label, 'run=', result.testsRun, 'failures=', len(result.failures),
              'errors=', len(result.errors), 'skipped=', len(result.skipped), flush=True)
        if not result.wasSuccessful():
            sys.exit(1)
'@ | .\.venv\Scripts\python.exe -B -
```

**Actual:** exit 0. Baseline: **2 passed**, 0.090 seconds; Lead: **11 passed**, 0.319 seconds; original-role/persistence: **7 passed**, 0.265 seconds. No failures/errors/skips in any group. Counts are methods, not subcases; the read-only probes are not counted as tests.

| Verified area | Executed evidence / result |
|---|---|
| Lead queue | Positive waiting-request contents and non-Lead refusal: **2 PASS**. |
| Initial assignment and information | Real assignment detail/candidate read, saved coordinator/Lead/time and non-Lead read/write refusal: **3 PASS**. |
| Reassignment | Saved replacement/audit, another Lead's reassignment moving supervision, non-Lead refusal: **3 PASS**. |
| Supervised events | Own active-event list, no disclosure via another Lead's coordinator filter, non-Lead refusal: **3 PASS**. |
| Original roles | Organiser own/unrelated reads; coordinator privilege transfer; all original roles/admin denied reassignment without persisted field changes; attendee direct internal-read refusal; Venue Staff catalogue creation; Technical Support arrangement update: **6 PASS**. |
| New-role persisted refusal | Single added case, both Lead and Safety Officer subcases: **1 PASS**. Every Event column is reloaded and compared; notification count unchanged and no queued email. |
| Local baseline | Actual restricted role/schema and model-column parity on local PostgreSQL: **2 PASS**. |

**Evidence boundary:** new-role login and role-transition checks still use mocked user lookup; database-backed tests add actual persistence evidence for write refusals and actual working Lead/original-role functions. Tests insert only their fixtures and roll back outer transactions. This does not establish Supabase policies, remote schema parity or browser end-to-end behaviour. No further tests are required by a demonstrated defect; no production correction is proposed.

## Remaining questions and handoff

| ID | State / implication for GREEN |
|---|---|
| Q1 | Resolved: SCRUM-90/91/92 own next-sprint safety workflow; no implementation required here. |
| Q2 | Global assignment-list interpretation remains unconfirmed. Preserve explicit SCRUM-81/82/83 behaviour; do not expand it under GREEN without agreement. |
| Q3 | Safety-review event scope belongs to SCRUM-90/91/92, not this increment. |
| Q4 | General-detail creator access after a role change remains ambiguous. Any changed expectation/helper requires clarification with SCRUM-74 owner/customer first. |

**Branch files changed:** `backend/tests/test_auth_unit.py` and `backend/tests/test_authorization_http_unit.py` from RED; `backend/tests/test_authorization.py` adds the single GREEN persisted-state case; this test-case document. No other SCRUM documentation, production/frontend code, schema, dependencies, `.env` or CI configuration changed. No Supabase access, reset/migration, full-suite run, commit, push or PR occurred. Local restricted-role database access during GREEN is recorded below.

**Verdict: READY FOR PR** for the confirmed SCRUM-76 scope. GREEN verifies existing functionality without production changes. No genuine production defect requiring correction was found. Q2/Q4 do not authorise expanded Lead access or a changed creator policy; resolve them before any such separate change. Stopped after verification/documentation; no commit, push or PR created.
