import { Component } from "react";
import { T } from "../theme.js";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: "2rem",
          textAlign: "center",
          fontFamily: T.font,
          color: T.text1,
          background: T.bg,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
        }}>
          <h2 style={{ color: T.red, margin: 0 }}>Something went wrong</h2>
          <p style={{ color: T.text3, maxWidth: 480, fontSize: T.textSm, fontFamily: T.mono }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
            style={{
              padding: "0.5rem 1.5rem",
              background: "transparent",
              color: T.text1,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: T.textSm,
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
