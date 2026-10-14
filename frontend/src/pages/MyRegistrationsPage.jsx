import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "../api/client.js";
import explain from "../utils/explain.js";
import singaporeTime from "../utils/singaporeTime.js";
import statusLabel from "../utils/statusLabel.js";

// The attendee's registrations, with withdrawal from an active one (SCRUM-68).
const NOT_LOADED = "Your registrations could not be loaded. Check your connection and try again.";
const NOT_SAVED = "Your withdrawal was not saved. Check your connection and try again.";

function Entry({ registration, children }) {
  return (
    <li>
      <p>{registration.event.title}</p>
      <p>{`Starts: ${singaporeTime(registration.event.start_time)}`}</p>
      <p>{`Status: ${statusLabel(registration.status)}`}</p>
      {children}
    </li>
  );
}

export default function MyRegistrationsPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [asking, setAsking] = useState(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/registrations/");
      setResult(response.data);
    } catch (failure) {
      if (failure.response?.status === 401) {
        navigate("/login");
        return;
      }
      setLoadError(explain(failure, NOT_LOADED));
    }
  }, [navigate]);

  useEffect(() => {
    load();
  }, [load]);

  function ask(registration) {
    setError("");
    setMessage("");
    setAsking(registration);
  }

  async function withdraw() {
    // Also guards against a second click before the buttons re-render as disabled.
    if (sending) return;
    setSending(true);
    setError("");
    const target = asking;
    try {
      const response = await apiClient.post(`/registrations/${target.id}/withdraw`);
      setMessage(response.data.message);
      setResult((current) => ({
        ...current,
        active: current.active.filter((registration) => registration.id !== target.id),
        history: [
          { ...target, status: response.data.registration.status, can_withdraw: false },
          ...current.history,
        ],
      }));
    } catch (failure) {
      setError(explain(failure, NOT_SAVED));
    }
    setAsking(null);
    setSending(false);
  }

  return (
    <section>
      <h1>My registrations</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {result && result.message && <p>{result.message}</p>}

      {result && result.active.length > 0 && (
        <section aria-labelledby="active-heading">
          <h2 id="active-heading">Active registrations</h2>
          <ul>
            {result.active.map((registration) => (
              <Entry key={registration.id} registration={registration}>
                {registration.can_withdraw && (
                  <button type="button" onClick={() => ask(registration)}>
                    {`Withdraw from ${registration.event.title}`}
                  </button>
                )}
              </Entry>
            ))}
          </ul>
        </section>
      )}

      {result && result.history.length > 0 && (
        <section aria-labelledby="history-heading">
          <h2 id="history-heading">History</h2>
          <ul>
            {result.history.map((registration) => (
              <Entry key={registration.id} registration={registration} />
            ))}
          </ul>
        </section>
      )}

      {asking && (
        <div role="dialog" aria-modal="true" aria-labelledby="withdraw-heading">
          <h2 id="withdraw-heading">{`Withdraw from ${asking.event.title}?`}</h2>
          <p>Your place will be released for other attendees.</p>
          <button type="button" className="btn-primary" disabled={sending} onClick={withdraw}>
            Confirm
          </button>
          <button type="button" disabled={sending} onClick={() => setAsking(null)}>
            Cancel
          </button>
        </div>
      )}
    </section>
  );
}
