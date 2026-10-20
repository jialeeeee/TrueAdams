import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import ARRANGEMENT_STATUSES from "../utils/arrangementStatuses.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-42 AC4: Technical Support Staff see which events have equipment requirements to
// arrange, soonest first, via GET /api/events/equipment-requests.
const NOT_LOADED = "The equipment requests could not be loaded. Check your connection and try again.";

function progress(event) {
  const count = `${event.requirement_count} ${event.requirement_count === 1 ? "requirement" : "requirements"}`;
  const byStatus = ARRANGEMENT_STATUSES.map(
    ([status, label]) => `${label}: ${event.status_counts[status] ?? 0}`,
  );
  return `${count} — ${byStatus.join(" · ")}`;
}

export default function EquipmentRequestsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get("/events/equipment-requests");
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
      <h1>Equipment requests</h1>
      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}
      {!loadError && !result && <p>Loading…</p>}
      {!loadError && result && (result.events.length === 0 ? (
        <p>{result.message}</p>
      ) : (
        <ul>
          {result.events.map((event) => (
            <li key={event.id}>
              <Link to={`/events/${event.id}/equipment`}>{event.title}</Link>
              <p>{event.start_time ? `${singaporeTime(event.start_time)} to ${singaporeTime(event.end_time)}` : "Time not recorded"}</p>
              <p>{`Status: ${statusLabel(event.status)}`}</p>
              <p>{`Coordinator: ${event.coordinator ? event.coordinator.email : "Not assigned"}`}</p>
              <p>{progress(event)}</p>
            </li>
          ))}
        </ul>
      ))}
    </section>
  );
}
