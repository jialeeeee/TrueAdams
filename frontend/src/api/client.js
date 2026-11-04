import axios from "axios";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:5000/api",
});

apiClient.interceptors.request.use((config) => {
  // SCRUM-75 AC6: signing out sends the token it signs out of, which the browser has
  // already forgotten by the time the request goes.
  const token = config.signingOutToken ?? sessionStorage.getItem("access_token");
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  } else {
    config.headers.delete("Authorization");
  }
  return config;
});

export default apiClient;
