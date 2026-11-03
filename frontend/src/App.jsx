import { useRef } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
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
import { ROLE_KEY } from "./pages/LoginPage.jsx";
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
  ["/venues/search", "Venue search", ["coordinator"]],
  ["/venues/bookings", "Venue booking requests", ["venue_staff"]],
  ["/venues/holds", "Tentative holds", ["venue_staff"]],
  ["/venues/flagged-bookings", "Setup or turnaround conflicts", ["venue_staff"]],
  ["/venues/replacement-needed", "Replacement venues needed", ["venue_staff"]],
  ["/equipment-requests", "Equipment requests", ["tech_staff"]],
  ["/my-registrations", "My registrations", ["attendee"]],
];
const KNOWN_ROLES = new Set(NAV_LINKS.flatMap(([, , roles]) => roles ?? []));

function visibleLinks(role) {
  if (!KNOWN_ROLES.has(role)) return NAV_LINKS;
  return NAV_LINKS.filter(([, , roles]) => roles === null || roles.includes(role));
}

function RequireSignIn() {
  return sessionStorage.getItem("access_token") ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  // Re-read the active session when login/logout or navigation changes location.
  useLocation();
  const navigate = useNavigate();
  const signedIn = Boolean(sessionStorage.getItem("access_token"));
  const role = signedIn ? sessionStorage.getItem(ROLE_KEY) : null;
  // SCRUM-75 AC6: login submissions and logout supersede pending login responses.
  const loginAttempt = useRef(0);

  const signOut = () => {
    loginAttempt.current += 1;
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem(ROLE_KEY);
    navigate("/login", { replace: true });
  };

  return (
    <div>
      <nav>
        {visibleLinks(role).map(([path, label]) => (
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
