import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// An event's planning information for its coordinator (SCRUM-34), opened from the
// managed events list (SCRUM-62).
const NOT_LOADED = "The event's information could not be loaded. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";

// Every planning field, in display order. Must match PLANNING_FIELDS in
// backend/app/events/routes.py.
const FIELDS = [
  ["title", "Event name"],
  ["purpose", "Purpose"],
  ["description", "Description"],
  ["status", "Status"],
  ["start_time", "Start"],
  ["end_time", "End"],
  ["venue", "Venue"],
  ["expected_attendance", "Expected attendance"],
  ["venue_requirements", "Venue requirements"],
  ["accessibility_needs", "Accessibility needs"],
  ["equipment_requirements", "Equipment requirements"],
  ["registration_required", "Attendee registration required"],
  ["organiser", "Organiser"],
  ["coordinator", "Coordinator"],
  ["coordinator_assigned_at", "Coordinator assigned"],
  ["created_at", "Request created"],
];

function display(field, value) {
  // "No" for registration is a recorded answer; only null is not recorded (SCRUM-34 A9).
  if (value === null || value === undefined || value === "") return NOT_RECORDED;
  switch (field) {
    case "status":
      return statusLabel(value);
    case "registration_required":
      return value ? "Yes" : "No";
    case "venue":
      return value.location ? `${value.name}, ${value.location}` : value.name;
    case "organiser":
    case "coordinator":
      return value.email;
    // Event times are Singapore time without a time zone: show them as recorded.
    case "start_time":
    case "end_time":
      return value.slice(0, 16).replace("T", " ");
    // Audit times are naive UTC: show them in the user's local time.
    case "coordinator_assigned_at":
    case "created_at":
      return formatSavedAt(value);
    default:
      return String(value);
  }
}

// Booking times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

// An expired hold blocks nothing (SCRUM-87), so it is not shown as a live hold.
function bookingStatus(booking) {
  if (booking.hold_expired) return `Hold expired on ${asText(booking.hold_expires_at)}`;
  if (booking.hold_expires_at) return `${statusLabel(booking.status)}, held until ${asText(booking.hold_expires_at)}`;
  return statusLabel(booking.status);
}

// SCRUM-85: every venue booking of the event, with the status of each (AC4).
function VenueBookings({ bookings }) {
  return (
    <section aria-label="Venue bookings">
      <h2>Venue bookings</h2>
      {bookings.length === 0 ? (
        <p>No venue bookings yet.</p>
      ) : (
        <ul>
          {bookings.map((booking) => (
            <li key={booking.id}>
              <p>{display("venue", booking.venue)}</p>
              <p>{`${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
              {(booking.setup_minutes > 0 || booking.turnaround_minutes > 0) && (
                <p>{`Setup ${booking.setup_minutes} min before, turnaround ${booking.turnaround_minutes} min after`}</p>
              )}
              <p>{`Status: ${bookingStatus(booking)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function EventPlanningPage() {
  const { eventId } = useParams();
  const [event, setEvent] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    setEvent(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/planning`);
      setEvent(response.data);
    } catch (failure) {
      const data = failure.response?.data;
      const message = typeof data?.error === "string" && data.error.trim() ? data.error : NOT_LOADED;
      // Retrying only helps when the server says so, or could not be reached at all.
      setLoadError({ message, retryable: !failure.response || data?.retryable === true });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const back = <Link to="/events/managed">Back to my managed events</Link>;

  if (loadError) {
    return (
      <section>
        {back}
        <p role="alert">{loadError.message}</p>
        {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
      </section>
    );
  }

  if (!event) return <p>Loading…</p>;

  return (
    <section>
      {back}
      <h1>{event.title || NOT_RECORDED}</h1>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Coordinator: ${display("coordinator", event.coordinator)}`}</p>
      {/* SCRUM-39: only approved events proceed to venue booking (A2). */}
      {event.status === "approved" && (
        <Link to={`/events/${event.id}/venue-request`}>Request a venue</Link>
      )}
      {/* SCRUM-38: a read-only check of a venue against the event's requirements. */}
      <Link to={`/events/${event.id}/venue-suitability`}>Check venue suitability</Link>
      {/* SCRUM-42: record what equipment the event needs, for Technical Support Staff. */}
      <Link to={`/events/${event.id}/equipment`}>Equipment requirements</Link>
      {event.status === "approved" && event.registration_required === true && (
        <Link to={`/events/${event.id}/registration-settings`}>Set up registration</Link>
      )}

      <dl>
        {FIELDS.map(([field, label]) => (
          <div key={field}>
            <dt>{label}</dt>
            <dd>{display(field, event[field])}</dd>
          </div>
        ))}
      </dl>
      <VenueBookings bookings={event.venue_bookings ?? []} />
      {event.safety_check && (
        <section aria-label="Safety check">
          <h2>Safety check</h2>
          <p>{`Decision: ${statusLabel(event.safety_check.decision)}`}</p>
          <p>{`Safety Officer: ${event.safety_check.officer?.email || NOT_RECORDED}`}</p>
          <p>{`Comment: ${event.safety_check.comment ?? NOT_RECORDED}`}</p>
          <p>{`Decided: ${event.safety_check.decided_at ? formatSavedAt(event.safety_check.decided_at) : NOT_RECORDED}`}</p>
        </section>
      )}
    </section>
  );
}
