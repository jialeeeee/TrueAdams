import { Route, Routes } from "react-router-dom";
import ClarificationPage from "./pages/ClarificationPage.jsx";
import DraftEventPage from "./pages/DraftEventPage.jsx";
import EventPlanningPage from "./pages/EventPlanningPage.jsx";
import EventRegistrationPage from "./pages/EventRegistrationPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ManagedEventsPage from "./pages/ManagedEventsPage.jsx";
import MyDraftsPage from "./pages/MyDraftsPage.jsx";
import MyEventRequestsPage from "./pages/MyEventRequestsPage.jsx";
import MyRequestsPage from "./pages/MyRequestsPage.jsx";
import RegistrationsPage from "./pages/RegistrationsPage.jsx";
import ResourcesPage from "./pages/ResourcesPage.jsx";
import ReviewRequestPage from "./pages/ReviewRequestPage.jsx";
import VenueAvailabilityPage from "./pages/VenueAvailabilityPage.jsx";
import VenueSearchPage from "./pages/VenueSearchPage.jsx";
import VenuesPage from "./pages/VenuesPage.jsx";

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<EventsPage />} />
        <Route path="/events/drafts" element={<MyDraftsPage />} />
        <Route path="/events/drafts/new" element={<DraftEventPage />} />
        <Route path="/events/drafts/:draftId" element={<DraftEventPage />} />
        <Route path="/events/requests" element={<MyRequestsPage />} />
        <Route path="/events/mine" element={<MyEventRequestsPage />} />
        <Route path="/events/managed" element={<ManagedEventsPage />} />
        <Route path="/events/:eventId/planning" element={<EventPlanningPage />} />
        <Route path="/events/:eventId/review" element={<ReviewRequestPage />} />
        <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
        <Route path="/events/:eventId/register" element={<EventRegistrationPage />} />
        <Route path="/venues" element={<VenuesPage />} />
        <Route path="/venues/availability" element={<VenueAvailabilityPage />} />
        <Route path="/venues/search" element={<VenueSearchPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/registrations" element={<RegistrationsPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </>
  );
}
