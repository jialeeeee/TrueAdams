import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";

// SCRUM-88: Venue Staff record a period when a venue is unavailable, even when it already has
// confirmed bookings (/venues/:venueId/unavailable). POST /api/venues/<id>/unavailable flags the
// overlapping confirmed bookings and tells their coordinators; the screen shows the server's
// words. Only Venue Staff may use it: for anyone else the server refuses the list (403) and no
// form is shown (AC6).
const NOT_LOADED = "The unavailable periods could not be loaded. Check your connection and try again.";
const NOT_SAVED = "The unavailable period was not saved. Your entries are still here; please try again.";
const EMPTY = { reason: "", start_time: "", end_time: "" };

// Times are Singapore time without a time zone: show them as recorded.
const asText = (value) => value.slice(0, 16).replace("T", " ");

function missingFields(form) {
  const problems = {};
  if (!form.reason.trim()) problems.reason = "Enter the reason.";
  if (!form.start_time) problems.start_time = "Enter the start date and time.";
  if (!form.end_time) problems.end_time = "Enter the end date and time.";
  if (form.start_time && form.end_time && form.end_time <= form.start_time) {
    problems.end_time = "The end must be after the start.";
  }
  return problems;
}

export default function VenueUnavailablePage() {
  const { venueId } = useParams();
  const [venue, setVenue] = useState(null);
  const [periods, setPeriods] = useState(null);
  const [denied, setDenied] = useState("");
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);

  const loadPeriods = useCallback(async () => {
    const response = await apiClient.get(`/venues/${venueId}/unavailable`);
    setPeriods(response.data);
  }, [venueId]);

  const load = useCallback(async () => {
    setLoadError(null);
    setDenied("");
    try {
      await loadPeriods();
    } catch (failure) {
      if (failure.response?.status === 403) {
        setDenied(explain(failure, "Only Venue Staff can record unavailable periods."));
      } else {
        setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
      }
      return;
    }
    try {
      setVenue((await apiClient.get(`/venues/${venueId}`)).data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, [loadPeriods, venueId]);

  useEffect(() => {
    load();
  }, [load]);

  const change = (field) => (e) => setForm((current) => ({ ...current, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setConfirmation("");
    setFormError("");
    const missing = missingFields(form);
    setFieldErrors(missing);
    if (Object.keys(missing).length) return;

    setSaving(true);
    try {
      const response = await apiClient.post(`/venues/${venueId}/unavailable`, {
        reason: form.reason.trim(),
        start_time: form.start_time,
        end_time: form.end_time,
      });
      setConfirmation(response.data.message);
      setForm(EMPTY);
      try {
        await loadPeriods();
      } catch {
        // The period is saved; the list refreshes the next time the page loads.
      }
    } catch (failure) {
      // The entered details stay in the form so the period can be saved again.
      setFieldErrors(failure.response?.data?.fields ?? {});
      setFormError(failure.response?.data?.fields ? "" : explain(failure, NOT_SAVED));
    } finally {
      setSaving(false);
    }
  };

  if (denied) {
    return (
      <section>
        <h1>Unavailable periods</h1>
        <p role="alert">{denied}</p>
      </section>
    );
  }

  return (
    <section>
      <h1>{`Unavailable periods${venue ? `: ${venue.name}` : ""}`}</h1>
      <Link to="/venues">Back to venues</Link>

      {loadError && (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}

      {periods && periods.periods.length === 0 && <p>{periods.message}</p>}
      {periods && periods.periods.length > 0 && (
        <ul aria-label="Unavailable periods">
          {periods.periods.map((period) => (
            <li key={period.id}>{`${period.reason}: ${asText(period.start_time)} to ${asText(period.end_time)}`}</li>
          ))}
        </ul>
      )}

      {periods && (
        <form onSubmit={handleSubmit} noValidate>
          <h2>Record unavailable period</h2>
          {confirmation && <p role="status">{confirmation}</p>}
          {formError && <p role="alert">{formError}</p>}

          <label htmlFor="unavailable-reason">Reason</label>
          <input id="unavailable-reason" type="text" value={form.reason} onChange={change("reason")} />
          {fieldErrors.reason && <span role="alert">{fieldErrors.reason}</span>}

          <label htmlFor="unavailable-start">Start</label>
          <input id="unavailable-start" type="datetime-local" value={form.start_time}
            onChange={change("start_time")} />
          {fieldErrors.start_time && <span role="alert">{fieldErrors.start_time}</span>}

          <label htmlFor="unavailable-end">End</label>
          <input id="unavailable-end" type="datetime-local" value={form.end_time}
            onChange={change("end_time")} />
          {fieldErrors.end_time && <span role="alert">{fieldErrors.end_time}</span>}

          <button type="submit" disabled={saving}>Save</button>
        </form>
      )}
    </section>
  );
}
