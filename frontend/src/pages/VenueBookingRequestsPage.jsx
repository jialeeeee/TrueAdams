import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-39: Venue Staff's list of pending venue requests (GET /api/venues/bookings).
// SCRUM-40: each can be approved (POST /api/venues/bookings/<id>/approve).
// SCRUM-41: each shows its conflicts before anyone approves it.
const NOT_LOADED = "Venue requests could not be loaded. Check your connection and try again.";
const NOT_APPROVED = "The approval was not saved. Check your connection and try again.";

// Booking times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

// One line per conflict, in the order the server lists them.
function conflictText(conflict) {
  const period = `${asText(conflict.start)} to ${asText(conflict.end)}`;
  if (conflict.type === "block") {
    return conflict.reason ? `Blocked (${conflict.reason}), ${period}` : `Blocked, ${period}`;
  }
  if (conflict.type === "booking") {
    return conflict.event
      ? `Confirmed booking for ${conflict.event.title}, ${period}`
      : `Confirmed booking, ${period}`;
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

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/venues/bookings");
      setResult(response.data);
    } catch (failure) {
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, []);

  const approve = async (booking) => {
    setConfirmation("");
    setActionError(null);
    try {
      const response = await apiClient.post(`/venues/bookings/${booking.id}/approve`);
      setConfirmation(response.data.message);
      setResult((current) => ({
        ...current,
        bookings: current.bookings.filter((b) => b.id !== booking.id),
      }));
      // SCRUM-41: reloaded so the remaining requests show any clash with this booking (A6).
      load();
    } catch (failure) {
      // The request stays listed and pending, so it can be approved later (AC5, AC6).
      setActionError({
        message: explain(failure, NOT_APPROVED),
        conflicts: failure.response?.data?.conflicts ?? [],
      });
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
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
