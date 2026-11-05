import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";

// SCRUM-63: add a venue (/venues/new) or edit one (/venues/:venueId/edit).
// POST /api/venues/ and PUT /api/venues/<id>; the server validates and names every
// invalid field (400 {"fields": {...}}), and the form keeps what was typed (AC5, AC6).
const NOT_SAVED = "The venue could not be saved. Your entries are still here; please try again.";
const NOT_LOADED = "The venue could not be loaded. Check your connection and try again.";
const LIST_FIELDS = [
  ["facilities", "Facilities"],
  ["accessibility_features", "Accessibility features"],
  ["room_layouts", "Layouts"],
];
const EMPTY = {
  name: "", location: "", capacity: "", facilities: [], accessibility_features: [],
  room_layouts: [], operating_hours: "",
  // SCRUM-63 AC9: whole minutes, 0 to 1440; empty means none set (the server uses 0).
  setup_minutes: "", turnaround_minutes: "",
};
const label = (option) => option.charAt(0).toUpperCase() + option.slice(1);
// SCRUM-63 AC7 and CF08: what each change history action is called.
// SCRUM-101: users see "delete", the customer's word (G4 #15); the code keeps "archive".
const ACTIONS = { added: "Added", archived: "Deleted", restored: "Restored" };
const NOT_ARCHIVED = "The venue was not deleted. Check your connection and try again.";
const NOT_RESTORED = "The venue was not restored. Check your connection and try again.";

