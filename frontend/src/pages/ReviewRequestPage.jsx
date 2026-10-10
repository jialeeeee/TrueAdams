import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import decidedBy from "../utils/decidedBy.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// Must match MAX_DECISION_WORDS in backend/app/events/routes.py.
const MAX_WORDS = 1000;
// A reason needs at least one visible character: spaces of any kind, including
// invisible ones such as zero-width spaces, are not a reason (SCRUM-60 A3).
// Must match _has_visible_text in backend/app/events/routes.py.
const VISIBLE = /[^\s\p{C}\p{Z}]/u;
// Must match REASON_REQUIRED in backend/app/events/routes.py.
const REASON_REQUIRED = "A reason is required to reject this request.";

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
  // Set when the reason itself was refused, here or by the server, to mark the box.
  const [reasonInvalid, setReasonInvalid] = useState(false);
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
    const reason = VISIBLE.test(text) ? text.trim() : "";
    if (decision === "reject" && !reason) {
      setError(REASON_REQUIRED);
      setReasonInvalid(true);
      return;
    }
    setBusy(true);
    setError("");
    setReasonInvalid(false);
    setConfirmation("");
    setEmailNote("");
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
      // The typed reason stays in the box, as typed, so the decision can be tried again.
      setError(explain(failure, "The decision was not saved. Check your connection and try again."));
      setReasonInvalid(failure.response?.data?.field === "reason");
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
        <>
          <p>{`Decided ${formatSavedAt(request.decided_at)}`}</p>
          <p>{decidedBy(request)}</p>
        </>
      )}

      <dl>
        {DETAILS.map(([field, label]) => (
          <div key={field}>
            <dt>{label}</dt>
            <dd>{display(field, request[field])}</dd>
          </div>
        ))}
      </dl>

      {confirmation && (
        <div role="status">
          <p>{confirmation}</p>
          <p>{`${decidedBy(request)} · ${formatSavedAt(request.decided_at)}`}</p>
        </div>
      )}
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
            aria-invalid={reasonInvalid}
            aria-describedby={error ? "decision-error" : undefined}
            onChange={(e) => {
              setText(e.target.value);
              // A refused reason's message goes once the coordinator edits it.
              if (reasonInvalid) {
                setError("");
                setReasonInvalid(false);
              }
            }}
          />
          <p>{`${words} / ${MAX_WORDS} words`}</p>
          {over > 0 && (
            <p>
              That is over the 1,000-word limit. Remove {over} word{over === 1 ? "" : "s"} to continue.
            </p>
          )}
          {error && <p role="alert" id="decision-error">{error}</p>}
          <button type="button" onClick={() => decide("approve")} disabled={busy || over > 0}>
            Approve
          </button>
          <button type="button" onClick={() => decide("reject")} disabled={busy || over > 0}>
            Reject
          </button>
        </form>
      )}
    </section>
  );
}
