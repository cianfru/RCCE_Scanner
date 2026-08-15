/**
 * apiClient — attaches the API auth token to backend requests.
 *
 * When VITE_API_TOKEN is set (and matches the backend's API_AUTH_TOKEN), it's
 * added as `Authorization: Bearer <token>` to every fetch aimed at the API,
 * so the whole existing codebase stays untouched — no per-call changes.
 *
 * Note: a token shipped in a static SPA is visible to anyone who inspects the
 * bundle/network. It is not a user-secret; its job is to stop drive-by access
 * to the backend by anyone who merely discovers the Railway URL. Combined with
 * the CORS allow-list, that closes the "open to the whole internet" hole.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const API_TOKEN = import.meta.env.VITE_API_TOKEN || "";

function isApiUrl(url) {
  return typeof url === "string" && (url.startsWith(API_BASE) || url.startsWith("/api/"));
}

if (API_TOKEN && typeof window !== "undefined" && typeof window.fetch === "function") {
  const origFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    try {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      if (isApiUrl(url)) {
        const headers = new Headers(
          (init && init.headers) || (typeof input !== "string" && input.headers) || {}
        );
        if (!headers.has("Authorization")) {
          headers.set("Authorization", `Bearer ${API_TOKEN}`);
        }
        init = { ...init, headers };
      }
    } catch {
      /* fall through to the unmodified request */
    }
    return origFetch(input, init);
  };
}
