import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";

// SCRUM-46: an organiser asks for changes to their approved event, via GET and POST
// /api/events/<id>/change-requests. The event itself is not changed: the request waits,
// Pending Review, for the event's coordinator (AC6, AC7).
const NOT_LOADED = "The change request form could not be loaded. Check your connection and try again.";
const NOT_SUBMITTED = "Your change request was not submitted. Check your connection and try again.";
const NOTHING_CHANGED = "Change at least one value before submitting a change request.";
const TIME_FIELDS = new Set(["start_time", "end_time"]);
const TEXT_FIELDS = new Set(["venue_requirements", "equipment_requirements"]);
const RECORDED_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

// What an input shows for a value. Times are Singapore time, shown as recorded.
function inputValue(name, value) {
  if (value === null || value === undefined) return "";
  return TIME_FIELDS.has(name) ? value.slice(0, 16) : String(value);
}

function shown(value) {
  if (value === null || value === undefined) return "none";
  if (typeof value === "string" && RECORDED_TIME.test(value)) return value.slice(0, 16).replace("T", " ");
  return String(value);
}

// Attendance is sent as a number; the server says if it isn't a valid one (AC4).
function outgoing(name, text) {
  if (name !== "expected_attendance") return text;
  return text.trim() === "" ? null : Number(text);
}

function RequestedChanges({ request }) {
  return (
    <>
      <p>{`Status: ${request.status_label}`}</p>
      <ul aria-label="Requested changes">
        {request.changes.map((change) => (
          <li key={change.field}>{`${change.label}: ${shown(change.from)} → ${shown(change.to)}`}</li>
        ))}
      </ul>
    </>
  );
}

function Field({ field, value, problem, onChange }) {
  const id = `change-${field.name}`;
  const props = { id, value, onChange: (e) => onChange(field.name, e.target.value) };
  let input;
  if (TIME_FIELDS.has(field.name)) input = <input type="datetime-local" {...props} />;
  else if (TEXT_FIELDS.has(field.name)) input = <textarea {...props} />;
  else input = <input type="number" min="1" {...props} />;
  return (
    <p>
      <label htmlFor={id}>{field.label}</label>
      {input}
      {problem && <span>{problem}</span>}
    </p>
  );
}

function EventChangeRequest({ eventId }) {
  const [form, setForm] = useState(null);
  const [loadError, setLoadError] = useState(null);
  // The values typed, kept after a refusal or a failed save (AC4, AC8).
  const [values, setValues] = useState({});
  const [failure, setFailure] = useState("");
  const [problems, setProblems] = useState({});
  const [sending, setSending] = useState(false);
  const [submitted, setSubmitted] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/change-requests`);
      const { current } = response.data.event;
      setValues(Object.fromEntries(response.data.fields.map(({ name }) => [name, inputValue(name, current[name])])));
      setForm(response.data);
    } catch (error) {
      // A failed load is never shown as an empty form.
      setLoadError({ message: explain(error, NOT_LOADED), retryable: canRetry(error) });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const change = (name, value) => setValues((all) => ({ ...all, [name]: value }));

  async function submit(e) {
    e.preventDefault();
    if (sending) return;
    const { current } = form.event;
    // Only what was changed is sent; the server ignores anything unchanged too (A3).
    const proposal = Object.fromEntries(
      form.fields
        .filter(({ name }) => values[name] !== inputValue(name, current[name]))
        .map(({ name }) => [name, outgoing(name, values[name])]),
    );
    setProblems({});
    if (Object.keys(proposal).length === 0) {
      setFailure(NOTHING_CHANGED);
      return;
    }
    setFailure("");
    setSending(true);
    try {
      const response = await apiClient.post(`/events/${eventId}/change-requests`, proposal);
      setSubmitted(response.data);
    } catch (error) {
      setFailure(explain(error, NOT_SUBMITTED));
      setProblems(error.response?.data?.fields ?? {});
    } finally {
      setSending(false);
    }
  }

  if (!form) {
    return (
      <section>
        <h1>Request a change</h1>
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

  const { event } = form;
  const pending = submitted?.request ?? form.pending_request;
  return (
    <section>
      <Link to="/events/mine">Back to my event requests</Link>
      <h1>Request a change</h1>
      <h2>{event.title}</h2>
      {event.coordinator && <p>{`Coordinator: ${event.coordinator.email}`}</p>}
      {submitted && <p role="status">{submitted.message}</p>}
      {!submitted && form.message && <p>{form.message}</p>}
      {pending && <RequestedChanges request={pending} />}

      {!submitted && form.can_request && (
        // noValidate: the server checks every value and says what is wrong (AC4).
        <form aria-label="Change request" noValidate onSubmit={submit}>
          <p>The approved event stays as it is until the coordinator reviews your request.</p>
          {form.fields.map((field) => (
            <Field key={field.name} field={field} value={values[field.name] ?? ""}
                   problem={problems[field.name]} onChange={change} />
          ))}
          {failure && <p role="alert">{failure}</p>}
          <button type="submit" className="btn-primary" disabled={sending}>Submit change request</button>
        </form>
      )}
    </section>
  );
}

export default function ChangeRequestPage() {
  const { eventId } = useParams();
  // A fresh page for each event, as the equipment pages: a reply for the previous event
  // can never show under this one.
  return <EventChangeRequest key={eventId} eventId={eventId} />;
}
