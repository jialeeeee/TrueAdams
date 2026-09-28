import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// The organiser's submitted, approved and rejected requests (SCRUM-32).
export default function MyRequestsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/requests");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(
        typeof error === "string" && error.trim()
          ? error
          : "Your event requests could not be loaded. Check your connection and try again.",
      );
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>My event requests</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}

      {result && result.requests.length === 0 && <p>{result.message}</p>}
      {result && result.requests.length > 0 && (
        <ul>
          {result.requests.map((request) => (
            <li key={request.id}>
              <strong>{request.title}</strong>
              <p>
                {request.decided_at
                  ? `Status: ${statusLabel(request.status)} · decided ${formatSavedAt(request.decided_at)}`
                  : `Status: ${statusLabel(request.status)}`}
              </p>
              {request.decision_note && (
                <p>{`${request.status === "rejected" ? "Reason" : "Note"}: ${request.decision_note}`}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
