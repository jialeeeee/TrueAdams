import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";

// The event's coordinator sets the number of places and the registration period
// (SCRUM-45 AC7), via GET/PUT /api/events/<id>/registration-settings.
const NOT_LOADED =
  "The registration settings could not be loaded. Check your connection and try again.";
const NOT_SAVED =
  "The registration settings were not saved. Check your connection and try again.";

// Times are Singapore time without a time zone, sent and shown as recorded.
const asInput = (value) => (value ? value.slice(0, 16) : "");

function formFrom(settings) {
  return {
    capacity: settings.capacity === null ? "" : String(settings.capacity),
    opens_at: asInput(settings.opens_at),
    closes_at: asInput(settings.closes_at),
  };
}

function SettingsForm({ form, onChange, onSubmit }) {
  const field = (name) => (e) => onChange({ ...form, [name]: e.target.value });
  return (
    <form onSubmit={onSubmit}>
      <label htmlFor="capacity">Number of places</label>
      <input id="capacity" type="number" min="1" value={form.capacity} onChange={field("capacity")} />
      <label htmlFor="opens_at">Registration opens</label>
      <input id="opens_at" type="datetime-local" value={form.opens_at} onChange={field("opens_at")} />
      <label htmlFor="closes_at">Registration closes</label>
      <input id="closes_at" type="datetime-local" value={form.closes_at} onChange={field("closes_at")} />
      <button type="submit">Save registration settings</button>
    </form>
  );
}

export default function RegistrationSettingsPage() {
  const { eventId } = useParams();
  const [settings, setSettings] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState(null);
  const [saveError, setSaveError] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/registration-settings`);
      setSettings(response.data);
      setForm(formFrom(response.data));
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(e) {
    e.preventDefault();
    setSaveError("");
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
      // What was entered stays, so it can be corrected and saved again.
      setSaveError(explain(failure, NOT_SAVED));
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
          {settings.venue_capacity !== null && (
            <p>{`The venue holds ${settings.venue_capacity} people.`}</p>
          )}
          {confirmation && <p role="status">{confirmation}</p>}
          {saveError && <p role="alert">{saveError}</p>}
          {settings.can_edit
            ? <SettingsForm form={form} onChange={setForm} onSubmit={save} />
            : <p>{settings.message}</p>}
        </>
      )}
    </section>
  );
}
