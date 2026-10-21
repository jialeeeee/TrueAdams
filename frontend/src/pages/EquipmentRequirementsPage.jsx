import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import ARRANGEMENT_STATUSES from "../utils/arrangementStatuses.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-42: the event's coordinator records its equipment requirements, and Technical
// Support Staff update each one's arrangement status, via
// /api/events/<id>/equipment-requirements. Recording reserves nothing (AC5).
const NOT_LOADED = "The equipment requirements could not be loaded. Check your connection and try again.";
const NOT_SAVED =
  "The equipment requirement was not saved, and the recorded requirements are unchanged. Check your connection and try again.";
const NOT_REMOVED =
  "The equipment requirement was not removed, and the recorded requirements are unchanged. Check your connection and try again.";
const ARRANGEMENT_NOT_SAVED = "The arrangement status was not saved. Check your connection and try again.";

const EMPTY_FORM = { equipment_type: "", quantity: "", technical_requirements: "" };

const describe = (requirement) => `${requirement.quantity} × ${requirement.equipment_type}`;

function when(event) {
  if (!event.start_time || !event.end_time) return "When: Not recorded";
  return `When: ${singaporeTime(event.start_time)} to ${singaporeTime(event.end_time)}`;
}

function formFrom(requirement) {
  return {
    equipment_type: requirement.equipment_type,
    quantity: String(requirement.quantity),
    technical_requirements: requirement.technical_requirements ?? "",
  };
}

function RequirementForm({ form, fieldErrors, editing, saving, onChange, onSubmit, onCancel }) {
  const field = (name) => (e) => onChange({ ...form, [name]: e.target.value });
  const problem = (name) =>
    fieldErrors[name] && <p id={`${name}-error`}>{fieldErrors[name]}</p>;
  const describedBy = (name) => (fieldErrors[name] ? `${name}-error` : undefined);
  return (
    // noValidate: the server names every problem, so the browser does not block the save (AC2).
    <form onSubmit={onSubmit} noValidate>
      <h3>{editing ? "Edit requirement" : "Record a requirement"}</h3>
      <label htmlFor="equipment_type">Equipment type</label>
      <input id="equipment_type" value={form.equipment_type} onChange={field("equipment_type")}
             aria-describedby={describedBy("equipment_type")} />
      {problem("equipment_type")}
      <label htmlFor="quantity">Quantity</label>
      <input id="quantity" type="number" min="1" step="1" value={form.quantity}
             onChange={field("quantity")} aria-describedby={describedBy("quantity")} />
      {problem("quantity")}
      <label htmlFor="technical_requirements">Technical requirements (optional)</label>
      <textarea id="technical_requirements" value={form.technical_requirements}
                onChange={field("technical_requirements")}
                aria-describedby={describedBy("technical_requirements")} />
      {problem("technical_requirements")}
      <button type="submit" disabled={saving}>{editing ? "Save changes" : "Record requirement"}</button>
      {editing && <button type="button" onClick={onCancel}>Cancel</button>}
    </form>
  );
}

function ArrangementForm({ requirement, onSave }) {
  const [status, setStatus] = useState(requirement.status);
  const [note, setNote] = useState(requirement.arrangement_note ?? "");
  const name = describe(requirement);

  function submit(e) {
    e.preventDefault();
    onSave(requirement, { status, note });
  }

  return (
    <form onSubmit={submit}>
      <select aria-label={`Arrangement status for ${name}`} value={status}
              onChange={(e) => setStatus(e.target.value)}>
        {ARRANGEMENT_STATUSES.map(([value, label]) => (
          <option key={value} value={value}>{label}</option>
        ))}
      </select>
      <textarea aria-label={`Note for ${name}`} value={note} onChange={(e) => setNote(e.target.value)} />
      <button type="submit" aria-label={`Update ${name}`}>Update</button>
    </form>
  );
}

function Requirement({ requirement, page, onEdit, onRemove, onArrange }) {
  const name = describe(requirement);
  return (
    <li>
      <strong>{name}</strong>
      <p>{`Technical requirements: ${requirement.technical_requirements ?? "None recorded"}`}</p>
      <p>{`Status: ${requirement.status_label}`}</p>
      {requirement.arrangement_note && (
        <p>{`Note from Technical Support: ${requirement.arrangement_note}`}</p>
      )}
      {page.can_edit && (
        <>
          <button type="button" aria-label={`Edit ${name}`} onClick={() => onEdit(requirement)}>Edit</button>
          <button type="button" aria-label={`Remove ${name}`} onClick={() => onRemove(requirement)}>Remove</button>
        </>
      )}
      {page.can_update_arrangements && (
        // Keyed by what was saved, so the form shows the saved values after an update.
        <ArrangementForm key={`${requirement.status}:${requirement.arrangement_note ?? ""}`}
                         requirement={requirement} onSave={onArrange} />
      )}
    </li>
  );
}

