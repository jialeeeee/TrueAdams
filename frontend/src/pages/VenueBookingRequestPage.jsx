import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-39: the event's coordinator requests a venue for an approved event.
// Talks to POST /api/venues/bookings (backend/app/venues/routes.py).

const NOT_LOADED = "The event or venues could not be loaded. Check your connection and try again.";
const NOT_SENT = "Your venue request was not sent. Check your connection and try again.";
// Must match the "missing" messages in _booking_problems (backend/app/venues/routes.py).
const MISSING = {
  venue_id: "Choose a venue.",
  start_time: "Enter the start date and time.",
  end_time: "Enter the end date and time.",
  venue_requirements: "Enter the venue requirements.",
};

// Event and booking times are Singapore time without a time zone: show them as recorded.
const asInput = (value) => (value ? value.slice(0, 16) : "");
const asText = (value) => value.slice(0, 16).replace("T", " ");

function explain(failure, fallback) {
  const error = failure.response?.data?.error;
  return typeof error === "string" && error.trim() ? error : fallback;
}

function missingFields(form) {
  const problems = {};
  if (!form.venue_id) problems.venue_id = MISSING.venue_id;
  if (!form.start_time) problems.start_time = MISSING.start_time;
  if (!form.end_time) problems.end_time = MISSING.end_time;
  if (!form.venue_requirements.trim()) problems.venue_requirements = MISSING.venue_requirements;
  return problems;
}

export default function VenueBookingRequestPage() {
  const { eventId } = useParams();
  const [event, setEvent] = useState(null);
  const [venues, setVenues] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(null);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [planning, venueList] = await Promise.all([
        apiClient.get(`/events/${eventId}/planning`),
        apiClient.get("/venues/"),
      ]);
      const loaded = planning.data;
      setEvent(loaded);
      setVenues(venueList.data.venues);
      // Prefilled from the event; the coordinator may change them (A3, A4).
      setForm({
        venue_id: "",
        start_time: asInput(loaded.start_time),
        end_time: asInput(loaded.end_time),
        venue_requirements: loaded.venue_requirements ?? "",
      });
    } catch (failure) {
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const change = (name) => (e) => setForm((current) => ({ ...current, [name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    const missing = missingFields(form);
    setFieldErrors(missing);
    if (Object.keys(missing).length) return;

    setSending(true);
    try {
      const response = await apiClient.post("/venues/bookings", {
        event_id: Number(eventId),
        venue_id: Number(form.venue_id),
        start_time: form.start_time,
        end_time: form.end_time,
        venue_requirements: form.venue_requirements.trim(),
      });
      setSent(response.data);
    } catch (failure) {
      // The entered details stay in the form so the request can be sent again (AC6).
      setError(explain(failure, NOT_SENT));
      setFieldErrors(failure.response?.data?.fields ?? {});
    } finally {
      setSending(false);
    }
  };

  if (loadError) {
    return (
      <section>
        <p role="alert">{loadError}</p>
        <button type="button" onClick={load}>Retry</button>
      </section>
    );
  }

  if (!event || !form) return <p>Loading…</p>;

  const back = <Link to={`/events/${event.id}/planning`}>Back to the event</Link>;

  if (sent) {
    const { booking } = sent;
    return (
      <section>
        {back}
        <h1>Request a venue: {event.title}</h1>
        <p role="status">{sent.message}</p>
        <p>{`Venue: ${booking.venue.name}`}</p>
        <p>{`Requested: ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
        <p>{`Status: ${statusLabel(booking.status)}`}</p>
      </section>
    );
  }

  // SCRUM-40: Venue Staff approved a venue; changing it goes through a change request (A3).
  if (event.venue) {
    return (
      <section>
        {back}
        <h1>Request a venue: {event.title}</h1>
        <p>
          {`Venue confirmed: ${event.venue.name}${event.venue.location ? `, ${event.venue.location}` : ""}`}
        </p>
        <p>To change the venue, submit a change request.</p>
      </section>
    );
  }

  if (event.status !== "approved") {
    return (
      <section>
        {back}
        <h1>Request a venue: {event.title}</h1>
        <p>{`A venue can only be requested for an approved event. This event is ${statusLabel(event.status)}.`}</p>
      </section>
    );
  }

  const fieldError = (name) =>
    fieldErrors[name] ? <p id={`venue-request-${name}-error`}>{fieldErrors[name]}</p> : null;

  return (
    <section>
      {back}
      <h1>Request a venue: {event.title}</h1>
      <form onSubmit={handleSubmit} noValidate>
        <label htmlFor="venue-request-venue">Venue</label>
        <select id="venue-request-venue" value={form.venue_id} onChange={change("venue_id")}>
          <option value="">Choose a venue</option>
          {venues.map((venue) => (
            <option key={venue.id} value={String(venue.id)}>
              {`${venue.name} (${venue.location ?? "location not recorded"}, capacity ${venue.capacity ?? "not recorded"})`}
            </option>
          ))}
        </select>
        {fieldError("venue_id")}

        <label htmlFor="venue-request-start">Start</label>
        <input id="venue-request-start" type="datetime-local" value={form.start_time}
          onChange={change("start_time")} />
        {fieldError("start_time")}

        <label htmlFor="venue-request-end">End</label>
        <input id="venue-request-end" type="datetime-local" value={form.end_time}
          onChange={change("end_time")} />
        {fieldError("end_time")}

        <label htmlFor="venue-request-requirements">Venue requirements</label>
        <textarea id="venue-request-requirements" rows={4} value={form.venue_requirements}
          onChange={change("venue_requirements")} />
        {fieldError("venue_requirements")}

        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={sending}>Submit request</button>
      </form>
    </section>
  );
}
