import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import occupiedParts from "../utils/occupiedParts.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-39: Venue Staff's list of pending venue requests (GET /api/venues/bookings).
// SCRUM-40: each can be approved (POST /api/venues/bookings/<id>/approve).
// SCRUM-41: each shows its conflicts before anyone approves it.
// SCRUM-87: each can be placed on a tentative hold (POST /api/venues/bookings/<id>/hold).
const NOT_LOADED = "Venue requests could not be loaded. Check your connection and try again.";
const NOT_APPROVED = "The approval was not saved. Check your connection and try again.";
const NOT_HELD = "The hold was not placed. Check your connection and try again.";
const NOT_REJECTED = "The rejection was not saved. Check your connection and try again.";
// Must match MAX_REJECTION_REASON_LENGTH in backend/app/venues/routes.py (SCRUM-69 AC3).
const MAX_REJECTION_REASON_LENGTH = 500;

// Booking times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

// SCRUM-84: a booking's period includes its setup and turnaround, which are labelled.
const withParts = (text, item) => {
  const parts = occupiedParts(item);
  return parts ? `${text} (${parts})` : text;
};

// One line per conflict, in the order the server lists them.
function conflictText(conflict) {
  const period = `${asText(conflict.start)} to ${asText(conflict.end)}`;
  if (conflict.type === "block") {
    return conflict.reason ? `Blocked (${conflict.reason}), ${period}` : `Blocked, ${period}`;
  }
  if (conflict.type === "booking") {
    const text = conflict.event
      ? `Confirmed booking for ${conflict.event.title}, ${period}`
      : `Confirmed booking, ${period}`;
    return withParts(text, conflict);
  }
  if (conflict.type === "hold") {
    return withParts(
      `Tentative hold for ${conflict.event.title} until ${asText(conflict.expires_at)}, ${period}`,
      conflict,
    );
  }
  return `This event's confirmed booking at ${conflict.venue.name}, ${period}`;
}

function ConflictList({ conflicts, label }) {
  return (
    <ul aria-label={label}>
      {conflicts.map((conflict) => (
        <li key={`${conflict.type}-${conflict.id}`}>{conflictText(conflict)}</li>
      ))}
    </ul>
  );
}

export default function VenueBookingRequestsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [actionError, setActionError] = useState(null);
  // The hold expiry entered for each request, by booking ID (SCRUM-87).
  const [expiries, setExpiries] = useState({});
  const [reasons, setReasons] = useState({});
  const [rejecting, setRejecting] = useState(null);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/venues/bookings");
      setResult(response.data);
    } catch (failure) {
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, []);

  // Approving (SCRUM-40) or holding (SCRUM-87) a request: on success the request leaves
  // the list, which is reloaded so the rest show any new clash (SCRUM-41 A6). On failure
  // it stays listed and pending, with what was entered, so it can be tried again.
  const decide = async (booking, send, fallback) => {
    setConfirmation("");
    setActionError(null);
    try {
      const response = await send();
      setConfirmation(response.data.message);
      setResult((current) => ({
        ...current,
        bookings: current.bookings.filter((b) => b.id !== booking.id),
      }));
      load();
    } catch (failure) {
      setActionError({
        message: explain(failure, fallback),
        conflicts: failure.response?.data?.conflicts ?? [],
      });
    }
  };

  const approve = (booking) =>
    decide(booking, () => apiClient.post(`/venues/bookings/${booking.id}/approve`), NOT_APPROVED);

  const placeHold = (booking) =>
    decide(
      booking,
      () => apiClient.post(`/venues/bookings/${booking.id}/hold`, { expires_at: expiries[booking.id] }),
      NOT_HELD,
    );

  const reject = async (booking) => {
    const reason = (reasons[booking.id] ?? "").trim();
    const problem = !reason ? "A rejection reason is required."
      : [...reason].length > MAX_REJECTION_REASON_LENGTH
        ? `The rejection reason must be ${MAX_REJECTION_REASON_LENGTH} characters or fewer.` : "";
    if (problem) {
      setConfirmation("");
      setActionError({ message: problem, conflicts: [] });
      return;
    }
    setRejecting(booking.id);
    try {
      await decide(booking, () => apiClient.post(`/venues/bookings/${booking.id}/reject`, { reason }),
        NOT_REJECTED);
    } finally {
      setRejecting(null);
    }
  };

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Venue booking requests</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}

      {confirmation && <p role="status">{confirmation}</p>}
      {actionError && (
        <div role="alert">
          <p>{actionError.message}</p>
          {actionError.conflicts.length > 0 && <ConflictList conflicts={actionError.conflicts} />}
        </div>
      )}

      {result && result.bookings.length === 0 && <p>{result.message}</p>}
      {result && result.bookings.length > 0 && (
        <ul>
          {result.bookings.map((booking) => (
            <li key={booking.id} aria-label={booking.event.title}>
              <h2>{booking.event.title}</h2>
              <p>
                {`Venue: ${booking.venue.name}${booking.venue.location ? `, ${booking.venue.location}` : ""}`}
              </p>
              <p>{`Requested: ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
              {(booking.setup_minutes > 0 || booking.turnaround_minutes > 0) && (
                <p>
                  {`Occupied: ${asText(booking.occupied_start)} to ${asText(booking.occupied_end)} `
                    + `(setup ${booking.setup_minutes} min, turnaround ${booking.turnaround_minutes} min)`}
                </p>
              )}
              <p>{`Expected attendance: ${booking.event.expected_attendance ?? "Not recorded"}`}</p>
              <p>{`Requirements: ${booking.venue_requirements}`}</p>
              <p>
                {`Requested by ${booking.requested_by?.email ?? "an unknown user"} on ${formatSavedAt(booking.requested_at)}`}
              </p>
              <p>{`Status: ${statusLabel(booking.status)}`}</p>
              {booking.conflicts.length === 0 ? (
                <p>No conflicts found.</p>
              ) : (
                <ConflictList
                  conflicts={booking.conflicts}
                  label={`Conflicts for ${booking.event.title}`}
                />
              )}
              <button
                type="button"
                aria-label={`Approve booking for ${booking.event.title}`}
                onClick={() => approve(booking)}
              >
                Approve
              </button>
              <label htmlFor={`hold-expiry-${booking.id}`}>Hold expires</label>
              <input
                id={`hold-expiry-${booking.id}`}
                type="datetime-local"
                aria-label={`Hold expiry for ${booking.event.title}`}
                value={expiries[booking.id] ?? ""}
                onChange={(e) => setExpiries((current) => ({ ...current, [booking.id]: e.target.value }))}
              />
              <button
                type="button"
                aria-label={`Place tentative hold for ${booking.event.title}`}
                onClick={() => placeHold(booking)}
              >
                Place tentative hold
              </button>
              <label htmlFor={`rejection-reason-${booking.id}`}>Rejection reason</label>
              <textarea
                id={`rejection-reason-${booking.id}`}
                aria-label={`Rejection reason for ${booking.event.title}`}
                value={reasons[booking.id] ?? ""}
                onChange={(e) => setReasons((current) => ({ ...current, [booking.id]: e.target.value }))}
                rows={3}
              />
              <button
                type="button"
                aria-label={`Reject booking for ${booking.event.title}`}
                disabled={rejecting !== null}
                onClick={() => reject(booking)}
              >
                Reject
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
