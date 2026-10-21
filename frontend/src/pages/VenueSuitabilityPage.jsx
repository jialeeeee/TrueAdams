import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";

// SCRUM-38: the event's coordinator checks a venue against the event's saved requirements.
// Talks to GET /api/events/<id>/venue-suitability?venue_id= (backend/app/events/routes.py).
// The check only reports; it never books or requests a venue.
const NOT_LOADED = "The venues could not be loaded. Check your connection and try again.";
const NOT_CHECKED = "The check could not be completed. Check your connection and try again.";
const SELECT_VENUE = "Select a venue to check.";
const STATUS_LABELS = {
  match: "Match",
  mismatch: "Mismatch",
  unable_to_assess: "Unable to assess",
  not_required: "Not required",
};
const OVERALL_HEADINGS = {
  meets: "Meets the checked requirements",
  does_not_meet: "Does not meet all the checked requirements",
  unable_to_assess: "Could not be fully assessed",
};

export default function VenueSuitabilityPage() {
  const { eventId } = useParams();
  const [venues, setVenues] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [venueId, setVenueId] = useState("");
  const [problem, setProblem] = useState("");
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const load = async () => {
    setLoadError(null);
    try {
      setVenues((await apiClient.get("/venues/")).data.venues);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  };

  useEffect(() => {
    load();
  }, []);

  const run = async (e) => {
    e.preventDefault();
    setProblem("");
    if (!venueId) {
      setResult(null);
      setProblem(SELECT_VENUE);
      return;
    }
    setRunning(true);
    try {
      const response = await apiClient.get(`/events/${eventId}/venue-suitability`, {
        params: { venue_id: venueId },
      });
      setResult(response.data);
    } catch (failure) {
      // An old result is never left showing beside a failure.
      setResult(null);
      setProblem(explain(failure, NOT_CHECKED));
    } finally {
      setRunning(false);
    }
  };

  const back = <Link to={`/events/${eventId}/planning`}>Back to the event</Link>;

  if (loadError) {
    return (
      <section>
        {back}
        <h1>Check venue suitability</h1>
        <p role="alert">{loadError.message}</p>
        {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
      </section>
    );
  }
  if (!venues) return <p>Loading…</p>;

  return (
    <section>
      {back}
      <h1>Check venue suitability</h1>
      <form onSubmit={run} noValidate>
        <label htmlFor="suitability-venue">Venue</label>
        <select id="suitability-venue" value={venueId} onChange={(e) => setVenueId(e.target.value)}>
          <option value="">Choose a venue</option>
          {venues.map((venue) => (
            <option key={venue.id} value={String(venue.id)}>{venue.name}</option>
          ))}
        </select>
        <button type="submit" disabled={running}>Run check</button>
      </form>
      {problem && <p role="alert">{problem}</p>}

      {result && (
        <div aria-label="Suitability result">
          <h2>{`${result.event.title} at ${result.venue.name}`}</h2>
          <ul aria-label="Checked requirements">
            {result.checks.map((check) => (
              <li key={check.label}>
                <strong>{`${check.label}: ${STATUS_LABELS[check.status]}`}</strong>
                {` — ${check.detail}`}
              </li>
            ))}
          </ul>
          <h3>{OVERALL_HEADINGS[result.overall]}</h3>
          <p>{result.summary}</p>
          <p>This check does not book the venue or send a venue request.</p>
        </div>
      )}
    </section>
  );
}
