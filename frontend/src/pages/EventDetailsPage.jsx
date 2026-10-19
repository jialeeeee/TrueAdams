import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import singaporeTime from "../utils/singaporeTime.js";
import statusLabel from "../utils/statusLabel.js";

// One event's details, with the actions the viewer may take on it (SCRUM-74).
const NOT_LOADED = "The event could not be loaded. Check your connection and try again.";
const NOT_PROVIDED = "Not provided";
// Published events (everyone sees them) need no status line. Must match
// PUBLISHED_STATUSES in backend/app/events/routes.py.
const PUBLISHED_STATUS = "approved";

function provided(value) {
  return value === null || value === undefined || value === "" ? NOT_PROVIDED : String(value);
}

function when(value) {
  return value ? singaporeTime(value) : NOT_PROVIDED;
}

// SCRUM-33: the event's current coordinator. Only some users may see it (admins,
// coordinators, venue and tech staff, and the event's organiser; can_view_coordinator
// in backend/app/events/permissions.py), so a refusal hides the section instead of
// showing an error.
const COORDINATOR_NOT_LOADED =
  "The coordinator could not be loaded. Check your connection and try again.";
const COORDINATOR_HIDDEN_STATUSES = [401, 403, 404];

function EventCoordinator({ eventId }) {
  const [assignment, setAssignment] = useState(null);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(false);

  // The error stays until a reload succeeds, so the section never blinks out mid-reload.
  const load = useCallback(async () => {
    try {
      const response = await apiClient.get(`/events/${eventId}/coordinator`);
      setAssignment(response.data);
      setError("");
    } catch (failure) {
      if (COORDINATOR_HIDDEN_STATUSES.includes(failure.response?.status)) {
        setHidden(true);
        return;
      }
      setError(explain(failure, COORDINATOR_NOT_LOADED));
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  if (hidden || (!assignment && !error)) return null;

  const coordinator = assignment?.coordinator;
  return (
    <section aria-labelledby="event-coordinator">
      <h2 id="event-coordinator">Coordinator</h2>
      {error ? (
        <>
          <p role="alert">{error}</p>
          <button type="button" onClick={load}>Reload coordinator</button>
        </>
      ) : coordinator ? (
        <>
          <p>{`Coordinator: ${coordinator.email}`}</p>
          {/* Assignment times are saved in UTC, unlike the event's own times. */}
          <p>{`Assigned: ${assignment.assigned_at ? formatSavedAt(assignment.assigned_at) : "Not recorded"}`}</p>
        </>
      ) : (
        <p>No coordinator has been assigned yet.</p>
      )}
    </section>
  );
}

export default function EventDetailsPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    setError("");
    setNotFound(false);
    try {
      const response = await apiClient.get(`/events/${eventId}`);
      setEvent(response.data.event);
    } catch (failure) {
      const status = failure.response?.status;
      if (status === 401) {
        navigate("/login");
        return;
      }
      if (status === 404) {
        setNotFound(true);
        return;
      }
      setError(explain(failure, NOT_LOADED));
    }
  }, [eventId, navigate]);

  useEffect(() => {
    load();
  }, [load]);

  if (notFound) {
    return (
      <section>
        <p role="alert">Event not found.</p>
        <Link to="/">Back to events</Link>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <p role="alert">{error}</p>
        <button type="button" onClick={load}>Retry</button>
      </section>
    );
  }
  if (!event) return null;

  const registration = event.registration;
  const state = `${registration.state.charAt(0).toUpperCase()}${registration.state.slice(1)}`;
  return (
    <section>
      <h1>{event.title}</h1>
      {event.status !== PUBLISHED_STATUS && <p>{`Status: ${statusLabel(event.status)}`}</p>}
      <p>{`Description: ${provided(event.description)}`}</p>
      <p>{`Starts: ${when(event.start_time)}`}</p>
      <p>{`Ends: ${when(event.end_time)}`}</p>
      <p>{`Venue: ${provided(event.venue?.name)}`}</p>
      <p>{`Location: ${provided(event.venue?.location)}`}</p>
      <p>{`Registration opens: ${when(registration.opens_at)}`}</p>
      <p>{`Registration closes: ${when(registration.closes_at)}`}</p>
      <p>{`Capacity: ${provided(registration.capacity)}`}</p>
      <p>{`Slots remaining: ${provided(registration.slots_remaining)}`}</p>
      <p>{`Registration: ${state}`}</p>
      {event.my_registration && (
        <p>{`Your registration: ${statusLabel(event.my_registration.status)}`}</p>
      )}
      {event.can_register && <Link to={`/events/${event.id}/register`}>Register</Link>}
      {event.can_request_reassignment && (
        <Link to={`/events/${event.id}/reassign`}>Request reassignment</Link>
      )}
      <EventCoordinator eventId={event.id} />
    </section>
  );
}
