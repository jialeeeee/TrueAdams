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

  const back = (
    <Link className="back-link" to="/events/managed">Back to my managed events</Link>
  );

  if (loadError) {
    return (
      <section>
        {back}
        <p role="alert">{loadError.message}</p>
        {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
      </section>
    );
  }

  if (!event) return <p className="loading">Loading…</p>;

  return (
    <section>
      {back}
      <h1>{event.title || NOT_RECORDED}</h1>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{`Coordinator: ${display("coordinator", event.coordinator)}`}</p>

      <dl>
        {FIELDS.map(([field, label]) => (
          <div key={field}>
            <dt>{label}</dt>
            <dd>{display(field, event[field])}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
