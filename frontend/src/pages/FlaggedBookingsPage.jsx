import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import occupiedParts from "../utils/occupiedParts.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-84 AC5: the pending, tentative and confirmed bookings flagged "Setup or turnaround
// conflict" after a venue's setup or turnaround time changed (GET /api/venues/flagged-bookings).
// Nothing here changes a booking: Venue Staff decide what to do about each one.
const NOT_LOADED = "Flagged bookings could not be loaded. Check your connection and try again.";

// Booking times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

export default function FlaggedBookingsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get("/venues/flagged-bookings");
      setResult(response.data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Setup or turnaround conflicts</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {result && result.bookings.length === 0 && <p>{result.message}</p>}
      {result && result.bookings.length > 0 && (
        <ul>
          {result.bookings.map((booking) => (
            <li key={booking.id} aria-label={booking.event ? booking.event.title : `Booking ${booking.id}`}>
              <h2>{booking.event ? booking.event.title : `Booking ${booking.id}`}</h2>
              <p>{booking.flag}</p>
              <p>{`Venue: ${booking.venue.name}${booking.venue.location ? `, ${booking.venue.location}` : ""}`}</p>
              <p>{`Event time: ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
              <p>{`Occupied: ${asText(booking.occupied_start)} to ${asText(booking.occupied_end)}`}</p>
              {occupiedParts(booking) && <p>{occupiedParts(booking)}</p>}
              <p>{`Status: ${statusLabel(booking.status)}`}</p>
              {booking.overlaps.length > 0 && (
                <p>{`Overlaps booking ${booking.overlaps.join(", ")}`}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
