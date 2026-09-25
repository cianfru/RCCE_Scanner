import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { applyTheme } from "./theme.js";

const ThemeContext = createContext({ mode: "dark", toggle: () => {} });

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem("rcce-theme") || "dark");

  useEffect(() => {
    applyTheme(mode);
    localStorage.setItem("rcce-theme", mode);
  }, [mode]);

  // Repaint the shared colour tables before the re-render that follows, not after it.
  const toggle = useCallback(() => setMode(m => { const next = m === "dark" ? "light" : "dark"; applyTheme(next); return next; }), []);

  return (
    <ThemeContext.Provider value={{ mode, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
