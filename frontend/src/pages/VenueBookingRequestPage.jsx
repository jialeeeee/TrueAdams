import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import occupiedParts from "../utils/occupiedParts.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-39: the event's coordinator requests a venue for an approved event.
// Talks to POST /api/venues/bookings (backend/app/venues/routes.py).

const NOT_LOADED = "The event or venues could not be loaded. Check your connection and try again.";
const NOT_SENT = "Your venue request was not sent. Check your connection and try again.";
const OUTCOMES_NOT_LOADED = "Saved venue outcomes could not be loaded. Check your connection and try again.";
// Must match the "missing" messages in _booking_problems (backend/app/venues/routes.py).
const MISSING = {
  venue_id: "Choose a venue.",
  start_time: "Enter the start date and time.",
  end_time: "Enter the end date and time.",
  venue_requirements: "Enter the venue requirements.",
};

const CONFLICT_LABELS = {
  booking: "Confirmed booking",
  block: "Blocked",
  hold: "Tentative hold",
};

// Event and booking times are Singapore time without a time zone: show them as recorded.
const asInput = (value) => (value ? value.slice(0, 16) : "");
const asText = (value) => value.slice(0, 16).replace("T", " ");

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
  // SCRUM-84: the server's conflicts when the occupied period clashes, and that period.
  const [clash, setClash] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [outcomeError, setOutcomeError] = useState(null);

  // SCRUM-69: recover decisions from request rows, independently of notifications.
  const loadOutcomes = useCallback(async () => {
    setOutcomeError(null);
    try {
      const response = await apiClient.get("/venues/bookings", { params: { event_id: eventId } });
      setBookings(response.data.bookings);
    } catch (failure) {
      setOutcomeError({
        message: explain(failure, OUTCOMES_NOT_LOADED),
        retryable: !failure.response || failure.response.data?.retryable === true,
      });
    }
  }, [eventId]);

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
        setup_minutes: "0",
        turnaround_minutes: "0",
      });
      loadOutcomes();
    } catch (failure) {
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, [eventId, loadOutcomes]);

  useEffect(() => {
    setBookings([]);
    setOutcomeError(null);
    load();
  }, [load]);

  const change = (name) => (e) => setForm((current) => ({ ...current, [name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setClash(null);
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
        setup_minutes: form.setup_minutes,
        turnaround_minutes: form.turnaround_minutes,
      });
      setSent(response.data);
    } catch (failure) {
      // The entered details stay in the form so the request can be sent again (AC6).
      setError(explain(failure, NOT_SENT));
      setFieldErrors(failure.response?.data?.fields ?? {});
      const data = failure.response?.data;
      if (failure.response?.status === 409 && data?.conflicts) {
        setClash({ conflicts: data.conflicts, occupied: data.occupied });
      }
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
  const rejections = bookings.filter((booking) => booking.status === "rejected");
  const outcomes = (
    <>
      {outcomeError && (
        <div>
          <p role="alert">{outcomeError.message}</p>
          {outcomeError.retryable && <button type="button" onClick={loadOutcomes}>Retry</button>}
        </div>
      )}
      {rejections.length > 0 && (
        <section aria-label="Previous venue decisions">
          <h2>Previous venue decisions</h2>
          <ul>
            {rejections.map((booking) => (
              <li key={booking.id}>
                <p>{`Status: ${statusLabel(booking.status)}`}</p>
                <p>{`Venue: ${booking.venue.name}`}</p>
                <p>{`Requested: ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
                <p>{`Reason: ${booking.rejection_reason}`}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );

  if (sent) {
    const { booking } = sent;
    return (
      <section>
        {back}
        <h1>Request a venue: {event.title}</h1>
        <p role="status">{sent.message}</p>
        <p>{`Venue: ${booking.venue.name}`}</p>
        <p>{`Requested: ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
        {(booking.setup_minutes > 0 || booking.turnaround_minutes > 0) && (
          <p>{`Occupied: ${asText(booking.occupied_start)} to ${asText(booking.occupied_end)}`}</p>
        )}
        <p>{`Status: ${statusLabel(booking.status)}`}</p>
        {outcomes}
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
        {outcomes}
      </section>
    );
  }

  if (event.status !== "approved") {
    return (
      <section>
        {back}
        <h1>Request a venue: {event.title}</h1>
        <p>{`A venue can only be requested for an approved event. This event is ${statusLabel(event.status)}.`}</p>
        {outcomes}
      </section>
    );
  }

  const fieldError = (name) =>
    fieldErrors[name] ? <p id={`venue-request-${name}-error`}>{fieldErrors[name]}</p> : null;

  return (
    <section>
      {back}
      <h1>Request a venue: {event.title}</h1>
      {outcomes}
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

        <label htmlFor="venue-request-setup">Setup time before the event (minutes)</label>
        <input id="venue-request-setup" type="number" min="0" max="1440" step="1"
          value={form.setup_minutes} onChange={change("setup_minutes")} />
        {fieldError("setup_minutes")}

        <label htmlFor="venue-request-turnaround">Turnaround time after the event (minutes)</label>
        <input id="venue-request-turnaround" type="number" min="0" max="1440" step="1"
          value={form.turnaround_minutes} onChange={change("turnaround_minutes")} />
        {fieldError("turnaround_minutes")}

        <label htmlFor="venue-request-requirements">Venue requirements</label>
        <textarea id="venue-request-requirements" rows={4} value={form.venue_requirements}
          onChange={change("venue_requirements")} />
        {fieldError("venue_requirements")}

        {error && <p role="alert">{error}</p>}
        {clash && (
          <>
            {clash.occupied && (
              <p>{`Your request would occupy the venue ${asText(clash.occupied.start)} to ${asText(clash.occupied.end)}.`}</p>
            )}
            <ul aria-label="Conflicts">
              {clash.conflicts.map((conflict) => {
                const parts = occupiedParts(conflict);
                return (
                  <li key={`${conflict.type}-${conflict.id}`}>
                    {`${CONFLICT_LABELS[conflict.type] ?? "Conflict"}: ${asText(conflict.start)} to ${asText(conflict.end)}`}
                    {parts ? ` (${parts})` : ""}
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <button type="submit" disabled={sending}>Submit request</button>
      </form>
    </section>
  );
}
