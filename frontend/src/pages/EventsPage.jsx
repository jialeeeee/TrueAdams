import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";

// The published events, each opening its details (SCRUM-74).
const NOT_LOADED = "Events could not be loaded. Check your connection and try again.";

export default function EventsPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/");
      setResult(response.data);
    } catch (failure) {
      if (failure.response?.status === 401) {
        navigate("/login");
        return;
      }
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, [navigate]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Events</h1>

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
              <Link to={`/events/${event.id}`}>{event.title}</Link>
              <p>{`Starts: ${singaporeTime(event.start_time)}`}</p>
              <p>{`Registration: ${event.registration_state.charAt(0).toUpperCase()}${event.registration_state.slice(1)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
