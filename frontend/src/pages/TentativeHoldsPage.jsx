import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";

// SCRUM-87: Venue Staff's unexpired tentative holds (GET /api/venues/holds), each of
// whose expiry can be changed (PATCH /api/venues/bookings/<id>/hold).
const NOT_LOADED = "Tentative holds could not be loaded. Check your connection and try again.";
const NOT_CHANGED = "The new expiry was not saved. Check your connection and try again.";

// Booking times and expiries are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");
const asInput = (value) => value.slice(0, 16);

export default function TentativeHoldsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);
  // The new expiry entered for each hold, by booking ID, starting at its current expiry.
  const [expiries, setExpiries] = useState({});
  const [confirmation, setConfirmation] = useState("");
  const [actionError, setActionError] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get("/venues/holds");
      setResult(response.data);
      setExpiries(Object.fromEntries(
        response.data.holds.map((hold) => [hold.id, asInput(hold.hold.expires_at)]),
      ));
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const changeExpiry = async (hold) => {
    setConfirmation("");
    setActionError("");
    try {
      const response = await apiClient.patch(`/venues/bookings/${hold.id}/hold`, {
        expires_at: expiries[hold.id],
      });
      setConfirmation(response.data.message);
      load();
    } catch (failure) {
      // The hold and the entered expiry stay, so the change can be tried again (AC7).
      setActionError(explain(failure, NOT_CHANGED));
    }
  };

  return (
    <section>
      <h1>Tentative holds</h1>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {confirmation && <p role="status">{confirmation}</p>}
      {actionError && <p role="alert">{actionError}</p>}

      {result && result.holds.length === 0 && <p>{result.message}</p>}
      {result && result.holds.length > 0 && (
        <ul>
          {result.holds.map((hold) => (
            <li key={hold.id} aria-label={hold.event.title}>
              <h2>{hold.event.title}</h2>
              <p>{`Venue: ${hold.venue.name}${hold.venue.location ? `, ${hold.venue.location}` : ""}`}</p>
              <p>{`Held: ${asText(hold.start_time)} to ${asText(hold.end_time)}`}</p>
              <p>{`Expires: ${asText(hold.hold.expires_at)}`}</p>
              <p>{`Held by ${hold.hold.held_by.email} on ${formatSavedAt(hold.hold.held_at)}`}</p>
              <label htmlFor={`new-expiry-${hold.id}`}>New expiry</label>
              <input
                id={`new-expiry-${hold.id}`}
                type="datetime-local"
                aria-label={`New expiry for ${hold.event.title}`}
                value={expiries[hold.id] ?? ""}
                onChange={(e) => setExpiries((current) => ({ ...current, [hold.id]: e.target.value }))}
              />
              <button
                type="button"
                aria-label={`Change expiry for ${hold.event.title}`}
                onClick={() => changeExpiry(hold)}
              >
                Change expiry
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
