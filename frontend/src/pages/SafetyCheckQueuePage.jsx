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
  const [comments, setComments] = useState({});
  const [approvals, setApprovals] = useState({});
  const loadAttempt = useRef(0);
  const saving = Object.values(approvals).some((approval) => approval.pending);

  const load = useCallback(async () => {
    const attempt = ++loadAttempt.current;
    // SCRUM-90 AC4: an earlier list must not remain visible during a failed reload.
    setResult(null);
    setLoadError(null);
    try {
      const response = await apiClient.get("/events/safety-checks");
      if (attempt !== loadAttempt.current) return;
      setResult(response.data);
      setApprovals({}); // SCRUM-92: a corrected event may return for another decision.
    } catch (failure) {
      if (attempt !== loadAttempt.current) return;
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const saveDecision = async (eventId, action = "approve") => {
    const comment = (comments[eventId] || "").trim();
    if (action !== "approve" && !comment) {
      setApprovals((previous) => ({ ...previous,
        [eventId]: { error: "Enter a comment explaining the safety problems or required changes." } }));
      return;
    }
    setApprovals((previous) => ({ ...previous, [eventId]: { pending: true } }));
    try {
      const response = await apiClient.post(`/events/${eventId}/safety-checks/${action}`,
        comment ? { comment } : {});
      setApprovals((previous) => ({ ...previous,
        [eventId]: { saved: true, message: response.data.message } }));
    } catch (failure) {
      setApprovals((previous) => ({ ...previous,
        [eventId]: { error: explain(failure, "The safety decision could not be saved. Please try again.") } }));
    }
  };

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
          <button type="button" onClick={load} disabled={saving}>Refresh</button>
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
                  {approvals[event.id]?.saved ? (
                    <p role="status">{approvals[event.id].message}</p>
                  ) : (
                    <form onSubmit={(submit) => { submit.preventDefault(); saveDecision(event.id); }}>
                      <label htmlFor={`safety-comment-${event.id}`}>Comment (optional for approval)</label>
                      <p>A comment is required to Reject or Request Changes. For Request Changes, explain what must change.</p>
                      <textarea id={`safety-comment-${event.id}`} value={comments[event.id] || ""}
                        disabled={approvals[event.id]?.pending}
                        onChange={(change) => setComments((previous) => ({ ...previous,
                          [event.id]: change.target.value }))} />
                      <button type="submit" disabled={approvals[event.id]?.pending}>
                        {approvals[event.id]?.pending ? "Saving…" : "Approve safety check"}
                      </button>
                      <button type="button" disabled={approvals[event.id]?.pending}
                        onClick={() => saveDecision(event.id, "reject")}>
                        Reject safety check
                      </button>
                      <button type="button" disabled={approvals[event.id]?.pending}
                        onClick={() => saveDecision(event.id, "request-changes")}>
                        Request Changes
                      </button>
                      {approvals[event.id]?.error && <p role="alert">{approvals[event.id].error}</p>}
                    </form>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
