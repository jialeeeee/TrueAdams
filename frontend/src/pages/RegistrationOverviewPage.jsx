import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import proposedDate from "../utils/proposedDate.js";
import registrationSummary from "../utils/registrationSummary.js";
import statusLabel from "../utils/statusLabel.js";

export default function RegistrationOverviewPage() {
  const { eventId } = useParams();
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const loadAttempt = useRef(0);

  const load = useCallback(async () => {
    const attempt = ++loadAttempt.current;
    setLoadError(null);
    setResult(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/registration-overview`);
      if (attempt !== loadAttempt.current) return;
      setResult(response.data);
    } catch (failure) {
      if (attempt !== loadAttempt.current) return;
      setLoadError({
        message: explain(failure,
          "The registration information could not be loaded. Check your connection and try again."),
        retryable: canRetry(failure),
      });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const back = <Link to="/events/managed/registrations">Back to registrations for my managed events</Link>;

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

  const { event, registration, message } = result;
  return (
    <section>
      {back}
      <h1>{event.title || "Not recorded"}</h1>
      <p>{`Starts: ${proposedDate(event.start_time)}`}</p>
      <p>{`Ends: ${proposedDate(event.end_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Expected attendance: ${event.expected_attendance ?? "Not recorded"}`}</p>
      <p>{`Venue: ${event.venue
        ? `${event.venue.name}${event.venue.capacity != null ? ` (holds ${event.venue.capacity})` : ""}`
        : "No venue yet"}`}</p>
      {registrationSummary(registration).map((line) => <p key={line}>{line}</p>)}
      <p>{`Withdrawn: ${registration.withdrawn_count}`}</p>
      <p>{`Cancelled: ${registration.cancelled_count}`}</p>
      <p>{`Registration period: ${registration.opens_at && registration.closes_at
        ? `${proposedDate(registration.opens_at)} to ${proposedDate(registration.closes_at)}`
        : "Not set up"}`}</p>
      {message && <p>{message}</p>}
    </section>
  );
}
