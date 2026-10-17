import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";

export default function UnassignedQueuePage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get("/events/queue");
      setResult(response.data);
    } catch (failure) {
      setResult(null);
      const error = failure.response?.data?.error;
      setLoadError({
        message: typeof error === "string" && error.trim()
          ? error
          : "The queue could not be loaded. Check your connection and try again.",
        retryable: !failure.response || failure.response.data?.retryable === true,
      });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Waiting events</h1>
      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}
      {result && result.events.length === 0 && <p>{result.message}</p>}
      {result && result.events.length > 0 && (
        <ul>
          {result.events.map((event) => (
            <li key={event.id}>
              <Link to={`/events/${event.id}/assign`}>{event.title || "Not recorded"}</Link>
              <p>{`Organiser: ${event.organiser.email}`}</p>
              <p>{`Proposed date: ${event.start_time ? event.start_time.slice(0, 16).replace("T", " ") : "Not recorded"}`}</p>
              <p>{`Submitted: ${event.submitted_at ? formatSavedAt(event.submitted_at) : "Not recorded"}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
