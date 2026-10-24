import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import proposedDate from "../utils/proposedDate.js";
import registrationSummary from "../utils/registrationSummary.js";
import statusLabel from "../utils/statusLabel.js";

// One event's registrations, for its organiser (SCRUM-54 AC2, AC4-AC6).
const NOT_LOADED =
  "The registration information could not be loaded. Check your connection and try again.";
// Registration.status values in backend/app/models.py.
const REGISTRATION_STATUS_LABELS = {
  registered: "Registered",
  withdrawn: "Withdrawn",
  cancelled: "Cancelled",
};

function RegistrationsTable({ registrations }) {
  return (
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
            {/* Accounts record no name, so the email identifies the attendee (A5). */}
            <td>{registration.attendee.email}</td>
            {/* An audit time in UTC, shown in the viewer's local time (A6). */}
            <td>{formatSavedAt(registration.registered_at)}</td>
            <td>{REGISTRATION_STATUS_LABELS[registration.status] ?? registration.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function EventRegistrationsPage() {
  const { eventId } = useParams();
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    // Cleared first, so another event's registrations never show while this one loads
    // or after it fails (AC6).
    setLoadError(null);
    setResult(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/registrations`);
      setResult(response.data);
    } catch (failure) {
      // A refusal (AC4) shows its message with no Retry; only failures worth retrying get one.
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
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

  const { event, registrations, message } = result;
  return (
    <section>
      {back}
      <h1>{event.title || "Not recorded"}</h1>
      <p>{`Proposed date: ${proposedDate(event.start_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      {registrationSummary(event.registration).map((line) => <p key={line}>{line}</p>)}

      {/* With no registrations, the server's message instead of an empty table (AC5). */}
      {registrations.length === 0
        ? <p>{message}</p>
        : <RegistrationsTable registrations={registrations} />}
    </section>
  );
}
