import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";

// Must match MAX_CLARIFICATION_WORDS in backend/app/events/routes.py.
const MAX_WORDS = 1000;
// SCRUM-95: reuse the existing request text fields and normal-field validators.
// Must match the text entries in NORMAL_FIELD_VALIDATORS in backend/app/events/routes.py.
const EDIT_FIELDS = [
  ["title", "Event name"], ["purpose", "Purpose"],
  ["description", "Description"], ["accessibility_needs", "Accessibility needs"],
];

// Words are runs of characters between whitespace, as the backend counts them.
function countWords(text) {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function serverError(failure, fallback) {
  const explanation = failure.response?.data?.error;
  return typeof explanation === "string" && explanation.trim() ? explanation : fallback;
}

export default function ClarificationPage() {
  const { eventId } = useParams();
  const url = `/events/${eventId}/clarifications`;

  const [thread, setThread] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [emailNote, setEmailNote] = useState("");
  const [edits, setEdits] = useState({});

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get(url);
      setThread(response.data);
      setEdits(Object.fromEntries(EDIT_FIELDS.map(([name]) => [name, response.data.editable_fields?.[name] ?? ""])));
    } catch (failure) {
      setLoadError(serverError(failure, "The questions could not be loaded. Please try again."));
    }
  }, [url]);

  useEffect(() => {
    load();
  }, [load]);

  const words = countWords(question);
  const over = words - MAX_WORDS;
  const canSend = words > 0 && over <= 0 && !sending;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!canSend) return;
    setSending(true);
    setSendError("");
    setConfirmation("");
    setEmailNote("");
    try {
      const resubmitting = thread.can_resubmit === true;
      const changes = Object.fromEntries(EDIT_FIELDS
        .filter(([name]) => edits[name] !== (thread.editable_fields?.[name] ?? ""))
        .map(([name]) => [name, edits[name]]));
      const response = resubmitting
        ? await apiClient.post(`/events/${eventId}/resubmit`, { message: question.trim(), changes })
        : await apiClient.post(url, { message: question.trim() });
      const { message, clarification, notification, request } = response.data;
      setConfirmation(message);
      if (notification && !notification.email_queued) {
        setEmailNote(
          resubmitting
            ? "The email could not be sent, but the coordinator will still see your reply in ConnectSphere."
            : "The email could not be sent, but the organiser will still see your question in ConnectSphere.",
        );
      }
      setThread((current) => ({
        ...current,
        event: request ? { ...current.event, ...request } : current.event,
        clarifications: clarification ? [...current.clarifications, clarification] : current.clarifications,
        ...(resubmitting ? { can_resubmit: false } : {}),
        message: null,
      }));
      setQuestion("");
    } catch (failure) {
      // SCRUM-95 AC5: the reply and unsaved edits stay available for retry.
      setSendError(
        [serverError(failure, thread.can_resubmit
          ? "Your reply and changes were not saved. Check your connection and try again."
          : "Your question was not sent. Check your connection and try again."),
        ...Object.values(failure.response?.data?.fields ?? {})].join(" "),
      );
    } finally {
      setSending(false);
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

  if (!thread) {
    return <p>Loading…</p>;
  }

  const { event, clarifications } = thread;

  return (
    <section>
      <h1>Clarification questions: {event.title}</h1>
      <p>
        Organiser: {event.organiser.email} · Status: {event.status}
      </p>

      {clarifications.length === 0 ? (
        <p>{thread.message}</p>
      ) : (
        <ol>
          {clarifications.map((clarification) => (
            <li key={clarification.id}>
              <p>{clarification.message}</p>
              <small>
                {clarification.sender.email} · {clarification.created_at}
              </small>
            </li>
          ))}
        </ol>
      )}

      {(thread.can_resubmit || thread.can_send !== false) && <form onSubmit={handleSubmit}>
        {thread.can_resubmit && EDIT_FIELDS.map(([name, label]) => (
          <div key={name}>
            <label htmlFor={`reply-${name}`}>{label}</label>
            {name === "title" ? (
              <input id={`reply-${name}`} value={edits[name] ?? ""} disabled={sending}
                onChange={(e) => setEdits((current) => ({ ...current, [name]: e.target.value }))} />
            ) : (
              <textarea id={`reply-${name}`} rows={3} value={edits[name] ?? ""} disabled={sending}
                onChange={(e) => setEdits((current) => ({ ...current, [name]: e.target.value }))} />
            )}
          </div>
        ))}
        <label htmlFor="clarification-question">{thread.can_resubmit ? "Your reply" : "Your question"}</label>
        <textarea
          id="clarification-question"
          rows={6}
          value={question}
          disabled={sending}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <p>{`${words} / ${MAX_WORDS} words`}</p>
        {over > 0 && (
          <p>
            That is over the 1,000-word limit. Remove {over} word{over === 1 ? "" : "s"} to send.
          </p>
        )}
        <button type="submit" disabled={!canSend}>{thread.can_resubmit ? "Resubmit for review" : "Send question"}</button>
      </form>}
      {sendError && <p role="alert">{sendError}</p>}
      {confirmation && <p role="status">{confirmation}</p>}
      {emailNote && <p>{emailNote}</p>}
    </section>
  );
}
