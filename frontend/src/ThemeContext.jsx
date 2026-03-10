import { createContext, useContext, useState, useCallback, useEffect } from "react";
import { applyTheme } from "./theme.js";

const ThemeContext = createContext({ mode: "dark", toggle: () => {} });

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem("rcce-theme") || "dark");

  useEffect(() => {
    applyTheme(mode);
    localStorage.setItem("rcce-theme", mode);
  }, [mode]);

  const toggle = useCallback(() => setMode(m => m === "dark" ? "light" : "dark"), []);

  return (
    <ThemeContext.Provider value={{ mode, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