export default function VenueFormPage() {
  const { venueId } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [options, setOptions] = useState(null);
  const [history, setHistory] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  // CF08: when the venue was archived (null while in use), and the archive step.
  const [archivedAt, setArchivedAt] = useState(null);
  const [confirmingArchive, setConfirmingArchive] = useState(false);

  const load = async () => {
    setLoadError(null);
    try {
      setOptions((await apiClient.get("/venues/options")).data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
      return;
    }
    if (!venueId) return;
    try {
      const venue = (await apiClient.get(`/venues/${venueId}`)).data;
      setForm({
        name: venue.name ?? "", location: venue.location ?? "", capacity: String(venue.capacity ?? ""),
        facilities: venue.facilities ?? [], accessibility_features: venue.accessibility_features ?? [],
        room_layouts: venue.room_layouts ?? [], operating_hours: venue.operating_hours ?? "",
        setup_minutes: String(venue.setup_minutes ?? ""),
        turnaround_minutes: String(venue.turnaround_minutes ?? ""),
      });
      setArchivedAt(venue.archived_at ?? null);
      setHistory((await apiClient.get(`/venues/${venueId}/history`)).data.history);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [venueId]);

  const toggle = (field, option) => setForm((current) => ({
    ...current,
    [field]: current[field].includes(option)
      ? current[field].filter((item) => item !== option)
      : [...current[field], option],
  }));

  const save = async (event) => {
    event.preventDefault();
    setFieldErrors({});
    setFormError("");
    setConfirmation("");
    setSaving(true);
    try {
      const response = venueId
        ? await apiClient.put(`/venues/${venueId}`, form)
        : await apiClient.post("/venues/", form);
      setConfirmation(response.data.message);
      if (!venueId) navigate(`/venues/${response.data.venue.id}/edit`);
      else setHistory((await apiClient.get(`/venues/${venueId}/history`)).data.history);
    } catch (failure) {
      const fields = failure.response?.data?.fields;
      if (failure.response?.status === 400 && fields) setFieldErrors(fields);
      else setFormError(explain(failure, NOT_SAVED));
    } finally {
      setSaving(false);
    }
  };

  // CF08: archive (delete) or restore the venue; the server refuses while it has bookings
  // still to come, and says why.
  const archiveOrRestore = async (action) => {
    setFormError("");
    setConfirmation("");
    setSaving(true);
    try {
      const response = await apiClient.post(`/venues/${venueId}/${action}`, {});
      setArchivedAt(response.data.venue.archived_at ?? null);
      setConfirmation(response.data.message);
      setHistory((await apiClient.get(`/venues/${venueId}/history`)).data.history);
    } catch (failure) {
      setFormError(explain(failure, action === "archive" ? NOT_ARCHIVED : NOT_RESTORED));
    } finally {
      setConfirmingArchive(false);
      setSaving(false);
    }
  };

  if (loadError) {
    return (
      <section>
        <h1>{venueId ? "Edit venue" : "Add venue"}</h1>
        <p role="alert">{loadError.message}</p>
        {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
      </section>
    );
  }
  if (!options) return <section><h1>{venueId ? "Edit venue" : "Add venue"}</h1></section>;

  const text = (field, text, extra = {}) => (
    <p>
      <label htmlFor={field}>{text}</label>
      <input
        id={field}
        value={form[field]}
        aria-invalid={fieldErrors[field] ? "true" : undefined}
        aria-describedby={fieldErrors[field] ? `${field}-error` : undefined}
        onChange={(e) => setForm((current) => ({ ...current, [field]: e.target.value }))}
        {...extra}
      />
      {fieldErrors[field] && <span id={`${field}-error`} role="alert">{fieldErrors[field]}</span>}
    </p>
  );

  return (
    <section>
      <h1>{venueId ? "Edit venue" : "Add venue"}</h1>
      {confirmation && <p role="status">{confirmation}</p>}
      {formError && <p role="alert">{formError}</p>}
      <form onSubmit={save} noValidate>
        {text("name", "Name")}
        {text("location", "Location")}
        {text("capacity", "Capacity", { inputMode: "numeric" })}
        {LIST_FIELDS.map(([field, heading]) => (
          <fieldset key={field} aria-invalid={fieldErrors[field] ? "true" : undefined}>
            <legend>{heading}</legend>
            {options[field].map((option) => (
              <label key={option}>
                <input
                  type="checkbox"
                  checked={form[field].includes(option)}
                  onChange={() => toggle(field, option)}
                />
                {label(option)}
              </label>
            ))}
            {fieldErrors[field] && <span role="alert">{fieldErrors[field]}</span>}
          </fieldset>
        ))}
        {text("operating_hours", "Operating hours", { placeholder: "Mon-Fri 08:00-22:00" })}
        {text("setup_minutes", "Setup time (minutes)", { inputMode: "numeric" })}
        {text("turnaround_minutes", "Turnaround time (minutes)", { inputMode: "numeric" })}
        {!archivedAt && <button type="submit" disabled={saving}>Save</button>}
      </form>

      {venueId && archivedAt && (
        <section aria-label="Deleted venue">
          <p>{`Deleted on ${formatSavedAt(archivedAt)}. It isn't offered for new bookings, and its records are kept. Restore it to edit it.`}</p>
          <button type="button" onClick={() => archiveOrRestore("restore")} disabled={saving}>Restore venue</button>
        </section>
      )}
      {venueId && !archivedAt && !confirmingArchive && (
        <button type="button" onClick={() => setConfirmingArchive(true)}>Delete venue</button>
      )}
      {venueId && !archivedAt && confirmingArchive && (
        <section aria-label="Delete this venue">
          <p>
            Deleting removes the venue from the catalogue, venue search and new bookings. Its
            bookings and history are kept, and it can be restored.
          </p>
          <button type="button" onClick={() => archiveOrRestore("archive")} disabled={saving}>Delete</button>
          <button type="button" onClick={() => setConfirmingArchive(false)} disabled={saving}>Back</button>
        </section>
      )}

      {venueId && (
        <>
          <h2>Change history</h2>
          <ul>
            {history.map((entry, index) => (
              <li key={index}>
                {`${ACTIONS[entry.action] ?? "Edited"} by ${entry.changed_by.email} on ${formatSavedAt(entry.changed_at)}`}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
