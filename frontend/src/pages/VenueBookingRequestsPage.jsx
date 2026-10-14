import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-39: Venue Staff's list of pending venue requests (GET /api/venues/bookings).
const NOT_LOADED = "Venue requests could not be loaded. Check your connection and try again.";

// Booking times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

export default function VenueBookingRequestsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/venues/bookings");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(typeof error === "string" && error.trim() ? error : NOT_LOADED);
    }
  }, []);

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
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
