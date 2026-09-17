import { Link, Route, Routes } from "react-router-dom";
import EventsPage from "./pages/EventsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import RegistrationsPage from "./pages/RegistrationsPage.jsx";
import ResourcesPage from "./pages/ResourcesPage.jsx";
import VenuesPage from "./pages/VenuesPage.jsx";

export default function App() {
  return (
    <div>
      <nav>
        <Link to="/">Events</Link>
        <Link to="/venues">Venues</Link>
        <Link to="/resources">Resources</Link>
        <Link to="/registrations">Registrations</Link>
        <Link to="/login">Login</Link>
      </nav>
      <Routes>
        <Route path="/" element={<EventsPage />} />
        <Route path="/venues" element={<VenuesPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/registrations" element={<RegistrationsPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </div>
  );
}
