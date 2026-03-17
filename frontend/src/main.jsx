import React from "react";
import ReactDOM from "react-dom/client";
import { ThemeProvider } from "./ThemeContext";
import { WalletProvider } from "./WalletContext";
import AuthGate from "./components/AuthGate";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthGate>
        <WalletProvider>
          <App />
        </WalletProvider>
      </AuthGate>
    </ThemeProvider>
  </React.StrictMode>
);
