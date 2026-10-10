import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import apiClient from "../api/client.js";
import decidedBy from "../utils/decidedBy.js";
import formatSavedAt from "../utils/formatSavedAt.js";
import statusLabel from "../utils/statusLabel.js";

// The organiser's drafts and submitted requests, in separate sections (SCRUM-59).
const NOT_LOADED = "Your event requests could not be loaded. Check your connection and try again.";

function draftName(title) {
  return typeof title === "string" && title.trim() ? title : "Untitled draft";
}

function DraftsSection({ drafts }) {
  return (
    <section aria-labelledby="drafts-heading">
      <h2 id="drafts-heading">Drafts</h2>
      {drafts.length === 0 ? (
        <p>No drafts.</p>
      ) : (
        <ul>
          {drafts.map((draft) => (
            <li key={draft.id}>
              <Link to={`/events/drafts/${draft.id}`}>{draftName(draft.title)}</Link>{" "}
              <span>{`Draft · last saved ${formatSavedAt(draft.last_saved_at)}`}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SubmittedSection({ requests }) {
  return (
    <section aria-labelledby="submitted-heading">
      <h2 id="submitted-heading">Submitted requests</h2>
      {requests.length === 0 ? (
        <p>No submitted requests.</p>
      ) : (
        <ul>
          {/* No link to the draft editor: submitted requests can no longer be edited. */}
          {requests.map((request) => (
            <li key={request.id}>
              <strong>{request.title}</strong>
              <p>
                {request.decided_at
                  ? `Status: ${statusLabel(request.status)} · decided ${formatSavedAt(request.decided_at)}`
                  : `Status: ${statusLabel(request.status)}`}
              </p>
              {request.decided_at && <p>{decidedBy(request)}</p>}
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

export default function MyEventRequestsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/events/mine");
      setResult(response.data);
    } catch (failure) {
      const error = failure.response?.data?.error;
      setLoadError(typeof error === "string" && error.trim() ? error : NOT_LOADED);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const empty = result && result.drafts.length === 0 && result.submitted.length === 0;

  return (
    <section>
      <h1>My event requests</h1>
      <Link to="/events/drafts/new">New event request</Link>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}

      {empty && <p>{result.message}</p>}
      {result && !empty && (
        <>
          <DraftsSection drafts={result.drafts} />
          <SubmittedSection requests={result.submitted} />
        </>
      )}
    </section>
  );
}
