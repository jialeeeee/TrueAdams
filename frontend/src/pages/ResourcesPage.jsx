import { useEffect, useState } from "react";
import apiClient from "../api/client.js";

export default function ResourcesPage() {
  const [resources, setResources] = useState([]);

  useEffect(() => {
    apiClient.get("/resources/").then((res) => setResources(res.data));
  }, []);

  return (
    <section>
      <h1>Resources</h1>
      <ul>
        {resources.map((resource) => (
          <li key={resource.id}>{resource.name}</li>
        ))}
      </ul>
    </section>
  );
}
