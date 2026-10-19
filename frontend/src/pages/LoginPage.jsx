import { useState } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "../api/client.js";

// SCRUM-75 Q1: use existing role pages; roles without one share Events (/).
// This selects navigation only. The backend remains responsible for permissions.
const ROLE_HOME_PATHS = {
  organiser: "/events/mine",
  coordinator: "/events/managed",
  coordinator_lead: "/events/supervised",
  venue_staff: "/venues/bookings",
};

export default function LoginPage({ loginAttempt }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    const attempt = ++loginAttempt.current;
    setError("");
    const missing = [];
    if (!email.trim()) missing.push("email");
    if (!password) missing.push("password");
    if (missing.length) {
      setError(`Please enter ${missing.join(" and ")}.`);
      return;
    }

    try {
      const response = await apiClient.post("/auth/login", { email, password });
      if (attempt !== loginAttempt.current) return;
      const token = response.data?.access_token;
      if (typeof token !== "string" || !token.trim()) {
        setError("Sign-in could not be completed. Please try again.");
        return;
      }
      sessionStorage.setItem("access_token", token);
      navigate(ROLE_HOME_PATHS[response.data.role] ?? "/", { replace: true });
    } catch (failure) {
      if (attempt !== loginAttempt.current) return;
      const status = failure.response?.status;
      const explanation = failure.response?.data?.error;
      setError(
        (status === 400 || status === 401) && typeof explanation === "string" && explanation.trim()
          ? explanation
          : "Sign-in is temporarily unavailable. Please try again.",
      );
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h1>Login</h1>
      {error && <p role="alert">{error}</p>}
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      <button type="submit">Login</button>
    </form>
  );
}
