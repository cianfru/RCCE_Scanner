import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "./ThemeContext";
import { WalletProvider } from "./WalletContext";
import AuthGate from "./components/AuthGate";
import ErrorBoundary from "./components/ErrorBoundary";
import App from "./App";
import { RefinedLanding } from "./landing/RefinedLanding.tsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <ErrorBoundary>
          <Routes>
            {/* Public marketing landing */}
            <Route path="/" element={<RefinedLanding />} />
            <Route path="/onchain" element={<Navigate to="/scanner" replace />} />
            {/* The scanner app (gated) — /scanner, /scanner/:symbol, etc. */}
            <Route
              path="/*"
              element={
                <AuthGate>
                  <WalletProvider>
                    <App />
                  </WalletProvider>
                </AuthGate>
              }
            />
          </Routes>
        </ErrorBoundary>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
