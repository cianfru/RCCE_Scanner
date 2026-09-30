import "./auth.js";   // installs the API token before anything fetches
import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import { Landing } from "./landing/Landing.jsx";

// The app (and its socket and shared worker) loads only on the gated routes.
const GatedApp = lazy(() => import("./GatedApp.jsx"));

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          {/* Public marketing landing */}
          <Route path="/" element={<Landing />} />
          <Route path="/onchain" element={<Navigate to="/scanner" replace />} />
          {/* The scanner app (gated): /scanner, /scanner/:symbol, etc. */}
          <Route
            path="/*"
            element={
              <Suspense fallback={<div style={{ minHeight: "100vh", background: "var(--t-bg, #04060C)" }} />}>
                <GatedApp />
              </Suspense>
            }
          />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>
);
