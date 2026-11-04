import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";

// SCRUM-63: the venue catalogue. Add and Edit are offered only when the server says the
// caller is Venue Staff (GET /venues/options is refused for everyone else), so the
// screen never decides roles itself.
export default function VenuesPage() {
  const [venues, setVenues] = useState([]);
  const [canEdit, setCanEdit] = useState(false);
  // CF08: Venue Staff can also list archived venues, to restore one.
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    apiClient.get("/venues/options").then(() => setCanEdit(true), () => setCanEdit(false));
  }, []);

  useEffect(() => {
    const listed = showArchived
      ? apiClient.get("/venues/", { params: { archived: "include" } })
      : apiClient.get("/venues/");
    listed.then((res) => setVenues(res.data.venues));
  }, [showArchived]);

  return (
    <section>
      <h1>Venues</h1>
      {canEdit && <Link to="/venues/new">Add venue</Link>}
      {canEdit && (
        <label>
          <input type="checkbox" checked={showArchived}
            onChange={(changed) => setShowArchived(changed.target.checked)} />
          Show archived venues
        </label>
      )}
      <ul>
        {venues.map((venue) => (
          <li key={venue.id}>
            {venue.archived_at ? `${venue.name} (archived)` : venue.name}
            {canEdit && <Link to={`/venues/${venue.id}/edit`} aria-label={`Edit ${venue.name}`}>Edit</Link>}
            {canEdit && (
              <Link to={`/venues/${venue.id}/unavailable`}
                aria-label={`Record unavailable period for ${venue.name}`}>
                Record unavailable period
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
