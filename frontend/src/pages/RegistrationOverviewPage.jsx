import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import proposedDate from "../utils/proposedDate.js";
import registrationSummary from "../utils/registrationSummary.js";
import statusLabel from "../utils/statusLabel.js";

// One assigned event's registration figures, for its coordinator to plan the venue and
// logistics around (SCRUM-72 AC2, AC4-AC6). Attendees' identities stay with the
// organiser's view (SCRUM-54), so none are shown here (A4).
const NOT_LOADED =
  "The registration information could not be loaded. Check your connection and try again.";

function venueText(venue) {
  if (!venue) return "No venue yet";
  return venue.capacity == null ? venue.name : `${venue.name} (holds ${venue.capacity})`;
}

// Registration times are Singapore time, shown as recorded like the event's own.
function registrationPeriod({ opens_at: opensAt, closes_at: closesAt }) {
  if (!opensAt || !closesAt) return "Not set up";
  return `${proposedDate(opensAt)} to ${proposedDate(closesAt)}`;
}

function Overview({ event, registration, message }) {
  return (
    <>
      <h1>{event.title || "Not recorded"}</h1>
      <p>{`Starts: ${proposedDate(event.start_time)}`}</p>
      <p>{`Ends: ${proposedDate(event.end_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Expected attendance: ${event.expected_attendance ?? "Not recorded"}`}</p>
      <p>{`Venue: ${venueText(event.venue)}`}</p>
      {registrationSummary(registration).map((line) => <p key={line}>{line}</p>)}
      <p>{`Withdrawn: ${registration.withdrawn_count}`}</p>
      <p>{`Cancelled: ${registration.cancelled_count}`}</p>
      <p>{`Registration period: ${registrationPeriod(registration)}`}</p>
      {/* No registrations at all: the server's message says so (AC5). */}
      {message && <p>{message}</p>}
    </>
  );
}

export default function RegistrationOverviewPage() {
  const { eventId } = useParams();
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const loadAttempt = useRef(0);

  const load = useCallback(async () => {
    // Another event's figures must never show (AC6): the page is cleared while this one
    // loads, and a late reply from an earlier load, e.g. for the event the coordinator
    // just left, is dropped (TC-72-20), as in SCRUM-80's queue and SCRUM-54's page.
    const attempt = ++loadAttempt.current;
    const isStale = () => attempt !== loadAttempt.current;
    setLoadError(null);
    setResult(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/registration-overview`);
      if (isStale()) return;
      setResult(response.data);
    } catch (failure) {
      if (isStale()) return;
      // A refusal (AC4) shows its message with no Retry; only failures worth retrying get one.
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
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

  return (
    <section>
      {back}
      <Overview {...result} />
    </section>
  );
}
