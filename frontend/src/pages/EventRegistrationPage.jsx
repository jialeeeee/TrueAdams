import { useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";

// Registration statuses as shown to attendees.
const STATUS_LABELS = { registered: "Registered", waitlisted: "Waitlisted" };
const NOT_SAVED = "Your registration was not saved. Check your connection and try again.";

function explain(failure) {
  const error = failure.response?.data?.error;
  return typeof error === "string" && error.trim() ? error : NOT_SAVED;
}

export default function EventRegistrationPage() {
  const { eventId } = useParams();
  const [sending, setSending] = useState(false);
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState(null);

  async function register() {
    // Also guards against a second click before the button re-renders as disabled.
    if (sending) return;
    setSending(true);
    setError(null);
    try {
      const { data } = await apiClient.post("/registrations/", { event_id: Number(eventId) });
      setOutcome({ message: data.message, status: data.registration.status });
    } catch (failure) {
      setError(explain(failure));
    } finally {
      setSending(false);
    }
  }

  return (
    <section>
      <h1>Register for this event</h1>
      {outcome ? (
        <>
          <p role="status">{outcome.message}</p>
          <p>{`Status: ${STATUS_LABELS[outcome.status] ?? outcome.status}`}</p>
        </>
      ) : (
        <button type="button" onClick={register} disabled={sending}>
          {sending ? "Registering…" : "Register"}
        </button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
