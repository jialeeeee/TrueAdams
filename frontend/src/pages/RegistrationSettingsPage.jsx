import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";

export default function RegistrationSettingsPage() {
  const { eventId } = useParams();
  const [settings, setSettings] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState({ capacity: "", opens_at: "", closes_at: "" });
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/registration-settings`);
      setSettings(response.data);
      setForm({
        capacity: response.data.capacity === null ? "" : String(response.data.capacity),
        opens_at: response.data.opens_at ? response.data.opens_at.slice(0, 16) : "",
        closes_at: response.data.closes_at ? response.data.closes_at.slice(0, 16) : "",
      });
    } catch (failure) {
      const message = failure.response?.data?.error;
      setLoadError({
        message: typeof message === "string" && message.trim()
          ? message
          : "The registration settings could not be loaded. Check your connection and try again.",
        retryable: !failure.response || failure.response.data?.retryable === true,
      });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(e) {
    e.preventDefault();
    setError("");
    setConfirmation("");
    try {
      const response = await apiClient.put(`/events/${eventId}/registration-settings`, {
        capacity: Number(form.capacity),
        opens_at: form.opens_at,
        closes_at: form.closes_at,
      });
      setSettings(response.data);
      setConfirmation(response.data.message);
    } catch (failure) {
      const message = failure.response?.data?.error;
      setError(typeof message === "string" && message.trim()
        ? message
        : "The registration settings were not saved. Check your connection and try again.");
    }
  }

  return (
    <section>
      <Link to={`/events/${eventId}/planning`}>Back to the event</Link>
      <h1>Set up registration</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {settings && (
        <>
          <p>{`Registered so far: ${settings.registered_count}`}</p>
          {settings.venue_capacity !== null && <p>{`The venue holds ${settings.venue_capacity} people.`}</p>}
          {confirmation && <p role="status">{confirmation}</p>}
          {error && <p role="alert">{error}</p>}
          {!settings.can_edit && <p>{settings.message}</p>}
          {settings.can_edit && (
            <form onSubmit={save}>
              <label htmlFor="capacity">Number of places</label>
              <input id="capacity" type="number" min="1" value={form.capacity}
                onChange={(e) => setForm({ ...form, capacity: e.target.value })} />
              <label htmlFor="opens_at">Registration opens</label>
              <input id="opens_at" type="datetime-local" value={form.opens_at}
                onChange={(e) => setForm({ ...form, opens_at: e.target.value })} />
              <label htmlFor="closes_at">Registration closes</label>
              <input id="closes_at" type="datetime-local" value={form.closes_at}
                onChange={(e) => setForm({ ...form, closes_at: e.target.value })} />
              <button type="submit">Save registration settings</button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
