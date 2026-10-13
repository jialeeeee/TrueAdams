import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import AppShell from "./components/AppShell.jsx";
import "./styles/app.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppShell>
        <App />
      </AppShell>
    </BrowserRouter>
  </React.StrictMode>,
);
