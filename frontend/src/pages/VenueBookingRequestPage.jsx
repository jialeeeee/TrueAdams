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
const NOT_CANCELLED = "The booking was not cancelled. Check your connection and try again.";
// SCRUM-94 AC1: the statuses a coordinator can cancel. Must match CANCELLABLE_STATUSES
// in backend/app/venues/routes.py.
const CANCELLABLE = ["pending", "tentative", "confirmed"];
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
const asPeriod = (booking) => `${asText(booking.start_time)} to ${asText(booking.end_time)}`;

// SCRUM-87 A10: a hold shows its expiry as recorded. The server says whether it has
// expired, so the browser's clock plays no part.
function bookingStatus(booking) {
  if (!booking.hold) return statusLabel(booking.status);
  const expiry = asText(booking.hold.expires_at);
  return booking.hold.expired ? `Hold expired on ${expiry}` : `Tentative hold until ${expiry} (Singapore time)`;
}

function missingFields(form) {
  const problems = {};
  if (!form.venue_id) problems.venue_id = MISSING.venue_id;
  if (!form.start_time) problems.start_time = MISSING.start_time;
  if (!form.end_time) problems.end_time = MISSING.end_time;
  if (!form.venue_requirements.trim()) problems.venue_requirements = MISSING.venue_requirements;
  return problems;
}

// The form for a new request, prefilled from the event; the coordinator may change them (A3, A4).
function freshForm(event) {
  return {
    venue_id: "",
    start_time: asInput(event.start_time),
    end_time: asInput(event.end_time),
    venue_requirements: event.venue_requirements ?? "",
    setup_minutes: "0",
    turnaround_minutes: "0",
  };
}

// SCRUM-94: the event's bookings, except rejections (listed with their reasons below), each
// pending, tentative or confirmed one with Cancel booking and a confirmation step (AC2, A5).
// SCRUM-85 A6, A8: the step also offers the event's other live bookings, unticked.
function VenueBookings({ bookings, onCancel }) {
  const [confirming, setConfirming] = useState(null);
  const [alsoCancel, setAlsoCancel] = useState([]);
  if (bookings.length === 0) return null;

  const startConfirming = (booking) => {
    setAlsoCancel([]);
    setConfirming(booking);
  };
  const toggle = (id) => setAlsoCancel((ids) => (ids.includes(id) ? ids.filter((other) => other !== id) : [...ids, id]));
  const others = confirming
    ? bookings.filter((booking) => booking.id !== confirming.id && CANCELLABLE.includes(booking.status))
    : [];

  const confirm = async () => {
    await onCancel(confirming, others.map((booking) => booking.id).filter((id) => alsoCancel.includes(id)));
    setConfirming(null);
  };

  return (
    <section aria-label="Venue bookings">
      <h2>Venue bookings</h2>
      <ul>
        {bookings.map((booking) => (
          <li key={booking.id}>
            <p>{`${booking.venue.name}, ${asPeriod(booking)}`}</p>
            <p>{`Status: ${bookingStatus(booking)}`}</p>
            {CANCELLABLE.includes(booking.status) && (
              <button type="button" onClick={() => startConfirming(booking)}>Cancel booking</button>
            )}
          </li>
        ))}
      </ul>
      {confirming && (
        <div role="group" aria-label="Confirm cancellation">
          <p>
            {`Cancel the booking of ${confirming.venue.name}, ${asPeriod(confirming)}? The venue will be released for that time.`}
          </p>
          {others.length > 0 && (
            <>
              <p>The event&apos;s other bookings stay as they are unless you tick them:</p>
              <ul>
                {others.map((booking) => (
                  <li key={booking.id}>
                    <label>
                      <input type="checkbox" checked={alsoCancel.includes(booking.id)}
                        onChange={() => toggle(booking.id)} />
                      {`Also cancel ${booking.venue.name}, ${asPeriod(booking)}`}
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}
          <button type="button" onClick={confirm}>Yes, cancel booking</button>
          <button type="button" onClick={() => setConfirming(null)}>Keep booking</button>
        </div>
      )}
    </section>
  );
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
  // SCRUM-94: the outcome of cancelling a booking.
  const [cancelMessage, setCancelMessage] = useState("");
  const [cancelError, setCancelError] = useState("");

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
      setForm(freshForm(loaded));
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

  // SCRUM-85 A6: the other bookings are sent only when the coordinator chose some.
  const cancelBooking = async (booking, alsoCancel = []) => {
    setCancelMessage("");
    setCancelError("");
    try {
      const url = `/venues/bookings/${booking.id}/cancel`;
      const response = alsoCancel.length
        ? await apiClient.post(url, { also_cancel: alsoCancel })
        : await apiClient.post(url);
      setCancelMessage(response.data.message);
      // Cancelling a confirmed venue can change the event's venue (A3; SCRUM-85 A4), so reload both.
      load();
    } catch (failure) {
      // The booking is unchanged (AC6), so it stays listed and can be cancelled again.
      setCancelError(explain(failure, NOT_CANCELLED));
    }
  };

  // SCRUM-85 A8: a fresh form for the next venue, and the list read again to show the last.
  const requestAnother = () => {
    setSent(null);
    setError("");
    setFieldErrors({});
    setClash(null);
    setForm(freshForm(event));
    loadOutcomes();
  };

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
      {cancelMessage && <p role="status">{cancelMessage}</p>}
      {cancelError && <p role="alert">{cancelError}</p>}
      <VenueBookings bookings={bookings.filter((booking) => booking.status !== "rejected")}
        onCancel={cancelBooking} />
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
        <button type="button" onClick={requestAnother}>Request another venue</button>
        {outcomes}
      </section>
    );
  }

  // SCRUM-40: Venue Staff approved a venue; changing it goes through a change request (A3).
  // SCRUM-85: the event may still need more venues, so the form is offered alongside it.
  const confirmed = event.venue && (
    <>
      <p>
        {`Venue confirmed: ${event.venue.name}${event.venue.location ? `, ${event.venue.location}` : ""}`}
      </p>
      <p>To change the venue, submit a change request.</p>
    </>
  );

  if (event.status !== "approved") {
    return (
      <section>
        {back}
        <h1>Request a venue: {event.title}</h1>
        {confirmed}
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
      {confirmed}
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
