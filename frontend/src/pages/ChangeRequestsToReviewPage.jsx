import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// SCRUM-70 A10: the pending change requests of the events the coordinator coordinates,
// oldest first, from GET /api/events/change-requests.
const NOT_LOADED = "Change requests could not be loaded. Check your connection and try again.";

const joinWords = (words) =>
  (words.length === 1 ? words[0] : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`);

export default function ChangeRequestsToReviewPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const response = await apiClient.get("/events/change-requests");
      setResult(response.data);
    } catch (failure) {
      setLoadError({ message: explain(failure, NOT_LOADED), retryable: canRetry(failure) });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Change requests to review</h1>
      {loadError ? (
        <>
          <p role="alert">{loadError.message}</p>
          {loadError.retryable && <button type="button" onClick={load}>Retry</button>}
        </>
      ) : !result ? (
        <p>Loading…</p>
      ) : result.requests.length === 0 ? (
        <p>{result.message}</p>
      ) : (
        <ul>
          {result.requests.map((request) => (
            <li key={request.id}>
              <Link to={`/events/${request.event.id}/change-requests/${request.id}`}>{request.event.title}</Link>
              <p>{`Requested by ${request.requested_by?.email ?? "not recorded"} on ${formatSavedAt(request.requested_at)}`}</p>
              <p>{`Changes: ${joinWords(request.changes.map((change) => change.label))}`}</p>
              <p>{`Event status: ${statusLabel(request.event.status)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
