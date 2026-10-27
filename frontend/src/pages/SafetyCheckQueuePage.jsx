import { useCallback, useEffect, useRef, useState } from "react";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";

const NOT_LOADED = "The safety check list could not be loaded. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";

export default function SafetyCheckQueuePage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const loadAttempt = useRef(0);

  const load = useCallback(async () => {
    const attempt = ++loadAttempt.current;
    // SCRUM-90 AC4: an earlier list must not remain visible during a failed reload.
    setResult(null);
    setLoadError(null);
    try {
      const response = await apiClient.get("/events/safety-checks");
      if (attempt !== loadAttempt.current) return;
      setResult(response.data);
    } catch (failure) {
      if (attempt !== loadAttempt.current) return;
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Events awaiting a safety check</h1>
      {loadError ? (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      ) : !result ? (
        <p>Loading…</p>
      ) : (
        <>
          <button type="button" onClick={load}>Refresh</button>
          {result.events.length === 0 ? (
            <p>{result.message}</p>
          ) : (
            <ul>
              {result.events.map((event) => (
                <li key={event.id}>
                  <h2>{event.title || NOT_RECORDED}</h2>
                  <p>{`Venue: ${event.venues.map((venue) => venue.name || NOT_RECORDED).join(", ")}`}</p>
                  <p>{`Date: ${event.start_time ? singaporeTime(event.start_time) : NOT_RECORDED} to ${event.end_time ? singaporeTime(event.end_time) : NOT_RECORDED}`}</p>
                  <p>{`Expected attendance: ${event.expected_attendance ?? NOT_RECORDED}`}</p>
                  {event.equipment.length === 0 ? (
                    <p>No equipment required</p>
                  ) : event.equipment.map((line, index) => (
                    <p key={index}>{`${line.quantity} × ${line.equipment_type} (${line.reserved_quantity} reserved)`}</p>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
