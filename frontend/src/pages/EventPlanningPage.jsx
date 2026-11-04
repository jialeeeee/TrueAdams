import { useCallback, useEffect, useRef, useState } from "react";
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

// CF11 (G4 clarification #8): what the event needs of a venue, recorded by its coordinator
// so the venue suitability check (SCRUM-38) can show a facility, accessibility or layout
// mismatch. The options are the lists Venue Staff choose from. Must match FACILITY_OPTIONS,
// ACCESSIBILITY_OPTIONS and LAYOUT_OPTIONS in backend/app/venues/routes.py.
const REQUIREMENT_GROUPS = [
  { key: "facilities", field: "required_facilities", label: "Required facilities",
    options: ["Projector", "Microphone", "Video conferencing"] },
  { key: "accessibility_features", field: "required_accessibility_features",
    label: "Required accessibility features", options: ["Wheelchair ramp", "Hearing loop"] },
  { key: "layouts", field: "required_layouts", label: "Required layouts",
    options: ["theatre", "classroom", "boardroom", "banquet"] },
];
const NONE_NEEDED = "None needed";
const NOT_SAVED = "Your changes could not be saved. Check your connection and try again.";
// Must match NON_EDITABLE_STATUSES in backend/app/events/routes.py (SCRUM-53).
const NON_EDITABLE_STATUSES = ["cancelled"];

const nameLabel = (name) => name[0].toUpperCase() + name.slice(1);
const sameName = (a, b) => a.toLowerCase() === b.toLowerCase();

// A saved list: null is not recorded, [] means the event needs none (SCRUM-62 AC5).
function describeNeeds(names) {
  if (names === null) return NOT_RECORDED;
  return names.length ? names.map(nameLabel).join(", ") : NONE_NEEDED;
}

// A group's boxes: the defined names, then any other name saved for the event, so saving
// never drops one silently.
function groupOptions(group, savedNames) {
  const others = (savedNames ?? []).filter((name) => !group.options.some((o) => sameName(o, name)));
  return [...group.options, ...others];
}

