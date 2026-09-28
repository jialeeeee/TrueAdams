import { Link, Route, Routes } from "react-router-dom";
import ClarificationPage from "./pages/ClarificationPage.jsx";
import DraftEventPage from "./pages/DraftEventPage.jsx";
import EventsPage from "./pages/EventsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MyDraftsPage from "./pages/MyDraftsPage.jsx";
import RegistrationsPage from "./pages/RegistrationsPage.jsx";
import ResourcesPage from "./pages/ResourcesPage.jsx";
import VenuesPage from "./pages/VenuesPage.jsx";

export default function App() {
  return (
    <div>
      <nav>
        <Link to="/">Events</Link>
        <Link to="/events/drafts">My drafts</Link>
        <Link to="/venues">Venues</Link>
        <Link to="/resources">Resources</Link>
        <Link to="/registrations">Registrations</Link>
        <Link to="/login">Login</Link>
      </nav>
      <Routes>
        <Route path="/" element={<EventsPage />} />
        <Route path="/events/drafts" element={<MyDraftsPage />} />
        <Route path="/events/drafts/new" element={<DraftEventPage />} />
        <Route path="/events/drafts/:draftId" element={<DraftEventPage />} />
        <Route path="/events/:eventId/clarifications" element={<ClarificationPage />} />
        <Route path="/venues" element={<VenuesPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/registrations" element={<RegistrationsPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </div>
  );
}
