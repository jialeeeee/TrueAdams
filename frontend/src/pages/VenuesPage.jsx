import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";

// SCRUM-63: the venue catalogue. Add and Edit are offered only when the server says the
// caller is Venue Staff (GET /venues/options is refused for everyone else), so the
// screen never decides roles itself.
export default function VenuesPage() {
  const [venues, setVenues] = useState([]);
  const [canEdit, setCanEdit] = useState(false);

  useEffect(() => {
    apiClient.get("/venues/").then((res) => setVenues(res.data.venues ?? res.data));
    apiClient.get("/venues/options").then(() => setCanEdit(true), () => setCanEdit(false));
  }, []);

  return (
    <section>
      <h1>Venues</h1>
      {canEdit && <Link to="/venues/new">Add venue</Link>}
      <ul>
        {venues.map((venue) => (
          <li key={venue.id}>
            {venue.name}
            {canEdit && <Link to={`/venues/${venue.id}/edit`} aria-label={`Edit ${venue.name}`}>Edit</Link>}
          </li>
        ))}
      </ul>
    </section>
  );
}