function EventRequirements({ eventId, status, requirements, onSaved }) {
  // Per group: null (nothing ticked, not recorded), [] (None needed) or the names ticked.
  const [choices, setChoices] = useState(requirements);
  const [saving, setSaving] = useState(false);
  const [outcome, setOutcome] = useState(null);
  // A reply that arrives after this event was left is not shown (or saved) here.
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  const editable = !NON_EDITABLE_STATUSES.includes(status);

  const ticked = (key, name) => (choices[key] ?? []).some((chosen) => sameName(chosen, name));
  // Keeps the names in the boxes' order, whatever order they were ticked in.
  const toggle = (group, name) => (e) => {
    const names = groupOptions(group, requirements[group.key])
      .filter((option) => (option === name ? e.target.checked : ticked(group.key, option)));
    setChoices((current) => ({ ...current, [group.key]: names.length ? names : null }));
  };
  const toggleNone = (key) => (e) => setChoices((current) => ({ ...current, [key]: e.target.checked ? [] : null }));

  const save = async () => {
    setSaving(true);
    setOutcome(null);
    let reply;
    try {
      const body = Object.fromEntries(REQUIREMENT_GROUPS.map((g) => [g.field, choices[g.key]]));
      reply = { data: (await apiClient.patch(`/events/${eventId}`, body)).data };
    } catch (failure) {
      reply = { failure };
    }
    if (!active.current) return;
    setSaving(false);
    if (reply.data) {
      setChoices(reply.data.requirements);
      setOutcome({ message: reply.data.message });
      onSaved(reply.data);
      return;
    }
    const data = reply.failure.response?.data;
    const message = typeof data?.error === "string" && data.error.trim()
      ? [data.error, ...Object.values(data.fields ?? {})].join(" ") : NOT_SAVED;
    setOutcome({ error: true, message });
  };

  return (
    <section aria-label="Event requirements">
      <h2>Event requirements</h2>
      <p>What the event needs of a venue. The venue suitability check compares each venue with these.</p>
      {REQUIREMENT_GROUPS.map((group) => (
        <fieldset key={group.key}>
          <legend>{group.label}</legend>
          <p>{`Saved: ${describeNeeds(requirements[group.key])}`}</p>
          {editable && groupOptions(group, requirements[group.key]).map((name) => (
            <label key={name}>
              <input type="checkbox" checked={ticked(group.key, name)}
                onChange={toggle(group, name)} disabled={saving} />
              {nameLabel(name)}
            </label>
          ))}
          {editable && (
            <label>
              <input type="checkbox" checked={Array.isArray(choices[group.key]) && !choices[group.key].length}
                onChange={toggleNone(group.key)} disabled={saving} />
              {NONE_NEEDED}
            </label>
          )}
        </fieldset>
      ))}
      {editable ? (
        <button type="button" onClick={save} disabled={saving}>Save requirements</button>
      ) : (
        <p>A cancelled event can&apos;t be edited.</p>
      )}
      {outcome && <p role={outcome.error ? "alert" : "status"}>{outcome.message}</p>}
    </section>
  );
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
              {booking.flag && <p>{booking.flag}</p>}
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
  const [confirmation, setConfirmation] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const confirmationRequest = useRef(null);

  const load = useCallback(async () => {
    // SCRUM-93: a new event invalidates confirmation replies for the previous one.
    confirmationRequest.current = null;
    setConfirming(false);
    setLoadError(null);
    setEvent(null);
    setConfirmation(null);
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
    return () => { confirmationRequest.current = null; };
  }, [load]);

  const confirm = async () => {
    const request = { eventId };
    confirmationRequest.current = request;
    const isStale = () => confirmationRequest.current !== request;
    setConfirming(true);
    setConfirmation(null);
    try {
      const response = await apiClient.post(`/events/${eventId}/confirm`, {});
      if (isStale()) return;
      setEvent((current) => ({ ...current, status: response.data.status }));
      setConfirmation({ message: response.data.message });
    } catch (failure) {
      if (isStale()) return;
      const error = failure.response?.data?.error;
      setConfirmation({ error: true, message: typeof error === "string" && error.trim()
        ? error : "The event was not confirmed. Please try again." });
    } finally {
      if (!isStale()) setConfirming(false);
    }
  };

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
      {/* Planning access already requires the current coordinator (SCRUM-93). */}
      {event.status === "approved" && (
        <button type="button" onClick={confirm} disabled={confirming}>
          {confirming ? "Confirming…" : "Mark event Confirmed"}
        </button>
      )}
      {confirmation && (
        <p role={confirmation.error ? "alert" : "status"}>{confirmation.message}</p>
      )}
      {/* SCRUM-39: only approved events proceed to venue booking (A2). */}
      {event.status === "approved" && (
        <Link to={`/events/${event.id}/venue-request`}>Request a venue</Link>
      )}
      {/* SCRUM-38: a read-only check of a venue against the event's requirements. */}
      <Link to={`/events/${event.id}/venue-suitability`}>Check venue suitability</Link>
      {/* SCRUM-42: record what equipment the event needs, for Technical Support Staff. */}
      <Link to={`/events/${event.id}/equipment`}>Equipment requirements</Link>
      {/* Must match REGISTRABLE_STATUSES in backend/app/registrations/routes.py (SCRUM-93 A4). */}
      {["approved", "confirmed"].includes(event.status) && event.registration_required === true && (
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
      {event.change_review?.needed && (
        <p role="status" aria-label="Change review">
          {`Back in planning for change review: ${event.change_review.reason}`}
        </p>
      )}
      {event.requirements && (
        <EventRequirements key={event.id} eventId={event.id} status={event.status}
          requirements={event.requirements} onSaved={setEvent} />
      )}
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
