import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

export default function EventRegistrationsPage() {
  const { eventId } = useParams();
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    setResult(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/registrations`);
      setResult(response.data);
    } catch (failure) {
      const data = failure.response?.data;
      const message = typeof data?.error === "string" && data.error.trim()
        ? data.error
        : "The registration information could not be loaded. Check your connection and try again.";
      setLoadError({ message, retryable: !failure.response || data?.retryable === true });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const back = <Link to="/events/organised">Back to registrations for my events</Link>;

  if (loadError) {
    return (
      <section>
        {back}
        <p role="alert">{loadError.message}</p>
        {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
      </section>
    );
  }

  if (!result) return <p>Loading…</p>;

  const { event, registrations } = result;
  return (
    <section>
      {back}
      <h1>{event.title || "Not recorded"}</h1>
      <p>{`Proposed date: ${event.start_time ? event.start_time.slice(0, 16).replace("T", " ") : "Not recorded"}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Registrations: ${event.registration.registered_count}`}</p>
      <p>{`Capacity: ${event.registration.capacity ?? "Not set up"}`}</p>
      <p>{`Remaining places: ${event.registration.slots_remaining ?? "Not set up"}`}</p>

      {registrations.length === 0 && <p>{result.message}</p>}
      {registrations.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Attendee</th>
              <th>Registered on</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {registrations.map((registration) => (
              <tr key={registration.id}>
                <td>{registration.attendee.email}</td>
                <td>{formatSavedAt(registration.registered_at)}</td>
                <td>{statusLabel(registration.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
