import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import statusLabel from "../utils/statusLabel.js";

// The active events a Coordinator Lead assigned, filterable by coordinator (SCRUM-83).
const NOT_LOADED =
  "The events you assigned could not be loaded. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";
const ALL_COORDINATORS = "";

// Proposed dates are Singapore time without a time zone: show them as recorded.
function proposedDate(value) {
  return value ? value.slice(0, 16).replace("T", " ") : NOT_RECORDED;
}

// A network failure, or one the server marks retryable, can be tried again; a refusal cannot.
function canRetry(failure) {
  return !failure.response || failure.response.data?.retryable === true;
}

function AssignedEvent({ event }) {
  return (
    <li>
      <h2>{event.title || NOT_RECORDED}</h2>
      <p>{`Coordinator: ${event.coordinator.email}`}</p>
      <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
    </li>
  );
}

export default function LeadAssignedEventsPage() {
  const [result, setResult] = useState(null);
  const [coordinatorId, setCoordinatorId] = useState(ALL_COORDINATORS);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async (selected) => {
    setLoadError(null);
    try {
      const params = selected === ALL_COORDINATORS ? {} : { coordinator_id: selected };
      const response = await apiClient.get("/events/supervised", { params });
      setResult(response.data);
    } catch (failure) {
      // Never leave an earlier list on screen as if it were current (AC4).
      setResult(null);
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load(ALL_COORDINATORS);
  }, [load]);

  function chooseCoordinator(selected) {
    setCoordinatorId(selected);
    load(selected);
  }

  return (
    <section>
      <h1>Events I assigned</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && (
            <button type="button" onClick={() => load(coordinatorId)}>Retry</button>
          )}
        </>
      )}

      {result && (
        <>
          <label>
            Coordinator
            <select value={coordinatorId} onChange={(e) => chooseCoordinator(e.target.value)}>
              <option value={ALL_COORDINATORS}>All coordinators</option>
              {result.coordinators.map((coordinator) => (
                <option key={coordinator.id} value={String(coordinator.id)}>
                  {coordinator.email}
                </option>
              ))}
            </select>
          </label>

          {result.events.length === 0 ? (
            <p>{result.message}</p>
          ) : (
            <ul>
              {result.events.map((event) => (
                <AssignedEvent key={event.id} event={event} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
