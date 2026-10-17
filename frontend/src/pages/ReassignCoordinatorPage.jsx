import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import statusLabel from "../utils/statusLabel.js";

export default function ReassignCoordinatorPage() {
  const { eventId } = useParams();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/eligible-coordinators`);
      setData(response.data);
    } catch (failure) {
      const message = failure.response?.data?.error;
      setLoadError({
        message: typeof message === "string" && message.trim()
          ? message
          : "The event could not be loaded. Check your connection and try again.",
        retryable: !failure.response || failure.response.data?.retryable === true,
      });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(e) {
    e.preventDefault();
    if (!choice) {
      setError("Choose a coordinator.");
      return;
    }
    setError("");
    try {
      const response = await apiClient.put(`/events/${eventId}/coordinator`, {
        coordinator_id: Number(choice),
      });
      setDone(response.data);
    } catch (failure) {
      const message = failure.response?.data?.error;
      setError(typeof message === "string" && message.trim()
        ? message
        : "The reassignment was not saved. Check your connection and try again.");
    }
  }

  const current = done ? done.coordinator : data?.current_coordinator;

  return (
    <section>
      <h1>Reassign coordinator</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {data && (
        <>
          <h2>{data.event.title || "Not recorded"}</h2>
          <p>{`Proposed date: ${data.event.start_time ? data.event.start_time.slice(0, 16).replace("T", " ") : "Not recorded"}`}</p>
          <p>{`Status: ${statusLabel(data.event.status)}`}</p>
          <p>{`Current coordinator: ${current.email}`}</p>

          {done && (
            <>
              <p>{done.message}</p>
              <p>
                {done.notification.email_queued
                  ? "Both coordinators have been notified."
                  : "Both coordinators were notified in ConnectSphere, but an email could not be sent."}
              </p>
            </>
          )}

          {error && <p role="alert">{error}</p>}

          {data.coordinators.length === 0 && <p>{data.message}</p>}

          {!done && data.coordinators.length > 0 && (
            <form onSubmit={submit}>
              <label>
                New coordinator
                <select value={choice} onChange={(e) => setChoice(e.target.value)}>
                  <option value="">Choose a coordinator</option>
                  {data.coordinators.map((c) => (
                    <option key={c.id} value={String(c.id)}>{c.email}</option>
                  ))}
                </select>
              </label>
              <button type="submit">Reassign coordinator</button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
