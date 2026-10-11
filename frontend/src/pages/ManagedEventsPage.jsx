import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import statusLabel from "../utils/statusLabel.js";

// The events the coordinator manages, each opening its planning view (SCRUM-62).
const NOT_LOADED = "Your managed events could not be loaded. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";

// Proposed dates are Singapore time without a time zone: show them as recorded.
function proposedDate(value) {
  return value ? value.slice(0, 16).replace("T", " ") : NOT_RECORDED;
}

export default function ManagedEventsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/managed");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(typeof error === "string" && error.trim() ? error : NOT_LOADED);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>My managed events</h1>

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
              <Link to={`/events/${event.id}/planning`}>{event.title || NOT_RECORDED}</Link>
              <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
              <p>{`Status: ${statusLabel(event.status)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
