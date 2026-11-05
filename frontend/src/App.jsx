import { useRef } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
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
const NAV_LINKS = [
  ["/", "Events", null],
  ["/notifications", "Notifications", null],
  ["/events/mine", "My event requests", ["organiser"]],
  ["/events/drafts", "My drafts", ["organiser"]],
  ["/events/requests", "My requests", ["organiser"]],
  ["/events/organised", "Registrations for my events", ["organiser"]],
  ["/events/managed", "My managed events", ["coordinator"]],
  ["/events/managed/registrations", "Registrations for my managed events", ["coordinator"]],
  ["/events/queue", "Waiting events", ["coordinator_lead"]],
  ["/events/supervised", "Events I assigned", ["coordinator_lead"]],
  ["/events/review-requests", "Requests for review", ["coordinator"]],
  ["/events/change-requests", "Change requests to review", ["coordinator"]],
  ["/events/safety-checks", "Safety checks", ["safety_officer"]],
  ["/venues", "Venues", ["coordinator", "venue_staff"]],
  ["/venues/availability", "Venue availability", ["coordinator", "venue_staff"]],
  // CF09: one calendar of all events, for planning.
  ["/events/calendar", "Events calendar", ["coordinator", "venue_staff", "tech_staff"]],
  ["/venues/search", "Venue search", ["coordinator"]],
  ["/venues/bookings", "Venue booking requests", ["venue_staff"]],
  ["/venues/holds", "Tentative holds", ["venue_staff"]],
  ["/venues/flagged-bookings", "Setup or turnaround conflicts", ["venue_staff"]],
  ["/venues/replacement-needed", "Replacement venues needed", ["venue_staff"]],
  ["/equipment-requests", "Equipment requests", ["tech_staff"]],
  ["/my-registrations", "My registrations", ["attendee"]],
];
const KNOWN_ROLES = new Set(NAV_LINKS.flatMap(([, , roles]) => roles ?? []));

function visibleLinks(userRoles) {
  const known = userRoles.filter((role) => KNOWN_ROLES.has(role));
  if (!known.length) return NAV_LINKS;
  return NAV_LINKS.filter(([, , roles]) => roles === null || roles.some((role) => known.includes(role)));
}

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
  useLocation();
  const navigate = useNavigate();
  const signedIn = Boolean(sessionStorage.getItem("access_token"));
  const roles = signedIn ? storedRoles() : [];
  // SCRUM-75 AC6: login submissions and logout supersede pending login responses.
  const loginAttempt = useRef(0);

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
    <div>
      <nav>
        {visibleLinks(roles).map(([path, label]) => (
          <Link key={path} to={path}>{label}</Link>
        ))}
        {signedIn ? <button type="button" onClick={signOut}>Sign out</button> : <Link to="/login">Login</Link>}
      </nav>
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
    </div>
  );
}
