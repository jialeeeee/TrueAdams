import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import proposedDate from "../utils/proposedDate.js";
import registrationSummary from "../utils/registrationSummary.js";
import statusLabel from "../utils/statusLabel.js";

// The organiser's events with their registration summary, each opening its
// registrations (SCRUM-54 AC1, AC2).
const NOT_LOADED =
  "Your events' registration information could not be loaded. Check your connection and try again.";

export default function OrganisedEventsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/organised");
      setResult(response.data);
    } catch (failure) {
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Registrations for my events</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}

      {result && result.events.length === 0 && <p>{result.message}</p>}
      {result && result.events.length > 0 && (
        <ul>
          {result.events.map((event) => (
            <li key={event.id}>
              <Link to={`/events/${event.id}/registrations`}>{event.title || "Not recorded"}</Link>
              <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
              <p>{`Status: ${statusLabel(event.status)}`}</p>
              {registrationSummary(event.registration).map((line) => <p key={line}>{line}</p>)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
