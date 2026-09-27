import "./auth.js";   // installs the API token before anything fetches
import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "./ThemeContext";

import AuthGate from "./components/AuthGate";
import ErrorBoundary from "./components/ErrorBoundary";
const ResearchApp = lazy(() => import("./ResearchApp.jsx"));
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
            {["/scanner/*", "/signals", "/analytics", "/hyperlens", "/tradfi", "/ai", "/backtest", "/executor", "/portfolio", "/admin"].map(path => <Route
              key={path} path={path}
              element={
                <AuthGate>
                  <Suspense fallback={<div role="status" style={{padding:40,color:"#F5FEFD",background:"#04060C",minHeight:"100vh"}}>Loading your research workspace…</div>}><ResearchApp /></Suspense>
                </AuthGate>
              }
            />)}
            <Route path="*" element={<main style={{minHeight:"100vh",display:"grid",placeContent:"center",gap:20,padding:32,background:"#04060C",color:"#F5FEFD",fontFamily:"var(--font-geist-sans)"}}><p style={{color:"#97FCE4"}}>404 · Reflex</p><h1>This page could not be found.</h1><p>The link may have moved. Return to the research workspace or the homepage.</p><div style={{display:"flex",gap:24}}><a style={{color:"#97FCE4"}} href="/scanner">Open scanner</a><a style={{color:"#97FCE4"}} href="/">Back to home</a></div></main>}/>
          </Routes>
        </ErrorBoundary>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
