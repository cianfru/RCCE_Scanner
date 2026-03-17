import { useState } from "react";
import { T } from "../theme.js";

const PASSWORD = "Admin123";
const AUTH_KEY = "reflex_auth";

export function isAuthenticated() {
  return sessionStorage.getItem(AUTH_KEY) === "1";
}

export default function AuthGate({ children }) {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [value, setValue] = useState("");
  const [error, setError] = useState(false);
  const [shaking, setShaking] = useState(false);

  if (authed) return children;

  const submit = (e) => {
    e.preventDefault();
    if (value === PASSWORD) {
      sessionStorage.setItem(AUTH_KEY, "1");
      setAuthed(true);
    } else {
      setError(true);
      setShaking(true);
      setTimeout(() => setShaking(false), 500);
      setValue("");
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: T.bg,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: T.font,
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Ambient glow */}
      <div style={{
        position: "absolute", top: "20%", left: "30%",
        width: 400, height: 400, borderRadius: "50%",
        background: `radial-gradient(circle, ${T.accent}12 0%, transparent 70%)`,
        filter: "blur(80px)", pointerEvents: "none",
      }} />
      <div style={{
        position: "absolute", bottom: "10%", right: "20%",
        width: 300, height: 300, borderRadius: "50%",
        background: `radial-gradient(circle, ${T.purple || "#a78bfa"}10 0%, transparent 70%)`,
        filter: "blur(80px)", pointerEvents: "none",
      }} />

      {/* Logo */}
      <div style={{ position: "relative", zIndex: 1, textAlign: "center", marginBottom: 48 }}>
        <img
          src="/logo.png"
          alt="Reflex"
          style={{ height: 56, width: "auto", objectFit: "contain", display: "block", margin: "0 auto" }}
        />
        <p style={{
          marginTop: 12, fontSize: 14, color: T.text4, letterSpacing: "0.04em",
        }}>
          Market intelligence, distilled.
        </p>
      </div>

      {/* Login card */}
      <form onSubmit={submit} style={{
        position: "relative", zIndex: 1,
        background: T.cardBg || T.overlay04,
        border: `1px solid ${T.border}`,
        borderRadius: 16, padding: "32px 36px",
        width: 340, maxWidth: "90vw",
        backdropFilter: "blur(20px)",
        boxShadow: `0 8px 32px rgba(0,0,0,0.4)`,
        animation: shaking ? "shake 0.4s ease-in-out" : undefined,
      }}>
        <label style={{
          display: "block", fontSize: 11, fontFamily: T.mono,
          color: T.text4, letterSpacing: "0.1em", marginBottom: 10,
          textTransform: "uppercase",
        }}>
          Access Code
        </label>
        <input
          type="password"
          value={value}
          onChange={e => { setValue(e.target.value); setError(false); }}
          autoFocus
          placeholder="Enter password"
          style={{
            width: "100%", padding: "12px 14px",
            fontSize: 14, fontFamily: T.mono,
            background: T.bg, color: T.text1,
            border: `1px solid ${error ? "#ef4444" : T.border}`,
            borderRadius: 10, outline: "none",
            transition: "border-color 0.2s",
          }}
          onFocus={e => e.target.style.borderColor = error ? "#ef4444" : T.accent}
          onBlur={e => e.target.style.borderColor = error ? "#ef4444" : T.border}
        />
        {error && (
          <p style={{
            fontSize: 12, color: "#ef4444", marginTop: 8, fontFamily: T.mono,
          }}>
            Invalid password
          </p>
        )}
        <button type="submit" style={{
          width: "100%", marginTop: 16, padding: "12px 0",
          fontSize: 13, fontWeight: 600, fontFamily: T.font,
          background: T.accent, color: T.bg,
          border: "none", borderRadius: 10, cursor: "pointer",
          letterSpacing: "0.04em",
          transition: "filter 0.2s",
          boxShadow: `0 0 24px ${T.accent}30`,
        }}
          onMouseEnter={e => e.target.style.filter = "brightness(1.15)"}
          onMouseLeave={e => e.target.style.filter = "none"}
        >
          Enter
        </button>
      </form>

      {/* Shake animation */}
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-8px); }
          40% { transform: translateX(8px); }
          60% { transform: translateX(-6px); }
          80% { transform: translateX(6px); }
        }
      `}</style>
    </div>
  );
}
