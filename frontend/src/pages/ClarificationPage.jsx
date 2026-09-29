import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import apiClient from "../api/client.js";

// Must match MAX_CLARIFICATION_WORDS in backend/app/events/routes.py.
const MAX_WORDS = 1000;

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

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get(url);
      setThread(response.data);
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
      const response = await apiClient.post(url, { message: question.trim() });
      const { message, clarification, notification } = response.data;
      setConfirmation(message);
      if (notification && !notification.email_queued) {
        setEmailNote(
          "The email could not be sent, but the organiser will still see your question in ConnectSphere.",
        );
      }
      setThread((current) => ({
        ...current,
        clarifications: [...current.clarifications, clarification],
        message: null,
      }));
      setQuestion("");
    } catch (failure) {
      // The question stays in the box so it can be sent again.
      setSendError(
        serverError(failure, "Your question was not sent. Check your connection and try again."),
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

      <form onSubmit={handleSubmit}>
        <label htmlFor="clarification-question">Your question</label>
        <textarea
          id="clarification-question"
          rows={6}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <p>{`${words} / ${MAX_WORDS} words`}</p>
        {over > 0 && (
          <p>
            That is over the 1,000-word limit. Remove {over} word{over === 1 ? "" : "s"} to send.
          </p>
        )}
        {sendError && <p role="alert">{sendError}</p>}
        {confirmation && <p role="status">{confirmation}</p>}
        {emailNote && <p>{emailNote}</p>}
        <button type="submit" disabled={!canSend}>Send question</button>
      </form>
    </section>
  );
}
