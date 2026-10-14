import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";

// A coordinator asks for one of their events to be handed to another coordinator (SCRUM-61).
// Must match MAX_REASON_LENGTH in backend/app/events/routes.py.
const MAX_REASON_LENGTH = 500;
const NOT_LOADED = "The reassignment form could not be loaded. Check your connection and try again.";
const NOT_SAVED = "Your request was not saved. Check your connection and try again.";

export default function ReassignmentRequestPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [coordinatorId, setCoordinatorId] = useState("");
  const [reason, setReason] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get(`/events/${eventId}/reassignment`);
      setForm(response.data);
    } catch (failure) {
      if (failure.response?.status === 401) {
        navigate("/login");
        return;
      }
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, [eventId, navigate]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(event) {
    event.preventDefault();
    // Also guards against a second submit before the button re-renders as disabled.
    if (sending) return;
    setError("");
    if (!coordinatorId) {
      setError("Choose a coordinator.");
      return;
    }
    const trimmed = reason.trim();
    if (!trimmed) {
      setError("Enter a reason for the reassignment.");
      return;
    }
    if (trimmed.length > MAX_REASON_LENGTH) {
      setError(`The reason must be ${MAX_REASON_LENGTH} characters or fewer.`);
      return;
    }
    setSending(true);
    try {
      const response = await apiClient.post(`/events/${eventId}/reassignment`, {
        coordinator_id: Number(coordinatorId),
        reason: trimmed,
      });
      setConfirmation(response.data.message);
    } catch (failure) {
      setError(explain(failure, NOT_SAVED));
      setSending(false);
    }
  }

  if (loadError) {
    return (
      <section>
        <p role="alert">{loadError}</p>
        <button type="button" onClick={load}>Retry</button>
      </section>
    );
  }
  if (!form) return null;

  const pending = form.pending_request;
  return (
    <section>
      <h1>Request reassignment</h1>
      <p>{form.event.title}</p>

      {confirmation && (
        <>
          <p role="status">{confirmation}</p>
          <p>Status: Pending</p>
        </>
      )}
      {!confirmation && form.message && <p>{form.message}</p>}
      {!confirmation && pending && (
        <p>{`Status: ${pending.status.charAt(0).toUpperCase()}${pending.status.slice(1)}`}</p>
      )}

      {!confirmation && form.can_request && (
        <form onSubmit={submit}>
          <label htmlFor="coordinator">New coordinator</label>
          <select
            id="coordinator"
            value={coordinatorId}
            onChange={(event) => setCoordinatorId(event.target.value)}
          >
            <option value="">Choose a coordinator</option>
            {form.coordinators.map((coordinator) => (
              <option key={coordinator.id} value={coordinator.id}>
                {coordinator.email}
              </option>
            ))}
          </select>

          <label htmlFor="reason">Reason</label>
          <textarea
            id="reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />

          {error && <p role="alert">{error}</p>}
          <button type="submit" className="btn-primary" disabled={sending}>
            Submit request
          </button>
        </form>
      )}
    </section>
  );
}
