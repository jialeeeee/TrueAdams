import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import apiClient from "./api/client.js";
import AssignCoordinatorPage from "./pages/AssignCoordinatorPage.jsx";
import ChangeRequestPage from "./pages/ChangeRequestPage.jsx";
import ChangeRequestReviewPage from "./pages/ChangeRequestReviewPage.jsx";
import ChangeRequestsToReviewPage from "./pages/ChangeRequestsToReviewPage.jsx";
import ClarificationPage from "./pages/ClarificationPage.jsx";
import DraftEventPage from "./pages/DraftEventPage.jsx";
import EquipmentAvailabilityPage from "./pages/EquipmentAvailabilityPage.jsx";
import EquipmentRequestsPage from "./pages/EquipmentRequestsPage.jsx";
import EquipmentRequirementsPage from "./pages/EquipmentRequirementsPage.jsx";
import EquipmentReservationPage from "./pages/EquipmentReservationPage.jsx";
import EventDetailsPage from "./pages/EventDetailsPage.jsx";
import EventPlanningPage from "./pages/EventPlanningPage.jsx";
import EventRegistrationPage from "./pages/EventRegistrationPage.jsx";
import EventRegistrationsPage from "./pages/EventRegistrationsPage.jsx";
import EventsCalendarPage from "./pages/EventsCalendarPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import LeadAssignedEventsPage from "./pages/LeadAssignedEventsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ManagedEventsPage from "./pages/ManagedEventsPage.jsx";
import ManagedRegistrationsPage from "./pages/ManagedRegistrationsPage.jsx";
import MyDraftsPage from "./pages/MyDraftsPage.jsx";
import MyEventRequestsPage from "./pages/MyEventRequestsPage.jsx";
import MyRegistrationsPage from "./pages/MyRegistrationsPage.jsx";
import MyRequestsPage from "./pages/MyRequestsPage.jsx";
import NotificationsPage from "./pages/NotificationsPage.jsx";
import OrganisedEventsPage from "./pages/OrganisedEventsPage.jsx";
import { ROLE_KEY, ROLES_KEY } from "./pages/LoginPage.jsx";
import ReassignCoordinatorPage from "./pages/ReassignCoordinatorPage.jsx";
import ReassignmentRequestPage from "./pages/ReassignmentRequestPage.jsx";
import RegistrationOverviewPage from "./pages/RegistrationOverviewPage.jsx";
import RegistrationSettingsPage from "./pages/RegistrationSettingsPage.jsx";
import ReviewRequestPage from "./pages/ReviewRequestPage.jsx";
import ReviewRequestsPage from "./pages/ReviewRequestsPage.jsx";
import SafetyCheckQueuePage from "./pages/SafetyCheckQueuePage.jsx";
import TentativeHoldsPage from "./pages/TentativeHoldsPage.jsx";
import UnassignedQueuePage from "./pages/UnassignedQueuePage.jsx";
import VenueAvailabilityPage from "./pages/VenueAvailabilityPage.jsx";
import VenueBookingRequestPage from "./pages/VenueBookingRequestPage.jsx";
import FlaggedBookingsPage from "./pages/FlaggedBookingsPage.jsx";
import ReplacementNeededPage from "./pages/ReplacementNeededPage.jsx";
import VenueUnavailablePage from "./pages/VenueUnavailablePage.jsx";
import VenueBookingRequestsPage from "./pages/VenueBookingRequestsPage.jsx";
import ReplacementVenuePage from "./pages/ReplacementVenuePage.jsx";
import VenueSearchPage from "./pages/VenueSearchPage.jsx";
import VenueFormPage from "./pages/VenueFormPage.jsx";
import VenueSuitabilityPage from "./pages/VenueSuitabilityPage.jsx";
import VenuesPage from "./pages/VenuesPage.jsx";

