import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-88 AC2: Venue Staff's confirmed bookings flagged "Venue unavailable: replacement
// needed" (GET /api/venues/replacement-needed). Nothing here changes a booking.
const NOT_LOADED = "Bookings needing a replacement could not be loaded. Check your connection and try again.";

// Times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

export default function ReplacementNeededPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setResult((await apiClient.get("/venues/replacement-needed")).data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Replacement venues needed</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {result && result.bookings.length === 0 && <p>{result.message}</p>}
      {result && result.bookings.length > 0 && (
        <ul>
          {result.bookings.map((booking) => {
            const title = booking.event ? booking.event.title : `Booking ${booking.id}`;
            return (
              <li key={booking.id} aria-label={title}>
                <h2>{title}</h2>
                <p>{booking.flag}</p>
                <p>{`Venue: ${booking.venue.name}${booking.venue.location ? `, ${booking.venue.location}` : ""}`}</p>
                <p>{`Booked: ${asText(booking.start_time)} to ${asText(booking.end_time)}`}</p>
                <p>{`Status: ${statusLabel(booking.status)}`}</p>
                <p>{`Unavailable: ${asText(booking.period.start_time)} to ${asText(booking.period.end_time)} (${booking.period.reason})`}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
