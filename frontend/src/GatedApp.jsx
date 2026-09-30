// The scanner app behind the login gate. main.jsx loads this chunk only on app
// routes, so the landing page downloads none of the app code.
import { ThemeProvider } from "./ThemeContext";
import { WalletProvider } from "./WalletContext";
import AuthGate from "./components/AuthGate";
import App from "./App";

export default function GatedApp() {
  return (
    <ThemeProvider>
      <AuthGate>
        <WalletProvider>
          <App />
        </WalletProvider>
      </AuthGate>
    </ThemeProvider>
  );
}
