import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// Must match MAX_DECISION_WORDS in backend/app/events/routes.py.
const MAX_WORDS = 1000;

// The organiser's request fields (SCRUM-29), in display order.
const DETAILS = [
  ["purpose", "Purpose"],
  ["description", "Description"],
  ["start_time", "Start"],
  ["end_time", "End"],
  ["expected_attendance", "Expected attendance"],
  ["venue_requirements", "Venue requirements"],
  ["accessibility_needs", "Accessibility needs"],
  ["equipment_requirements", "Equipment requirements"],
  ["registration_required", "Attendee registration needed"],
];

function countWords(text) {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function display(field, value) {
  if (value === null || value === undefined || value === "") return "Not provided";
  if (field === "registration_required") return value ? "Yes" : "No";
  // Proposed times are Singapore time without a time zone: show them as recorded.
  if (field.endsWith("_time")) return value.slice(0, 16).replace("T", " ");
  return String(value);
}

function explain(failure, fallback) {
  const error = failure.response?.data?.error;
  return typeof error === "string" && error.trim() ? error : fallback;
}

export default function ReviewRequestPage() {
  const { eventId } = useParams();
  const [request, setRequest] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [emailNote, setEmailNote] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get(`/events/${eventId}/review`);
      setRequest(response.data.request);
    } catch (failure) {
      setLoadError(explain(failure, "The request could not be loaded. Please try again."));
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const words = countWords(text);
  const over = words - MAX_WORDS;

  const decide = async (decision) => {
    setBusy(true);
    setError("");
    setConfirmation("");
    setEmailNote("");
    const reason = text.trim();
    try {
      const response = await apiClient.post(
        `/events/${eventId}/decision`,
        reason ? { decision, reason } : { decision },
      );
      const { message, request: decided, notification } = response.data;
      setRequest(decided);
      setConfirmation(message);
      if (notification && !notification.email_queued) {
        setEmailNote("The email could not be sent, but the organiser will still see the outcome in ConnectSphere.");
      }
      setText("");
    } catch (failure) {
      // The typed reason stays in the box so the decision can be tried again.
      setError(explain(failure, "The decision was not saved. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  };

  if (loadError) {
    return (
      <section>
        <p role="alert">{loadError}</p>
        <button type="button" onClick={load}>Retry</button>
      </section>
    );
  }

  if (!request) return <p>Loading…</p>;

  const undecided = request.status === "submitted";

  return (
    <section>
      <h1>Review: {request.title}</h1>
      <p>{`Status: ${statusLabel(request.status)}`}</p>
      {request.decision_note && (
        <p>{`${request.status === "rejected" ? "Reason" : "Note"}: ${request.decision_note}`}</p>
      )}
      {request.decided_at && (
        <p>
          Decided {formatSavedAt(request.decided_at)}
          {request.decided_by ? ` by ${request.decided_by.email}` : ""}
        </p>
      )}

      <dl>
        {DETAILS.map(([field, label]) => (
          <div key={field}>
            <dt>{label}</dt>
            <dd>{display(field, request[field])}</dd>
          </div>
        ))}
      </dl>

      {confirmation && <p role="status">{confirmation}</p>}
      {emailNote && <p>{emailNote}</p>}

      {undecided && (
        <form onSubmit={(e) => e.preventDefault()}>
          <label htmlFor="decision-reason">
            Reason or note (a reason is required to reject)
          </label>
          <textarea
            id="decision-reason"
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <p>{`${words} / ${MAX_WORDS} words`}</p>
          {over > 0 && (
            <p>
              That is over the 1,000-word limit. Remove {over} word{over === 1 ? "" : "s"} to continue.
            </p>
          )}
          {error && <p role="alert">{error}</p>}
          <button type="button" onClick={() => decide("approve")} disabled={busy || over > 0}>
            Approve
          </button>
          <button type="button" onClick={() => decide("reject")} disabled={busy || words === 0 || over > 0}>
            Reject
          </button>
        </form>
      )}
    </section>
  );
}
