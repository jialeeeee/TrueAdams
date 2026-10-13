import { useState } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "../api/client.js";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError("");
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await apiClient.post("/auth/login", { email, password });
      const token = response.data?.access_token;
      if (typeof token !== "string" || !token.trim()) {
        setError("Sign-in could not be completed. Please try again.");
        return;
      }
      sessionStorage.setItem("access_token", token);
      navigate("/");
    } catch (failure) {
      const status = failure.response?.status;
      const explanation = failure.response?.data?.error;
      setError(
        (status === 400 || status === 401) && typeof explanation === "string" && explanation.trim()
          ? explanation
          : "Sign-in is temporarily unavailable. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="auth-card" onSubmit={handleSubmit}>
      <h1>Login</h1>
      {error && <p role="alert">{error}</p>}
      <label htmlFor="login-email">Email</label>
      <input
        id="login-email"
        type="email"
        autoComplete="username"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
      />
      <label htmlFor="login-password">Password</label>
      <input
        id="login-password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      <button type="submit" disabled={submitting}>Login</button>
    </form>
  );
}
