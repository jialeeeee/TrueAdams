import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import proposedDate from "../utils/proposedDate.js";
import statusLabel from "../utils/statusLabel.js";

// A Coordinator Lead assigns a coordinator to an event waiting in the queue (SCRUM-81).
const NOT_LOADED = "The event could not be loaded. Check your connection and try again.";
const NOT_SAVED = "The assignment was not saved. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";
const CHOOSE = "Choose a coordinator.";

function EventSummary({ event }) {
  return (
    <>
      <h2>{event.title || NOT_RECORDED}</h2>
      <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
    </>
  );
}

function Confirmation({ result }) {
  return (
    <>
      <p>{result.message}</p>
      <p>
        {result.notification.email_queued
          ? "They have been notified."
          : "They were notified in ConnectSphere, but the email could not be sent."}
      </p>
    </>
  );
}

function AssignmentForm({ coordinators, choice, onChoose, onSubmit }) {
  return (
    <form onSubmit={onSubmit}>
      <label>
        Coordinator
        <select value={choice} onChange={(e) => onChoose(e.target.value)}>
          <option value="">Choose a coordinator</option>
          {coordinators.map((coordinator) => (
            <option key={coordinator.id} value={String(coordinator.id)}>
              {coordinator.email}
            </option>
          ))}
        </select>
      </label>
      <button type="submit">Assign coordinator</button>
    </form>
  );
}

export default function AssignCoordinatorPage() {
  const { eventId } = useParams();
  const [queued, setQueued] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [choice, setChoice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [result, setResult] = useState(null);
  // Set when the server says the event can no longer be assigned here (HTTP 409).
  const [closed, setClosed] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/assignment`);
      setQueued(response.data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  async function assign(e) {
    e.preventDefault();
    if (!choice) {
      setSaveError(CHOOSE);
      return;
    }
    setSaveError("");
    try {
      const response = await apiClient.post(`/events/${eventId}/assignment`, {
        coordinator_id: Number(choice),
      });
      setResult(response.data);
    } catch (failure) {
      // The choice is kept, so a retryable failure can simply be sent again.
      setSaveError(explain(failure, NOT_SAVED));
      setClosed(failure.response?.status === 409);
    }
  }

  const canAssign = queued && !result && !closed && queued.coordinators.length > 0;

  return (
    <section>
      <h1>Assign a coordinator</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {queued && (
        <>
          <EventSummary event={queued.event} />
          {result && <Confirmation result={result} />}
          {saveError && <p role="alert">{saveError}</p>}
          {queued.coordinators.length === 0 && <p>{queued.message}</p>}
          {canAssign && (
            <AssignmentForm
              coordinators={queued.coordinators}
              choice={choice}
              onChoose={setChoice}
              onSubmit={assign}
            />
          )}
        </>
      )}
    </section>
  );
}
