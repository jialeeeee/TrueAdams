import { useEffect, useState } from "react";
import apiClient from "../api/client.js";

export default function VenuesPage() {
  const [venues, setVenues] = useState([]);

  useEffect(() => {
    apiClient.get("/venues/").then((res) => setVenues(res.data));
  }, []);

  return (
    <section>
      <h1>Venues</h1>
      <ul>
        {venues.map((venue) => (
          <li key={venue.id}>{venue.name}</li>
        ))}
      </ul>
    </section>
  );
}