// Each nav link and the roles whose pages it opens, from the role checks of the endpoint
// each page loads; null means every role. This only tidies the menu: the backend still
// refuses anyone else, so a role it doesn't know (or none) sees every link, as before.
// A user with several roles (CF01) sees the links of each of them.
// The menu's groups, in display order. Each link below names its group; links of one group
// are listed together, so the menu keeps the order of NAV_LINKS.
const OVERVIEW = "Overview";
const ORGANISING = "My events";
const COORDINATION = "Coordination";
const SAFETY = "Safety";
const VENUES = "Venues and planning";
const EQUIPMENT = "Equipment";
const ATTENDING = "Attending";
const NAV_LINKS = [
  ["/", "Events", null, OVERVIEW],
  ["/notifications", "Notifications", null, OVERVIEW],
  ["/events/mine", "My event requests", ["organiser"], ORGANISING],
  ["/events/drafts", "My drafts", ["organiser"], ORGANISING],
  ["/events/requests", "My requests", ["organiser"], ORGANISING],
  ["/events/organised", "Registrations for my events", ["organiser"], ORGANISING],
  ["/events/managed", "My managed events", ["coordinator"], COORDINATION],
  ["/events/managed/registrations", "Registrations for my managed events", ["coordinator"], COORDINATION],
  ["/events/queue", "Waiting events", ["coordinator_lead"], COORDINATION],
  ["/events/supervised", "Events I assigned", ["coordinator_lead"], COORDINATION],
  ["/events/review-requests", "Requests for review", ["coordinator"], COORDINATION],
  ["/events/change-requests", "Change requests to review", ["coordinator"], COORDINATION],
  ["/events/safety-checks", "Safety checks", ["safety_officer"], SAFETY],
  ["/venues", "Venues", ["coordinator", "venue_staff"], VENUES],
  ["/venues/availability", "Venue availability", ["coordinator", "venue_staff"], VENUES],
  // CF09: one calendar of all events, for planning.
  ["/events/calendar", "Events calendar", ["coordinator", "venue_staff", "tech_staff"], VENUES],
  ["/venues/search", "Venue search", ["coordinator"], VENUES],
  ["/venues/bookings", "Venue booking requests", ["venue_staff"], VENUES],
  ["/venues/holds", "Tentative holds", ["venue_staff"], VENUES],
  ["/venues/flagged-bookings", "Setup or turnaround conflicts", ["venue_staff"], VENUES],
  ["/venues/replacement-needed", "Replacement venues needed", ["venue_staff"], VENUES],
  ["/equipment-requests", "Equipment requests", ["tech_staff"], EQUIPMENT],
  ["/my-registrations", "My registrations", ["attendee"], ATTENDING],
];
const KNOWN_ROLES = new Set(NAV_LINKS.flatMap(([, , roles]) => roles ?? []));

function visibleLinks(userRoles) {
  const known = userRoles.filter((role) => KNOWN_ROLES.has(role));
  if (!known.length) return NAV_LINKS;
  return NAV_LINKS.filter(([, , roles]) => roles === null || roles.some((role) => known.includes(role)));
}

// The visible links in groups, keeping their order: a new group starts when the group changes.
function groupLinks(links) {
  const groups = [];
  for (const link of links) {
    const last = groups[groups.length - 1];
    if (last && last.name === link[3]) last.links.push(link);
    else groups.push({ name: link[3], links: [link] });
  }
  return groups;
}

// How each role is named in the header. A role this list doesn't know is shown as stored.
const ROLE_LABELS = {
  admin: "Administrator",
  attendee: "Attendee",
  coordinator: "Event Coordinator",
  coordinator_lead: "Coordinator Lead",
  organiser: "Event Organiser",
  safety_officer: "Safety Officer",
  tech_staff: "Technical Support",
  venue_staff: "Venue Staff",
};

// The signed-in user's roles from the login reply. A session from before CF01, or one
// whose list can't be read, falls back to its main role.
function storedRoles() {
  try {
    const roles = JSON.parse(sessionStorage.getItem(ROLES_KEY));
    if (Array.isArray(roles)) return roles;
  } catch {
    // Not JSON: use the main role below.
  }
  const role = sessionStorage.getItem(ROLE_KEY);
  return role ? [role] : [];
}

