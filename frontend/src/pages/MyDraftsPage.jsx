import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import formatSavedAt from "../utils/formatSavedAt.js";

export default function MyDraftsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/drafts");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(
        typeof error === "string" && error.trim()
          ? error
          : "Your drafts could not be loaded. Check your connection and try again.",
      );
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section>
      <h1>My draft event requests</h1>
      <Link to="/events/drafts/new">New event request</Link>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}

      {result && result.drafts.length === 0 && <p>{result.message}</p>}
      {result && result.drafts.length > 0 && (
        <ul>
          {result.drafts.map((draft) => (
            <li key={draft.id}>
              <Link to={`/events/drafts/${draft.id}`}>{draft.title}</Link>{" "}
              <span>{`Draft · last saved ${formatSavedAt(draft.last_saved_at)}`}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
