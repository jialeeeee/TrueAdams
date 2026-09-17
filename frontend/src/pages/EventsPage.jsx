import { useEffect, useState } from "react";
import apiClient from "../api/client.js";

export default function EventsPage() {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    apiClient.get("/events/").then((res) => setEvents(res.data));
  }, []);

  return (
    <section>
      <h1>Events</h1>
      <ul>
        {events.map((event) => (
          <li key={event.id}>{event.title}</li>
        ))}
      </ul>
    </section>
  );
}
