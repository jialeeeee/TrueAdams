import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import proposedDate from "../utils/proposedDate.js";
import statusLabel from "../utils/statusLabel.js";

// A Coordinator Lead reassigns an event to a different coordinator (SCRUM-82).
const NOT_LOADED = "The event could not be loaded. Check your connection and try again.";
const NOT_SAVED = "The reassignment was not saved. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";
const CHOOSE = "Choose a coordinator.";

function EventSummary({ event, coordinator }) {
  return (
    <>
      <h2>{event.title || NOT_RECORDED}</h2>
      <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Current coordinator: ${coordinator.email}`}</p>
    </>
  );
}

function Confirmation({ result }) {
  return (
    <>
      <p>{result.message}</p>
      <p>
        {result.notification.email_queued
          ? "Both coordinators have been notified."
          : "Both coordinators were notified in ConnectSphere, but an email could not be sent."}
      </p>
    </>
  );
}

function ReassignForm({ coordinators, choice, onChoose, onSubmit }) {
  return (
    <form onSubmit={onSubmit}>
      <label>
        New coordinator
        <select value={choice} onChange={(e) => onChoose(e.target.value)}>
          <option value="">Choose a coordinator</option>
          {coordinators.map((coordinator) => (
            <option key={coordinator.id} value={String(coordinator.id)}>
              {coordinator.email}
            </option>
          ))}
        </select>
      </label>
      <button type="submit">Reassign coordinator</button>
    </form>
  );
}

export default function ReassignCoordinatorPage() {
  const { eventId } = useParams();
  const [options, setOptions] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [choice, setChoice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/eligible-coordinators`);
      setOptions(response.data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  async function reassign(e) {
    e.preventDefault();
    if (!choice) {
      setSaveError(CHOOSE);
      return;
    }
    setSaveError("");
    try {
      const response = await apiClient.put(`/events/${eventId}/coordinator`, {
        coordinator_id: Number(choice),
      });
      setResult(response.data);
    } catch (failure) {
      // The choice is kept, so the Lead can send it again or pick someone else.
      setSaveError(explain(failure, NOT_SAVED));
    }
  }

  return (
    <section>
      <h1>Reassign coordinator</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {options && (
        <>
          <EventSummary
            event={options.event}
            coordinator={result ? result.coordinator : options.current_coordinator}
          />
          {result && <Confirmation result={result} />}
          {saveError && <p role="alert">{saveError}</p>}
          {options.coordinators.length === 0 && <p>{options.message}</p>}
          {!result && options.coordinators.length > 0 && (
            <ReassignForm
              coordinators={options.coordinators}
              choice={choice}
              onChoose={setChoice}
              onSubmit={reassign}
            />
          )}
        </>
      )}
    </section>
  );
}
