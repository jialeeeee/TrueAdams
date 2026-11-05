import { useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";
import statusLabel from "../utils/statusLabel.js";
import { formatDate } from "./VenueAvailabilityPage.jsx";

// CF09: one calendar of every event with a plan, for coordinators, Venue Staff and
// Technical Support Staff. GET /api/venues/calendar?from&to, at most 31 days as for a
// venue's calendar; the server checks the range and who may see it.
const NOT_LOADED = "The events calendar could not be loaded. Check your connection and try again.";

// The events grouped by the day each starts on, keeping the server's order.
function byDay(events) {
  const days = new Map();
  events.forEach((event) => {
    const day = event.start_time.slice(0, 10);
    days.set(day, [...(days.get(day) ?? []), event]);
  });
  return [...days.entries()];
}

function CalendarEvent({ event }) {
  return (
    <li>
      <p>
        {event.managed
          ? <Link to={`/events/${event.id}/planning`}>{event.title}</Link>
          : event.title}
      </p>
      <p>{`${singaporeTime(event.start_time)} to ${singaporeTime(event.end_time)}`}</p>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Coordinator: ${event.coordinator?.email ?? "Not assigned yet"}`}</p>
      {event.venues.length === 0 ? (
        <p>No venue booked or requested yet.</p>
      ) : (
        <ul aria-label={`Venues for ${event.title}`}>
          {event.venues.map((venue) => (
            <li key={`${venue.id}-${venue.start_time}`}>
              {`${venue.name} (${statusLabel(venue.booking_status)})`}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function EventsCalendarPage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [calendar, setCalendar] = useState(null);
  const [formError, setFormError] = useState("");
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoadError(null);
    setLoading(true);
    try {
      const response = await apiClient.get("/venues/calendar", { params: to ? { from, to } : { from } });
      setCalendar(response.data);
    } catch (failure) {
      // A failed load is never shown as an empty calendar.
      setCalendar(null);
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    } finally {
      setLoading(false);
    }
  };

  const show = (submitted) => {
    submitted.preventDefault();
    if (!from) {
      setFormError("Choose a start date.");
      return;
    }
    setFormError("");
    load();
  };

  return (
    <section>
      <h1>Events calendar</h1>
      <form onSubmit={show} noValidate>
        <label htmlFor="calendar-from">From</label>
        <input id="calendar-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <label htmlFor="calendar-to">To (optional)</label>
        <input id="calendar-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        <button type="submit" disabled={loading}>{loading ? "Loading…" : "Show events"}</button>
      </form>
      {formError && <p role="alert">{formError}</p>}
      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}
      {calendar && calendar.message && <p>{calendar.message}</p>}
      {calendar && byDay(calendar.events).map(([day, events]) => (
        <section key={day} aria-label={formatDate(day)}>
          <h2>{formatDate(day)}</h2>
          <ul>
            {events.map((event) => <CalendarEvent key={event.id} event={event} />)}
          </ul>
        </section>
      ))}
    </section>
  );
}
