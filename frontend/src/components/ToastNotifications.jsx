import { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";
import { T } from "../theme.js";

// ---------------------------------------------------------------------------
// Toast Context + Provider
// ---------------------------------------------------------------------------

const ToastContext = createContext(null);

// Global event bus — allows firing toasts without importing useToast
// (avoids circular import / TDZ issues in production builds)
const _listeners = new Set();
export function fireToast(opts) {
  _listeners.forEach(fn => fn(opts));
}

const TOAST_COLORS = {
  entry:   "#34d399",
  exit:    "#f87171",
  warning: "#fbbf24",
  whale:   "#c084fc",
  info:    T.accent,
};

const MAX_TOASTS = 3;
const AUTO_DISMISS_MS = 8000;

let _toastId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef({});

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
    if (timersRef.current[id]) {
      clearTimeout(timersRef.current[id]);
      delete timersRef.current[id];
    }
  }, []);

  const addToast = useCallback(({ type = "info", title, body, symbol, severity }) => {
    const id = ++_toastId;
    const color = TOAST_COLORS[type] || TOAST_COLORS.info;

    setToasts(prev => {
      const next = [{ id, type, title, body, symbol, severity, color, createdAt: Date.now() }, ...prev];
      // Evict oldest if over max
      if (next.length > MAX_TOASTS) {
        const evicted = next.pop();
        if (timersRef.current[evicted.id]) {
          clearTimeout(timersRef.current[evicted.id]);
          delete timersRef.current[evicted.id];
        }
      }
      return next;
    });

    // Auto-dismiss
    timersRef.current[id] = setTimeout(() => removeToast(id), AUTO_DISMISS_MS);

    return id;
  }, [removeToast]);

  // Register addToast on the global event bus
  useEffect(() => {
    _listeners.add(addToast);
    return () => _listeners.delete(addToast);
  }, [addToast]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      Object.values(timersRef.current).forEach(clearTimeout);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ addToast, removeToast, toasts }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Toast Stack — renders floating notifications
// ---------------------------------------------------------------------------

export function ToastStack() {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div style={{
      position: "fixed",
      bottom: "env(safe-area-inset-bottom, 16px)",
      right: 16,
      zIndex: 9999,
      display: "flex",
      flexDirection: "column-reverse",
      gap: 8,
      maxWidth: 360,
      width: "calc(100vw - 32px)",
      pointerEvents: "none",
    }}>
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single Toast Item
// ---------------------------------------------------------------------------

function ToastItem({ toast, onDismiss }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Trigger slide-in on next frame
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      onClick={onDismiss}
      style={{
        pointerEvents: "auto",
        cursor: "pointer",
        background: T.popoverBg,
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: `1px solid ${T.border}`,
        borderLeft: `3px solid ${toast.color}`,
        borderRadius: 12,
        padding: "12px 16px",
        boxShadow: `0 8px 32px ${T.shadowDeep}`,
        transform: visible ? "translateX(0)" : "translateX(120%)",
        opacity: visible ? 1 : 0,
        transition: "transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      {/* Title row */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
      }}>
        <span style={{
          fontSize: 12,
          fontWeight: 700,
          fontFamily: T.mono,
          color: toast.color,
          letterSpacing: "0.02em",
        }}>
          {toast.title}
        </span>
        {toast.symbol && (
          <span style={{
            fontSize: 10,
            fontWeight: 600,
            fontFamily: T.mono,
            color: T.text3,
            background: T.surface,
            padding: "2px 6px",
            borderRadius: 4,
          }}>
            {toast.symbol}
          </span>
        )}
      </div>

      {/* Body */}
      {toast.body && (
        <span style={{
          fontSize: 11,
          fontFamily: T.mono,
          color: T.text2,
          lineHeight: 1.4,
        }}>
          {toast.body}
        </span>
      )}

      {/* Progress bar */}
      <div style={{
        position: "absolute",
        bottom: 0,
        left: 3,
        right: 0,
        height: 2,
        borderRadius: "0 0 12px 12px",
        overflow: "hidden",
      }}>
        <div style={{
          height: "100%",
          background: toast.color,
          opacity: 0.4,
          animation: `toast-progress ${AUTO_DISMISS_MS}ms linear forwards`,
        }} />
      </div>
    </div>
  );
}

// Inject keyframes once
if (typeof document !== "undefined" && !document.getElementById("toast-keyframes")) {
  const style = document.createElement("style");
  style.id = "toast-keyframes";
  style.textContent = `
    @keyframes toast-progress {
      from { width: 100%; }
      to { width: 0%; }
    }
  `;
  document.head.appendChild(style);
}
