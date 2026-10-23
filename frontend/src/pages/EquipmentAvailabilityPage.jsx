import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";

// SCRUM-43: Technical Support Staff check whether an event's equipment requirements can be
// met from the equipment available over its period, via
// GET /api/events/<id>/equipment-availability. Read-only: it reserves nothing (AC4).
const NOT_CHECKED = "The equipment availability check could not be completed. Check your connection and try again.";

// SCRUM-44: what other overlapping events have reserved is not available (AC4).
const countedItem = (item) => (item.reserved_for_other_events
  ? `${item.name} (${item.available_quantity} of ${item.quantity_available}; ${item.reserved_for_other_events} reserved for other events at this time)`
  : `${item.name} (${item.available_quantity})`);

const counted = (line) => line.suitable.map(countedItem).join(", ");

function Line({ line }) {
  return (
    <li>
      <strong>{`${line.requested_quantity} × ${line.equipment_type}`}</strong>
      <p>{`Requested: ${line.requested_quantity} · Available: ${line.available_quantity}`}</p>
      <p>{line.result_label}</p>
      {/* Review of PR #48: requirements for the same equipment share its stock. */}
      {line.shared_note && <p>{line.shared_note}</p>}
      {line.technical_note && <p>{line.technical_note}</p>}
      {line.suitable.length > 0 && <p>{`Counted: ${counted(line)}`}</p>}
      {line.excluded.map((item) => (
        <p key={item.id}>{`Not counted: ${item.name} (${item.detail})`}</p>
      ))}
    </li>
  );
}

function EventAvailability({ eventId }) {
  const [result, setResult] = useState(null);
  const [failure, setFailure] = useState(null);

  const load = useCallback(async () => {
    setFailure(null);
    setResult(null);
    try {
      const response = await apiClient.get(`/events/${eventId}/equipment-availability`);
      setResult(response.data);
    } catch (error) {
      // A failed check is never shown as a result (AC5).
      setFailure({ message: explain(error, NOT_CHECKED), retryable: canRetry(error) });
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <Link to={`/events/${eventId}/equipment`}>Back to the equipment requirements</Link>
      <h1>Equipment availability</h1>
      {failure && (
        <>
          <p role="alert">{failure.message}</p>
          {failure.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      )}
      {!failure && !result && <p>Checking…</p>}
      {result && (
        <>
          <h2>{result.event.title}</h2>
          <p>{`For: ${singaporeTime(result.event.start_time)} to ${singaporeTime(result.event.end_time)}`}</p>
          <p>{result.notice}</p>
          <Link to={`/events/${eventId}/equipment-reservations`}>Reserve equipment</Link>
          {result.checks.length > 0 ? (
            <>
              <p>{result.summary}</p>
              <ul aria-label="Availability by requirement">
                {result.checks.map((line) => <Line key={line.requirement_id} line={line} />)}
              </ul>
              <button type="button" onClick={load}>Check again</button>
            </>
          ) : (
            <p>{result.message}</p>
          )}
        </>
      )}
    </section>
  );
}

export default function EquipmentAvailabilityPage() {
  const { eventId } = useParams();
  // A fresh page for each event, as the equipment requirements page (review of PR #47):
  // a result for the previous event can never show under this one.
  return <EventAvailability key={eventId} eventId={eventId} />;
}
