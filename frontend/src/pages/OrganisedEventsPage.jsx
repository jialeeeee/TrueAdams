import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import statusLabel from "../utils/statusLabel.js";

export default function OrganisedEventsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/organised");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(typeof error === "string" && error.trim()
        ? error
        : "Your events' registration information could not be loaded. Check your connection and try again.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Registrations for my events</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}

      {result && result.events.length === 0 && <p>{result.message}</p>}
      {result && result.events.length > 0 && (
        <ul>
          {result.events.map((event) => (
            <li key={event.id}>
              <Link to={`/events/${event.id}/registrations`}>{event.title || "Not recorded"}</Link>
              <p>{`Proposed date: ${event.start_time ? event.start_time.slice(0, 16).replace("T", " ") : "Not recorded"}`}</p>
              <p>{`Status: ${statusLabel(event.status)}`}</p>
              <p>{`Registrations: ${event.registration.registered_count}`}</p>
              <p>{`Capacity: ${event.registration.capacity ?? "Not set up"}`}</p>
              <p>{`Remaining places: ${event.registration.slots_remaining ?? "Not set up"}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
