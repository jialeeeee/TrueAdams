import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";

// Fields of an event request, in display order. Names match the API (SCRUM-29).
const FIELDS = [
  { name: "title", label: "Event name", type: "text" },
  { name: "purpose", label: "Purpose", type: "textarea" },
  { name: "description", label: "Description", type: "textarea" },
  { name: "start_time", label: "Start", type: "datetime-local" },
  { name: "end_time", label: "End", type: "datetime-local" },
  { name: "expected_attendance", label: "Expected attendance", type: "number" },
  { name: "venue_requirements", label: "Venue requirements", type: "textarea" },
  { name: "accessibility_needs", label: "Accessibility needs", type: "textarea" },
  { name: "equipment_requirements", label: "Equipment requirements", type: "textarea" },
  { name: "registration_required", label: "Attendee registration needed", type: "yes-no" },
];
const LABELS = Object.fromEntries(FIELDS.map((f) => [f.name, f.label]));
const EMPTY_FORM = Object.fromEntries(FIELDS.map((f) => [f.name, ""]));

// Draft from the API -> form input values (all strings).
function toForm(draft) {
  const form = { ...EMPTY_FORM };
  for (const { name, type } of FIELDS) {
    const value = draft[name];
    if (value === null || value === undefined) continue;
    if (type === "datetime-local") form[name] = value.slice(0, 16);
    else if (type === "yes-no") form[name] = value ? "yes" : "no";
    else form[name] = String(value);
  }
  return form;
}

// Form input values -> request body. Empty inputs are sent as null (not filled in).
function toBody(form) {
  const body = {};
  for (const { name, type } of FIELDS) {
    const value = form[name];
    if (value === "") body[name] = null;
    else if (type === "yes-no") body[name] = value === "yes";
    // Anything but digits is sent as typed, so the server can explain what is wrong.
    else if (type === "number") body[name] = /^\d+$/.test(value) ? Number(value) : value;
    else body[name] = value;
  }
  return body;
}

function explain(failure, fallback) {
  const error = failure.response?.data?.error;
  return typeof error === "string" && error.trim() ? error : fallback;
}

export default function DraftEventPage() {
  const { draftId } = useParams();
  const navigate = useNavigate();
  // The draft id already in state, so the URL change after a first save does not reload it.
  const loadedId = useRef(null);

  const [draft, setDraft] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(Boolean(draftId));
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const show = (saved) => {
    loadedId.current = saved.id;
    setDraft(saved);
    setForm(toForm(saved));
  };

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const response = await apiClient.get(`/events/drafts/${draftId}`);
      show(response.data);
    } catch (failure) {
      setLoadError(explain(failure, "This draft could not be loaded. Please try again."));
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => {
    if (draftId && Number(draftId) !== loadedId.current) load();
  }, [draftId, load]);

  // Saves the current edits: creates the draft on its first save, updates it after.
  const persist = async () => {
    const body = toBody(form);
    const response = draft
      ? await apiClient.put(`/events/drafts/${draft.id}`, body)
      : await apiClient.post("/events/drafts", body);
    const saved = response.data;
    const created = !draft;
    show(saved);
    if (created) navigate(`/events/drafts/${saved.id}`, { replace: true });
    return saved;
  };

  const start = () => {
    setBusy(true);
    setError("");
    setNotice("");
  };

  const handleSave = async () => {
    start();
    try {
      await persist();
      setNotice("Draft saved.");
    } catch (failure) {
      // The edits stay in the form, and the last-saved time is unchanged.
      setError(explain(failure, "Your draft was not saved. Check your connection and try again."));
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async () => {
    start();
    try {
      let saved;
      try {
        saved = await persist();
      } catch (failure) {
        setError(explain(failure, "Your draft was not saved. Check your connection and try again."));
        return;
      }
      try {
        const response = await apiClient.post(`/events/drafts/${saved.id}/submit`);
        show(response.data);
        setNotice("Your request has been submitted for review.");
      } catch (failure) {
        const missing = failure.response?.data?.missing;
        setError(
          Array.isArray(missing) && missing.length
            ? `Complete these fields before submitting: ${missing.map((m) => LABELS[m] ?? m).join(", ")}.`
            : explain(failure, "Your request was not submitted. Check your connection and try again."),
        );
      }
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p>Loading…</p>;

  if (loadError) {
    return (
      <section>
        <p role="alert">{loadError}</p>
        <button type="button" onClick={load}>Retry</button>
      </section>
    );
  }

  const submitted = draft?.status === "submitted";
  const set = (name) => (e) => setForm((current) => ({ ...current, [name]: e.target.value }));

  return (
    <section>
      <h1>{draft ? `Event request: ${draft.title}` : "New event request"}</h1>
      <p>{submitted ? "Status: Submitted" : "Status: Draft"}</p>
      <p>{draft?.last_saved_at ? `Last saved: ${formatSavedAt(draft.last_saved_at)}` : "Not saved yet"}</p>

      <form onSubmit={(e) => e.preventDefault()}>
        {FIELDS.map(({ name, label, type }) => {
          const id = `draft-${name}`;
          const common = { id, value: form[name], onChange: set(name), disabled: submitted };
          return (
            <div key={name}>
              <label htmlFor={id}>{label}</label>
              {type === "textarea" && <textarea rows={3} {...common} />}
              {type === "yes-no" && (
                <select {...common}>
                  <option value="">Not decided yet</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              )}
              {!["textarea", "yes-no"].includes(type) && (
                <input type={type} min={type === "number" ? 1 : undefined} {...common} />
              )}
            </div>
          );
        })}

        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}

        {!submitted && (
          <>
            <button type="button" onClick={handleSave} disabled={busy || !form.title.trim()}>
              Save draft
            </button>
            <button type="button" onClick={handleSubmit} disabled={busy || !form.title.trim()}>
              Submit for review
            </button>
          </>
        )}
      </form>
    </section>
  );
}
