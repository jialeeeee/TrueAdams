import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import statusLabel from "../utils/statusLabel.js";

export default function LeadAssignedEventsPage() {
  const [result, setResult] = useState(null);
  const [coordinatorId, setCoordinatorId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [canRetry, setCanRetry] = useState(false);

  const load = useCallback(async (selected) => {
    setLoadError("");
    try {
      const params = selected ? { coordinator_id: selected } : {};
      const response = await apiClient.get("/events/supervised", { params });
      setResult(response.data);
    } catch (failure) {
      setResult(null);
      const error = failure.response?.data?.error;
      setLoadError(typeof error === "string" && error.trim()
        ? error
        : "The events you assigned could not be loaded. Check your connection and try again.");
      setCanRetry(!failure.response || failure.response.data?.retryable === true);
    }
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  return (
    <section>
      <h1>Events I assigned</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          {canRetry && <button type="button" onClick={() => load(coordinatorId)}>Retry</button>}
        </>
      )}

      {result && (
        <label>
          Coordinator
          <select
            value={coordinatorId}
            onChange={(e) => {
              setCoordinatorId(e.target.value);
              load(e.target.value);
            }}
          >
            <option value="">All coordinators</option>
            {result.coordinators.map((c) => (
              <option key={c.id} value={String(c.id)}>{c.email}</option>
            ))}
          </select>
        </label>
      )}

      {result && result.events.length === 0 && <p>{result.message}</p>}
      {result && result.events.length > 0 && (
        <ul>
          {result.events.map((event) => (
            <li key={event.id}>
              <h2>{event.title || "Not recorded"}</h2>
              <p>{`Coordinator: ${event.coordinator.email}`}</p>
              <p>{`Proposed date: ${event.start_time ? event.start_time.slice(0, 16).replace("T", " ") : "Not recorded"}`}</p>
              <p>{`Status: ${statusLabel(event.status)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
