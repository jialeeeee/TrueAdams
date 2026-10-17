import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import proposedDate from "../utils/proposedDate.js";

// The events waiting for a coordinator, each opening its assignment page (SCRUM-81).
const NOT_LOADED = "The queue could not be loaded. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";

function WaitingEvent({ event }) {
  // Submission times are naive UTC, so they are shown in the Lead's local time.
  const submitted = event.submitted_at ? formatSavedAt(event.submitted_at) : NOT_RECORDED;
  return (
    <li>
      <Link to={`/events/${event.id}/assign`}>{event.title || NOT_RECORDED}</Link>
      <p>{`Organiser: ${event.organiser.email}`}</p>
      <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
      <p>{`Submitted: ${submitted}`}</p>
    </li>
  );
}

export default function UnassignedQueuePage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get("/events/queue");
      setResult(response.data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
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
            <WaitingEvent key={event.id} event={event} />
          ))}
        </ul>
      )}
    </section>
  );
}
