import { useEffect, useState } from "react";
import apiClient from "../api/client.js";

export default function RegistrationsPage() {
  const [registrations, setRegistrations] = useState([]);

  useEffect(() => {
    apiClient.get("/registrations/").then((res) => setRegistrations(res.data));
  }, []);

  return (
    <section>
      <h1>Registrations</h1>
      <ul>
        {registrations.map((registration) => (
          <li key={registration.id}>{registration.id}</li>
        ))}
      </ul>
    </section>
  );
}