function RequireSignIn() {
  return sessionStorage.getItem("access_token") ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  // Re-read the active session when login/logout or navigation changes location.
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const signedIn = Boolean(sessionStorage.getItem("access_token"));
  const roles = signedIn ? storedRoles() : [];
  // SCRUM-75 AC6: login submissions and logout supersede pending login responses.
  const loginAttempt = useRef(0);
  // On small screens the menu is hidden behind the Menu button; opening a page closes it.
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);

  const signOut = () => {
    loginAttempt.current += 1;
    const token = sessionStorage.getItem("access_token");
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem(ROLE_KEY);
    sessionStorage.removeItem(ROLES_KEY);
    navigate("/login", { replace: true });
    // SCRUM-75 AC6: the server refuses this token from now on. The browser has forgotten
    // it either way, so a failure here never keeps anyone signed in.
    if (token) {
      apiClient.post("/auth/logout", {}, { signingOutToken: token }).catch(() => {});
    }
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="app-header">
        {signedIn && (
          <button type="button" className="menu-toggle" aria-expanded={menuOpen}
            aria-controls="primary-nav" onClick={() => setMenuOpen((open) => !open)}>
            Menu
          </button>
        )}
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true" />
          ConnectSphere
        </Link>
        <div className="header-user">
          {/* Groups, not lists: page tests look for the page's own list items. */}
          {roles.length > 0 && (
            <div className="role-badges" role="group" aria-label="Your roles">
              {roles.map((role) => <span key={role}>{ROLE_LABELS[role] ?? role}</span>)}
            </div>
          )}
          {signedIn
            ? <button type="button" className="button-quiet" onClick={signOut}>Sign out</button>
            : <Link to="/login" className="button-link">Login</Link>}
        </div>
      </header>
      <div className={signedIn ? "app-body" : "app-body signed-out"}>
        {/* Signed out, every page but Login sends the visitor to Login, so there is no menu. */}
        {signedIn && (
          <nav id="primary-nav" aria-label="Main" className={menuOpen ? "side-nav open" : "side-nav"}>
            {groupLinks(visibleLinks(roles)).map((group, index) => (
              <div key={group.name} className="nav-group" role="group" aria-labelledby={`nav-group-${index}`}>
                <p className="nav-group-title" id={`nav-group-${index}`}>{group.name}</p>
                {group.links.map(([path, label]) => <NavLink key={path} to={path} end>{label}</NavLink>)}
              </div>
            ))}
          </nav>
        )}
        <main id="main" className="content" tabIndex={-1}>
      <Routes>
        <Route path="/login" element={<LoginPage loginAttempt={loginAttempt} />} />
        <Route element={<RequireSignIn />}>
          <Route path="/" element={<EventsPage />} />
          <Route path="/events/drafts" element={<MyDraftsPage />} />
          <Route path="/events/drafts/new" element={<DraftEventPage />} />
          <Route path="/events/drafts/:draftId" element={<DraftEventPage />} />
          <Route path="/events/requests" element={<MyRequestsPage />} />
          <Route path="/events/mine" element={<MyEventRequestsPage />} />
          <Route path="/events/managed" element={<ManagedEventsPage />} />
          <Route path="/events/managed/registrations" element={<ManagedRegistrationsPage />} />
          <Route path="/events/organised" element={<OrganisedEventsPage />} />
          <Route path="/events/supervised" element={<LeadAssignedEventsPage />} />
          <Route path="/events/queue" element={<UnassignedQueuePage />} />
          <Route path="/events/review-requests" element={<ReviewRequestsPage />} />
          <Route path="/events/change-requests" element={<ChangeRequestsToReviewPage />} />
          <Route path="/events/safety-checks" element={<SafetyCheckQueuePage />} />
          <Route path="/events/calendar" element={<EventsCalendarPage />} />
          <Route path="/events/:eventId" element={<EventDetailsPage />} />
          <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
          <Route path="/events/:eventId/review" element={<ReviewRequestPage />} />
          <Route path="/events/:eventId/change-request" element={<ChangeRequestPage />} />
          <Route path="/events/:eventId/change-requests/:requestId" element={<ChangeRequestReviewPage />} />
          <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
          <Route path="/events/:eventId/register" element={<EventRegistrationPage />} />
          <Route path="/events/:eventId/registrations" element={<EventRegistrationsPage />} />
          <Route path="/events/:eventId/registration-overview" element={<RegistrationOverviewPage />} />
          <Route path="/events/:eventId/registration-settings" element={<RegistrationSettingsPage />} />
          <Route path="/events/:eventId/venue-request" element={<VenueBookingRequestPage />} />
          <Route path="/events/:eventId/venue-suitability" element={<VenueSuitabilityPage />} />
          <Route path="/events/:eventId/equipment" element={<EquipmentRequirementsPage />} />
          <Route path="/events/:eventId/equipment-availability" element={<EquipmentAvailabilityPage />} />
          <Route path="/events/:eventId/equipment-reservations" element={<EquipmentReservationPage />} />
          <Route path="/events/:eventId/reassign" element={<ReassignmentRequestPage />} />
          <Route path="/events/:eventId/assign" element={<AssignCoordinatorPage />} />
          <Route path="/events/:eventId/change-coordinator" element={<ReassignCoordinatorPage />} />
          <Route path="/bookings/:bookingId/replacement" element={<ReplacementVenuePage />} />
          <Route path="/venues" element={<VenuesPage />} />
          <Route path="/venues/new" element={<VenueFormPage />} />
          <Route path="/venues/:venueId/edit" element={<VenueFormPage />} />
          <Route path="/venues/availability" element={<VenueAvailabilityPage />} />
          <Route path="/venues/search" element={<VenueSearchPage />} />
          <Route path="/venues/bookings" element={<VenueBookingRequestsPage />} />
          <Route path="/venues/holds" element={<TentativeHoldsPage />} />
          <Route path="/venues/flagged-bookings" element={<FlaggedBookingsPage />} />
          <Route path="/venues/replacement-needed" element={<ReplacementNeededPage />} />
          <Route path="/venues/:venueId/unavailable" element={<VenueUnavailablePage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/equipment-requests" element={<EquipmentRequestsPage />} />
          <Route path="/my-registrations" element={<MyRegistrationsPage />} />
          <Route path="/registrations" element={<Navigate to="/my-registrations" replace />} />
        </Route>
      </Routes>
        </main>
      </div>
    </div>
  );
}
