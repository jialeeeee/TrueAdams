import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

const NOT_LOADED = "Review requests could not be loaded. Check your connection and try again.";
const NOT_RECORDED = "Not recorded";

export default function ReviewRequestsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/review-requests");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(typeof error === "string" && error.trim() ? error : NOT_LOADED);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>Requests for review</h1>
      {loadError ? (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      ) : !result ? (
        <p>Loading…</p>
      ) : result.requests.length === 0 ? (
        <p>{result.message}</p>
      ) : (
        <ul>
          {result.requests.map((request) => (
            <li key={request.id}>
              <Link to={`/events/${request.id}/review`}>{request.title || NOT_RECORDED}</Link>
              <p>{`Organiser: ${request.organiser?.email || NOT_RECORDED}`}</p>
              <p>{`Proposed date: ${request.start_time ? request.start_time.slice(0, 16).replace("T", " ") : NOT_RECORDED}`}</p>
              <p>{`Submitted: ${request.submitted_at ? formatSavedAt(request.submitted_at) : NOT_RECORDED}`}</p>
              <p>{`Status: ${statusLabel(request.status)}`}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