function EventEquipment({ eventId }) {
  const url = `/events/${eventId}/equipment-requirements`;
  // Only the newest load or save may update the list, whatever order replies arrive in.
  const latest = useRef(0);
  const [page, setPage] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const load = useCallback(async () => {
    const attempt = ++latest.current;
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/equipment-requirements`);
      if (attempt === latest.current) setPage(response.data);
    } catch (error) {
      if (attempt === latest.current) {
        setLoadError({ message: explain(error, NOT_LOADED), retryable: canRetry(error) });
      }
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  function startChange() {
    setFailure("");
    setConfirmation("");
    setFieldErrors({});
  }

  function finished(response) {
    setConfirmation(response.data.confirmation);
    if (response.data.refresh_error) {
      // Saved, but the server couldn't send the updated list back: load it (AC7).
      load();
      return;
    }
    latest.current += 1; // Any load still on its way is older than this reply.
    setPage(response.data);
  }

  function resetForm() {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setFieldErrors({});
  }

  async function save(e) {
    e.preventDefault();
    startChange();
    setSaving(true);
    const body = {
      equipment_type: form.equipment_type,
      quantity: form.quantity.trim() === "" ? null : Number(form.quantity),
      technical_requirements: form.technical_requirements,
    };
    try {
      const response = editingId === null
        ? await apiClient.post(url, body)
        : await apiClient.put(`${url}/${editingId}`, body);
      finished(response);
      resetForm();
    } catch (error) {
      // What was entered stays, so it can be corrected and saved again (AC2, AC7).
      setFailure(explain(error, NOT_SAVED));
      setFieldErrors(error.response?.data?.fields ?? {});
    } finally {
      setSaving(false);
    }
  }

  function edit(requirement) {
    startChange();
    setEditingId(requirement.id);
    setForm(formFrom(requirement));
  }

  async function remove(requirement) {
    startChange();
    try {
      finished(await apiClient.delete(`${url}/${requirement.id}`));
      if (editingId === requirement.id) resetForm();
    } catch (error) {
      setFailure(explain(error, NOT_REMOVED));
    }
  }

  async function arrange(requirement, { status, note }) {
    startChange();
    try {
      finished(await apiClient.patch(`${url}/${requirement.id}/arrangement`, { status, note }));
    } catch (error) {
      setFailure(explain(error, ARRANGEMENT_NOT_SAVED));
    }
  }

  if (loadError) {
    return (
      <section>
        <h1>Equipment requirements</h1>
        {confirmation && <p role="status">{confirmation}</p>}
        <p role="alert">{loadError.message}</p>
        {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
      </section>
    );
  }

  if (!page) return <p>Loading…</p>;

  const { event } = page;
  return (
    <section>
      {page.can_update_arrangements
        ? <Link to="/equipment-requests">Back to equipment requests</Link>
        : <Link to={`/events/${event.id}/planning`}>Back to the event</Link>}
      <h1>Equipment requirements</h1>
      <h2>{event.title}</h2>
      <p>{`Status: ${statusLabel(event.status)}`}</p>
      <p>{when(event)}</p>
      {page.organiser_note && <p>{`From the organiser's request: ${page.organiser_note}`}</p>}
      {/* SCRUM-43: Technical Support check whether the requirements can be met. */}
      {page.can_update_arrangements && (
        <Link to={`/events/${event.id}/equipment-availability`}>Check availability</Link>
      )}
      {page.notice && <p>{page.notice}</p>}
      {confirmation && <p role="status">{confirmation}</p>}
      {failure && <p role="alert">{failure}</p>}

      {page.requirements.length > 0 ? (
        <ul aria-label="Recorded equipment requirements">
          {page.requirements.map((requirement) => (
            <Requirement key={requirement.id} requirement={requirement} page={page}
                         onEdit={edit} onRemove={remove} onArrange={arrange} />
          ))}
        </ul>
      ) : (
        <p>{page.message}</p>
      )}

      {page.can_edit && (
        <RequirementForm form={form} fieldErrors={fieldErrors} editing={editingId !== null}
                         saving={saving} onChange={setForm} onSubmit={save} onCancel={resetForm} />
      )}
    </section>
  );
}

export default function EquipmentRequirementsPage() {
  const { eventId } = useParams();
  // A fresh page for each event (as SCRUM-55's review page): nothing from the previous
  // event, and no reply to it, can show under this one (AC3).
  return <EventEquipment key={eventId} eventId={eventId} />;
}
