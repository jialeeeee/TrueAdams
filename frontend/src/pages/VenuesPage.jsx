import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import VenueDetails from "../utils/VenueDetails.jsx";

// SCRUM-35 AC5: shown when the server sent no message of its own.
const LIST_NOT_LOADED = "Venues could not be loaded. Check your connection and try again.";
const DETAILS_NOT_LOADED = "Venue details could not be loaded. Please try again.";

// SCRUM-35 AC1-AC3, AC5: one venue, and its details on request.
function VenueItem({ venue, canEdit }) {
  const [details, setDetails] = useState(null);
  const [detailsError, setDetailsError] = useState("");

  const showDetails = async () => {
    setDetailsError("");
    try {
      const response = await apiClient.get(`/venues/${venue.id}`);
      setDetails(response.data);
    } catch (failure) {
      setDetailsError(explain(failure, DETAILS_NOT_LOADED));
    }
  };

  return (
    <li aria-label={venue.name}>
      <strong>{venue.archived_at ? `${venue.name} (deleted)` : venue.name}</strong>
      {/* The actions get a line of their own, apart from the name. */}
      {canEdit && (
        <p>
          <Link to={`/venues/${venue.id}/edit`} aria-label={`Edit ${venue.name}`}>Edit</Link>
          <Link to={`/venues/${venue.id}/unavailable`}
            aria-label={`Record unavailable period for ${venue.name}`}>
            Record unavailable period
          </Link>
        </p>
      )}
      <p>Location: {venue.location ?? "Not recorded"}</p>
      <p>Capacity: {venue.capacity ?? "Not recorded"}</p>
      {details ? <VenueDetails details={details} />
        : <button type="button" onClick={showDetails}>View details</button>}
      {detailsError && <p role="alert">{detailsError}</p>}
    </li>
  );
}

// SCRUM-63: the venue catalogue. Add and Edit are offered only when the server says the
// caller is Venue Staff (GET /venues/options is refused for everyone else), so the
// screen never decides roles itself.
export default function VenuesPage() {
  const [venues, setVenues] = useState([]);
  // SCRUM-35 AC4: the server's empty-state text, shown when no venues are recorded.
  const [emptyMessage, setEmptyMessage] = useState(null);
  // SCRUM-35 AC5: a failed load is an error, never an empty list.
  const [loadError, setLoadError] = useState(null);
  const [attempt, setAttempt] = useState(0);
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
    listed.then((res) => {
      setLoadError(null);
      setVenues(res.data.venues);
      setEmptyMessage(res.data.message);
    }, (failure) => {
      setVenues([]);
      setEmptyMessage(null);
      setLoadError({ message: explain(failure, LIST_NOT_LOADED), retry: canRetry(failure) });
    });
  }, [showArchived, attempt]);

  return (
    <section>
      <h1>Venues</h1>
      {canEdit && <Link to="/venues/new">Add venue</Link>}
      {canEdit && (
        <label>
          <input type="checkbox" checked={showArchived}
            onChange={(changed) => setShowArchived(changed.target.checked)} />
          Show deleted venues
        </label>
      )}
      {loadError && <p role="alert">{loadError.message}</p>}
      {loadError?.retry && (
        <button type="button" onClick={() => setAttempt((count) => count + 1)}>Try again</button>
      )}
      {emptyMessage && <p>{emptyMessage}</p>}
      <ul>
        {venues.map((venue) => <VenueItem key={venue.id} venue={venue} canEdit={canEdit} />)}
      </ul>
    </section>
  );
}
