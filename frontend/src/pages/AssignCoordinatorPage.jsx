import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import statusLabel from "../utils/statusLabel.js";

export default function AssignCoordinatorPage() {
  const { eventId } = useParams();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);
  const [closed, setClosed] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/assignment`);
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
      const response = await apiClient.post(`/events/${eventId}/assignment`, {
        coordinator_id: Number(choice),
      });
      setDone(response.data);
    } catch (failure) {
      const message = failure.response?.data?.error;
      setError(typeof message === "string" && message.trim()
        ? message
        : "The assignment was not saved. Check your connection and try again.");
      if (failure.response?.status === 409) {
        setClosed(true);
      }
    }
  }

  return (
    <section>
      <h1>Assign a coordinator</h1>

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

          {done && (
            <>
              <p>{done.message}</p>
              <p>
                {done.notification.email_queued
                  ? "They have been notified."
                  : "They were notified in ConnectSphere, but the email could not be sent."}
              </p>
            </>
          )}

          {error && <p role="alert">{error}</p>}

          {data.coordinators.length === 0 && <p>{data.message}</p>}

          {!done && !closed && data.coordinators.length > 0 && (
            <form onSubmit={submit}>
              <label>
                Coordinator
                <select value={choice} onChange={(e) => setChoice(e.target.value)}>
                  <option value="">Choose a coordinator</option>
                  {data.coordinators.map((c) => (
                    <option key={c.id} value={String(c.id)}>{c.email}</option>
                  ))}
                </select>
              </label>
              <button type="submit">Assign coordinator</button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
