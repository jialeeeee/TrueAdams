import { useRef } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import AssignCoordinatorPage from "./pages/AssignCoordinatorPage.jsx";
import ClarificationPage from "./pages/ClarificationPage.jsx";
import DraftEventPage from "./pages/DraftEventPage.jsx";
import EventDetailsPage from "./pages/EventDetailsPage.jsx";
import EventPlanningPage from "./pages/EventPlanningPage.jsx";
import EventRegistrationPage from "./pages/EventRegistrationPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import LeadAssignedEventsPage from "./pages/LeadAssignedEventsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ManagedEventsPage from "./pages/ManagedEventsPage.jsx";
import MyDraftsPage from "./pages/MyDraftsPage.jsx";
import MyEventRequestsPage from "./pages/MyEventRequestsPage.jsx";
import MyRegistrationsPage from "./pages/MyRegistrationsPage.jsx";
import MyRequestsPage from "./pages/MyRequestsPage.jsx";
import ResourcesPage from "./pages/ResourcesPage.jsx";
import ReassignCoordinatorPage from "./pages/ReassignCoordinatorPage.jsx";
import ReassignmentRequestPage from "./pages/ReassignmentRequestPage.jsx";
import RegistrationSettingsPage from "./pages/RegistrationSettingsPage.jsx";
import ReviewRequestPage from "./pages/ReviewRequestPage.jsx";
import ReviewRequestsPage from "./pages/ReviewRequestsPage.jsx";
import TentativeHoldsPage from "./pages/TentativeHoldsPage.jsx";
import UnassignedQueuePage from "./pages/UnassignedQueuePage.jsx";
import VenueAvailabilityPage from "./pages/VenueAvailabilityPage.jsx";
import VenueBookingRequestPage from "./pages/VenueBookingRequestPage.jsx";
import VenueBookingRequestsPage from "./pages/VenueBookingRequestsPage.jsx";
import VenueSearchPage from "./pages/VenueSearchPage.jsx";
import VenuesPage from "./pages/VenuesPage.jsx";

function RequireSignIn() {
  return sessionStorage.getItem("access_token") ? <Outlet /> : <Navigate to="/login" replace />;
}

export default function App() {
  // Re-read the active session when login/logout or navigation changes location.
  useLocation();
  const navigate = useNavigate();
  const signedIn = Boolean(sessionStorage.getItem("access_token"));
  // SCRUM-75 AC6: login submissions and logout supersede pending login responses.
  const loginAttempt = useRef(0);

  const signOut = () => {
    loginAttempt.current += 1;
    sessionStorage.removeItem("access_token");
    navigate("/login", { replace: true });
  };

  return (
    <div>
      <nav>
        <Link to="/">Events</Link>
        <Link to="/events/mine">My event requests</Link>
        <Link to="/events/drafts">My drafts</Link>
        <Link to="/events/requests">My requests</Link>
        <Link to="/events/managed">My managed events</Link>
        <Link to="/events/queue">Waiting events</Link>
        <Link to="/events/supervised">Events I assigned</Link>
        <Link to="/events/review-requests">Requests for review</Link>
        <Link to="/venues">Venues</Link>
        <Link to="/venues/availability">Venue availability</Link>
        <Link to="/venues/search">Venue search</Link>
        <Link to="/venues/bookings">Venue booking requests</Link>
        <Link to="/venues/holds">Tentative holds</Link>
        <Link to="/resources">Resources</Link>
        <Link to="/my-registrations">My registrations</Link>
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
          <Route path="/events/supervised" element={<LeadAssignedEventsPage />} />
          <Route path="/events/queue" element={<UnassignedQueuePage />} />
          <Route path="/events/review-requests" element={<ReviewRequestsPage />} />
          <Route path="/events/:eventId" element={<EventDetailsPage />} />
          <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
          <Route path="/events/:eventId/review" element={<ReviewRequestPage />} />
          <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
          <Route path="/events/:eventId/register" element={<EventRegistrationPage />} />
          <Route path="/events/:eventId/registration-settings" element={<RegistrationSettingsPage />} />
          <Route path="/events/:eventId/venue-request" element={<VenueBookingRequestPage />} />
          <Route path="/events/:eventId/reassign" element={<ReassignmentRequestPage />} />
          <Route path="/events/:eventId/assign" element={<AssignCoordinatorPage />} />
          <Route path="/events/:eventId/change-coordinator" element={<ReassignCoordinatorPage />} />
          <Route path="/venues" element={<VenuesPage />} />
          <Route path="/venues/availability" element={<VenueAvailabilityPage />} />
          <Route path="/venues/search" element={<VenueSearchPage />} />
          <Route path="/venues/bookings" element={<VenueBookingRequestsPage />} />
          <Route path="/venues/holds" element={<TentativeHoldsPage />} />
          <Route path="/resources" element={<ResourcesPage />} />
          <Route path="/my-registrations" element={<MyRegistrationsPage />} />
          <Route path="/registrations" element={<Navigate to="/my-registrations" replace />} />
        </Route>
      </Routes>
    </div>
  );
}
