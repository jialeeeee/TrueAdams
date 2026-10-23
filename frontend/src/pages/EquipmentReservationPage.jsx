import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";

// SCRUM-44: Technical Support Staff reserve equipment for an event's requirements, via
// GET and POST /api/events/<id>/equipment-reservations. The event's coordinator sees the
// same page without the forms. The page shows availability when it was loaded; the server
// checks it again when reserving (AC2), so its refusals are shown as they come.
const NOT_LOADED = "The equipment reservations could not be loaded. Check your connection and try again.";
const NOT_RESERVED = "The equipment was not reserved. Check your connection and try again.";

const describe = (quantity, name) => `${quantity} × ${name}`;

function availabilityText(option) {
  const text = `${option.name}: ${option.available_to_reserve} available to reserve`;
  const held = [];
  if (option.reserved_for_other_events) held.push(`${option.reserved_for_other_events} reserved for other events at this time`);
  if (option.reserved_for_this_event) held.push(`${option.reserved_for_this_event} already reserved for this event`);
  return held.length ? `${text} (${option.quantity_available} recorded, ${held.join(", ")})` : text;
}

function ReserveForm({ requirement, quantities, onChange, onReserve, busy }) {
  const name = describe(requirement.quantity, requirement.equipment_type);
  return (
    // noValidate: the server checks availability again and says how many are available
    // (AC2, AC5); the browser must not block the request with its own message first.
    <form aria-label={`Reserve for ${name}`} noValidate
          onSubmit={(e) => { e.preventDefault(); onReserve(); }}>
      {requirement.options.map((option) => (
        <p key={option.id}>
          <label>
            {`Quantity of ${option.name}`}
            <input type="number" min="0" max={option.available_to_reserve}
                   value={quantities[option.id] ?? ""}
                   onChange={(e) => onChange(option.id, e.target.value)} />
          </label>
        </p>
      ))}
      <button type="submit" disabled={busy}>{`Reserve for ${name}`}</button>
    </form>
  );
}

function Requirement({ requirement, canReserve, quantities, failure, busy, onChange, onReserve }) {
  const reservable = canReserve && requirement.state === "can_reserve";
  return (
    <li>
      <strong>{describe(requirement.quantity, requirement.equipment_type)}</strong>
      {requirement.technical_note && <p>{requirement.technical_note}</p>}
      <p>{`Reserved: ${requirement.reserved_quantity} of ${requirement.quantity}`}</p>
      <p>{requirement.state_label}</p>
      {requirement.reservations.length > 0 && (
        <ul aria-label={`Reserved for ${describe(requirement.quantity, requirement.equipment_type)}`}>
          {requirement.reservations.map((reservation) => (
            <li key={reservation.id}>
              {`${describe(reservation.quantity, reservation.resource.name)} reserved by ${reservation.reserved_by?.email ?? "Technical Support"}`}
            </li>
          ))}
        </ul>
      )}
      {requirement.options.map((option) => <p key={option.id}>{availabilityText(option)}</p>)}
      {requirement.excluded.map((item) => (
        <p key={item.id}>{`Not available: ${item.name} (${item.detail})`}</p>
      ))}
      {failure && <p role="alert">{failure}</p>}
      {reservable && (
        <ReserveForm requirement={requirement} quantities={quantities} busy={busy}
                     onChange={onChange} onReserve={onReserve} />
      )}
    </li>
  );
}

function EventReservations({ eventId }) {
  const [page, setPage] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  // The quantities typed and the last refusal, per requirement, kept after a failure (AC7).
  const [quantities, setQuantities] = useState({});
  const [failures, setFailures] = useState({});
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/equipment-reservations`);
      setPage(response.data);
    } catch (error) {
      // A failed load is never shown as an empty page.
      setLoadError({ message: explain(error, NOT_LOADED), retryable: canRetry(error) });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  const change = (requirementId, optionId, value) =>
    setQuantities((all) => ({ ...all, [requirementId]: { ...all[requirementId], [optionId]: value } }));

  const reserve = async (requirement) => {
    const chosen = quantities[requirement.id] ?? {};
    const items = requirement.options
      .filter((option) => (chosen[option.id] ?? "").trim() !== "" && Number(chosen[option.id]) !== 0)
      .map((option) => ({ resource_id: option.id, quantity: Number(chosen[option.id]) }));
    setBusy(requirement.id);
    setConfirmation(null);
    setFailures((all) => ({ ...all, [requirement.id]: null }));
    try {
      const response = await apiClient.post(`/events/${eventId}/equipment-reservations`, {
        requirement_id: requirement.id, items,
      });
      setConfirmation(response.data.confirmation);
      setQuantities((all) => ({ ...all, [requirement.id]: {} }));
      // Saved, but the page couldn't be sent back: load it rather than show the old one.
      if (response.data.refresh_error) await load();
      else setPage(response.data);
    } catch (error) {
      setFailures((all) => ({ ...all, [requirement.id]: explain(error, NOT_RESERVED) }));
    } finally {
      setBusy(null);
    }
  };

  if (!page) {
    return (
      <section>
        <h1>Equipment reservations</h1>
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

  const { event, reservation_period: period } = page;
  return (
    <section>
      <Link to={`/events/${event.id}/equipment`}>Back to the equipment requirements</Link>
      <h1>Equipment reservations</h1>
      <h2>{event.title}</h2>
      {period && (
        <p>{`Reservation period: ${singaporeTime(period.start_time)} to ${singaporeTime(period.end_time)}`}</p>
      )}
      {page.notice && <p>{page.notice}</p>}
      {confirmation && <p role="status">{confirmation}</p>}
      {page.requirements.length > 0 ? (
        <ul aria-label="Equipment requirements">
          {page.requirements.map((requirement) => (
            <Requirement key={requirement.id} requirement={requirement} canReserve={page.can_reserve}
                         quantities={quantities[requirement.id] ?? {}}
                         failure={failures[requirement.id]} busy={busy === requirement.id}
                         onChange={(optionId, value) => change(requirement.id, optionId, value)}
                         onReserve={() => reserve(requirement)} />
          ))}
        </ul>
      ) : (
        <p>{page.message}</p>
      )}
      {page.released.length > 0 && (
        <>
          <h2>Released reservations</h2>
          <ul aria-label="Released reservations">
            {page.released.map((reservation) => (
              <li key={reservation.id}>
                {`${describe(reservation.quantity, reservation.resource.name)} released: ${reservation.release_reason}`}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default function EquipmentReservationPage() {
  const { eventId } = useParams();
  // A fresh page for each event, as the other equipment pages (review of PR #47): a page
  // or a reply for the previous event can never show under this one.
  return <EventReservations key={eventId} eventId={eventId} />;
}
