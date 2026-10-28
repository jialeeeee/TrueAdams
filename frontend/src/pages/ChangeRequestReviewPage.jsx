import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import decidedBy from "../utils/decidedBy.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-70: the event's coordinator reviews a change request (SCRUM-46): what it would
// change and affect (AC2), then accepts or rejects it (AC3), via GET
// /api/events/<id>/change-requests/<rid> and POST .../decision.
const NOT_LOADED = "The change request could not be loaded. Check your connection and try again.";
const NOT_SAVED = "The decision was not saved. Check your connection and try again.";
// Must match REASON_MAX_LENGTH in backend/app/events/change_review.py (AC4).
const MAX_REASON_LENGTH = 500;
// Must match REASON_REQUIRED in backend/app/events/change_review.py.
const REASON_REQUIRED = "A reason is required to reject this change request.";
// A reason needs a visible character (SCRUM-60 A3). Must match _has_visible_text in
// backend/app/events/change_review.py.
const VISIBLE = /[^\s\p{C}\p{Z}]/u;
const RECORDED_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

// Event and booking times are Singapore time without a time zone: shown as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

function shown(value) {
  if (value === null || value === undefined) return "none";
  if (typeof value === "string" && RECORDED_TIME.test(value)) return asText(value);
  return String(value);
}

function Reasons({ reasons }) {
  return (
    <ul>
      {reasons.map((reason) => <li key={reason}>{reason}</li>)}
    </ul>
  );
}

// AC2: the venue bookings, equipment and registrations the change affects, and why.
function Impact({ impact }) {
  const { venue_bookings: bookings, equipment, registrations } = impact;
  return (
    <section aria-label="What this change affects">
      <h2>What this change affects</h2>
      {!impact.affected && <p>{impact.message}</p>}
      {bookings.length > 0 && (
        <section aria-label="Venue bookings affected">
          <h3>Venue bookings</h3>
          <ul>
            {bookings.map((booking) => (
              <li key={booking.id}>
                <p>{`${booking.venue.name}, ${asText(booking.start_time)} to ${asText(booking.end_time)} (${statusLabel(booking.status)})`}</p>
                <Reasons reasons={booking.reasons} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {equipment.length > 0 && (
        <section aria-label="Equipment affected">
          <h3>Equipment</h3>
          <ul>
            {equipment.map((item) => (
              <li key={item.id}>
                <p>{`${item.equipment_type} × ${item.quantity}${item.reserved ? ` (${item.reserved} reserved)` : ""}`}</p>
                <Reasons reasons={item.reasons} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {registrations.reasons.length > 0 && (
        <section aria-label="Registrations affected">
          <h3>Registrations</h3>
          <Reasons reasons={registrations.reasons} />
        </section>
      )}
    </section>
  );
}

function Decision({ request }) {
  if (!request.decided_at) return null;
  return (
    <>
      <p>{`${decidedBy(request)} · ${formatSavedAt(request.decided_at)}`}</p>
      {request.decision_reason && <p>{`Reason: ${request.decision_reason}`}</p>}
    </>
  );
}

function ReviewChangeRequest({ eventId, requestId }) {
  const [review, setReview] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Set when the reason itself was refused, here or by the server, to mark the box.
  const [reasonInvalid, setReasonInvalid] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [emailNote, setEmailNote] = useState("");
  const url = `/events/${eventId}/change-requests/${requestId}`;

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(url);
      setReview(response.data);
    } catch (failure) {
      // A failed load is never shown as "nothing affected" (AC2).
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, [url]);

  useEffect(() => {
    load();
  }, [load]);

  const length = text.trim().length;
  const over = length - MAX_REASON_LENGTH;

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
    setEmailNote("");
    try {
      const response = await apiClient.post(
        `${url}/decision`,
        decision === "reject" ? { decision, reason } : { decision },
      );
      const { message, request, notification } = response.data;
      setReview((current) => ({ ...current, request, can_decide: false }));
      setConfirmation(message);
      if (notification && !notification.email_queued) {
        setEmailNote("Some emails could not be sent, but everyone notified will still see it in ConnectSphere.");
      }
      setText("");
    } catch (failure) {
      // The request and the event are unchanged (AC6): the reason stays, as typed, so the
      // decision can be tried again.
      setError(explain(failure, NOT_SAVED));
      setReasonInvalid(failure.response?.data?.field === "reason");
    } finally {
      setBusy(false);
    }
  };

  if (!review) {
    return (
      <section>
        <h1>Review change request</h1>
        {loadError ? (
          <>
            <p role="alert">{loadError.message}</p>
            {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
          </>
        ) : (
          <p>Loading…</p>
        )}
      </section>
    );
  }

  const { event, request, impact } = review;
  return (
    <section>
      <Link to="/events/change-requests">Back to change requests</Link>
      <h1>{`Review change request: ${event.title}`}</h1>
      <p>{`Requested by ${request.requested_by?.email ?? "not recorded"} on ${formatSavedAt(request.requested_at)}`}</p>
      <p>{`Status: ${request.status_label}`}</p>
      <Decision request={request} />
      {!confirmation && review.message && <p>{review.message}</p>}
      <ul aria-label="Requested changes">
        {request.changes.map((change) => (
          <li key={change.field}>{`${change.label}: ${shown(change.from)} → ${shown(change.to)}`}</li>
        ))}
      </ul>
      {/* Only before deciding (AC2): afterwards it no longer describes the event. */}
      {impact && request.status === "pending_review" && <Impact impact={impact} />}

      {confirmation && <p role="status">{confirmation}</p>}
      {emailNote && <p>{emailNote}</p>}

      {review.can_decide && (
        <form aria-label="Decision" onSubmit={(e) => e.preventDefault()}>
          <label htmlFor="change-decision-reason">Reason for rejecting (required to reject)</label>
          <textarea
            id="change-decision-reason"
            rows={4}
            value={text}
            aria-invalid={reasonInvalid}
            aria-describedby={error ? "change-decision-error" : undefined}
            onChange={(e) => {
              setText(e.target.value);
              // A refused reason's message goes once the coordinator edits it.
              if (reasonInvalid) {
                setError("");
                setReasonInvalid(false);
              }
            }}
          />
          <p>{`${length} / ${MAX_REASON_LENGTH} characters`}</p>
          {over > 0 && (
            <p>
              {`That is over the ${MAX_REASON_LENGTH}-character limit. Remove ${over} character${over === 1 ? "" : "s"} to continue.`}
            </p>
          )}
          {error && <p role="alert" id="change-decision-error">{error}</p>}
          <button type="button" className="btn-primary" onClick={() => decide("accept")} disabled={busy}>
            Accept
          </button>
          <button type="button" onClick={() => decide("reject")} disabled={busy || over > 0}>
            Reject
          </button>
        </form>
      )}
    </section>
  );
}

export default function ChangeRequestReviewPage() {
  const { eventId, requestId } = useParams();
  // A fresh page for each request: a reply for the previous one can never show here.
  return <ReviewChangeRequest key={`${eventId}/${requestId}`} eventId={eventId} requestId={requestId} />;
}
