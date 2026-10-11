import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { MotionPreferenceProvider } from "./hooks/MotionPreference";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionPreferenceProvider>
      <App />
    </MotionPreferenceProvider>
  </React.StrictMode>,
);
