import { useCallback, useEffect, useState } from "react";
import apiClient from "../api/client.js";
import canRetry from "../utils/canRetry.js";
import explain from "../utils/explain.js";
import formatSavedAt from "../utils/formatSavedAt.js";

// The signed-in user's in-app notifications, newest first. Every story that tells someone
// about a decision saves one; this is where they are read.
export default function NotificationsPage() {
  const [result, setResult] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [markError, setMarkError] = useState("");
  const [marking, setMarking] = useState(null);

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const response = await apiClient.get("/notifications/");
      setResult(response.data);
    } catch (failure) {
      setLoadError(explain(failure, "Your notifications could not be loaded. Check your connection and try again."));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function markRead(id) {
    setMarkError("");
    setMarking(id);
    try {
      const response = await apiClient.post(`/notifications/${id}/read`);
      const updated = response.data.notification;
      setResult((current) => ({
        ...current,
        notifications: current.notifications.map((n) => (n.id === updated.id ? updated : n)),
      }));
    } catch (failure) {
      const message = explain(failure, "The notification could not be marked as read.");
      setMarkError(canRetry(failure) ? `${message} You can try again.` : message);
    } finally {
      setMarking(null);
    }
  }

  return (
    <section>
      <h1>Notifications</h1>

      {loadError && (
        <>
          <p role="alert">{loadError}</p>
          <button type="button" onClick={load}>Retry</button>
        </>
      )}
      {markError && <p role="alert">{markError}</p>}

      {result && result.notifications.length === 0 && <p>{result.message}</p>}
      {result && result.notifications.length > 0 && (
        <ul>
          {result.notifications.map((notification) => (
            <li key={notification.id}>
              <p>
                {notification.read_at ? "" : "New · "}
                {`Received ${formatSavedAt(notification.created_at)}`}
              </p>
              <p>{notification.message}</p>
              {!notification.read_at && (
                <button
                  type="button"
                  onClick={() => markRead(notification.id)}
                  disabled={marking === notification.id}
                >
                  {marking === notification.id ? "Marking…" : "Mark as read"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
