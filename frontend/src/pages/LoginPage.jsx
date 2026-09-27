import { useState } from "react";
import { useNavigate } from "react-router-dom";
import apiClient from "../api/client.js";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }

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
