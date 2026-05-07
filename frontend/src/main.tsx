import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("app")!).render(
  <React.StrictMode>
    <App />
    <Toaster />
  </React.StrictMode>
);
