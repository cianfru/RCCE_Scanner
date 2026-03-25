import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "./ThemeContext";
import { WalletProvider } from "./WalletContext";
import AuthGate from "./components/AuthGate";
import { ToastProvider, ToastStack } from "./components/ToastNotifications";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthGate>
          <WalletProvider>
            <ToastProvider>
              <App />
              <ToastStack />
            </ToastProvider>
          </WalletProvider>
        </AuthGate>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
