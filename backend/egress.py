"""
egress.py
~~~~~~~~~
Network egress: conditional GETs (ETag / 304) and a per-endpoint byte counter.

Railway bills data sent from the server, so two ASGI middlewares live here:

* ``ConditionalGetMiddleware`` gives JSON GET responses under ``/api/`` a strong
  ETag and answers ``If-None-Match`` with an empty 304 when the body has not
  changed. An endpoint may set its own ETag (``/api/scan`` does, from its cached
  body); otherwise the ETag is a hash of the body, with the per-request
  ``cache_age_seconds`` field left out so an unchanged payload still matches.
  Responses carry ``Cache-Control: no-cache``: browsers keep the body and
  revalidate on every fetch, so data is never served stale.
  It must sit inside GZipMiddleware (added before it) so it sees the plain body.

* ``EgressCounterMiddleware`` counts bytes actually sent per endpoint (status
  line excluded; headers and body after gzip included). It must be the outermost
  middleware (added last). WebSocket traffic is counted by ``ws_hub`` through
  :func:`record_ws`.

``snapshot()`` feeds the read-only ``/api/net-stats`` endpoint.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
import zlib
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# ETag helpers
# ---------------------------------------------------------------------------

# Per-request fields that change on every call without the data changing.
_VOLATILE = re.compile(rb'"cache_age_seconds":\s*(?:null|-?[0-9][0-9.eE+-]*)')


def etag_for(body: bytes) -> str:
    """Strong ETag for a JSON body, ignoring the per-request cache age."""
    if b'"cache_age_seconds"' in body:
        body = _VOLATILE.sub(b"", body)
    return '"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'


def etag_matches(if_none_match: Optional[str], etag: str) -> bool:
    """True when an If-None-Match header names *etag* (weak comparison, RFC 9110)."""
    if not if_none_match or not etag:
        return False
    if if_none_match.strip() == "*":
        return True
    bare = etag[2:] if etag.startswith("W/") else etag
    for tag in if_none_match.split(","):
        tag = tag.strip()
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag == bare:
            return True
    return False


# Paths that never get an ETag: admin and auth answers, the counter itself.
_ETAG_SKIP_PREFIXES = ("/api/admin", "/api/auth", "/api/net-stats")


def _etag_applies(scope) -> bool:
    if scope.get("type") != "http" or scope.get("method") != "GET":
        return False
    path = scope.get("path", "")
    return path.startswith("/api/") and not path.startswith(_ETAG_SKIP_PREFIXES)


def _header(headers, name: bytes) -> Optional[str]:
    for k, v in headers:
        if k.lower() == name:
            return v.decode("latin-1")
    return None


class ConditionalGetMiddleware:
    """ETag + 304 for JSON GET responses under /api/ (see module docstring)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if not _etag_applies(scope):
            await self.app(scope, receive, send)
            return
        if_none_match = _header(scope.get("headers") or [], b"if-none-match")
        start: Optional[dict] = None
        chunks: list = []
        passthrough = False

        async def send_wrapper(message) -> None:
            nonlocal start, passthrough
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.start":
                ctype = (_header(message.get("headers") or [], b"content-type") or "").lower()
                cc = (_header(message.get("headers") or [], b"cache-control") or "").lower()
                if message.get("status") != 200 or not ctype.startswith("application/json") or "no-store" in cc:
                    passthrough = True
                    await send(message)
                    return
                start = message
                return
            if message["type"] != "http.response.body" or start is None:
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return
            body = b"".join(chunks)
            headers = [(k, v) for k, v in start.get("headers") or []]
            etag = _header(headers, b"etag")
            if etag is None:
                etag = etag_for(body)
                headers.append((b"etag", etag.encode("latin-1")))
            if _header(headers, b"cache-control") is None:
                headers.append((b"cache-control", b"no-cache"))
            if etag_matches(if_none_match, etag):
                keep = {b"etag", b"cache-control", b"cdn-cache-control", b"vary"}
                await send({"type": "http.response.start", "status": 304,
                            "headers": [(k, v) for k, v in headers if k.lower() in keep]})
                await send({"type": "http.response.body", "body": b""})
                return
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------------------
# Egress counter
# ---------------------------------------------------------------------------

_MAX_KEYS = 400            # distinct endpoints kept; the rest pool under "(other)"


class _Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.since = time.time()
        self.http: Dict[str, list] = {}   # key -> [requests, bytes, not_modified]
        self.ws: Dict[str, list] = {}     # event type -> [messages, raw_bytes, est_wire_bytes]


STATS = _Stats()


def reset() -> None:
    with STATS.lock:
        STATS.reset()


def _bump(table: Dict[str, list], key: str, values) -> None:
    row = table.get(key)
    if row is None:
        if len(table) >= _MAX_KEYS:
            key = "(other)"
            row = table.get(key)
        if row is None:
            row = table[key] = [0] * len(values)
    for i, v in enumerate(values):
        row[i] += v


def record_http(key: str, nbytes: int, not_modified: bool) -> None:
    with STATS.lock:
        _bump(STATS.http, key, (1, nbytes, 1 if not_modified else 0))


def estimate_deflate(payload: str) -> int:
    """Bytes a payload takes after WebSocket permessage-deflate (uvicorn: 12-bit window).

    Measured per message without the shared context, so it is an upper bound.
    Very large payloads are estimated from the measured ratio instead of compressed.
    """
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(data) > 256 * 1024:
        return int(len(data) * 0.28)
    co = zlib.compressobj(6, zlib.DEFLATED, -12, 5)
    return len(co.compress(data) + co.flush(zlib.Z_SYNC_FLUSH)) - 4


def record_ws(event_type: str, payload_len: int, recipients: int, est_wire: int) -> None:
    """Count one WebSocket payload sent to *recipients* clients."""
    if recipients <= 0:
        return
    with STATS.lock:
        _bump(STATS.ws, event_type or "?", (recipients, payload_len * recipients, est_wire * recipients))


def _route_key(scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    raw = scope.get("path", "")
    # Unmatched paths are not echoed back (they can hold anything); static pages pool.
    return "(unmatched)" if raw.startswith("/api/") else "(non-api)"


class EgressCounterMiddleware:
    """Counts bytes sent per endpoint: headers plus body as sent (after gzip)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        sent = 0
        status = 0

        async def send_wrapper(message) -> None:
            nonlocal sent, status
            if message["type"] == "http.response.start":
                status = message.get("status", 0)
                # "HTTP/1.1 200 OK\r\n" plus "name: value\r\n" per header and the blank line.
                sent += 17 + sum(len(k) + len(v) + 4 for k, v in message.get("headers") or []) + 2
            elif message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            method = scope.get("method", "GET")
            key = _route_key(scope)
            if method == "OPTIONS":
                key = "OPTIONS (CORS preflight)"   # answered before routing
            elif method not in ("GET", "HEAD"):
                key = f"{method} {key}"
            record_http(key, sent, status == 304)


def snapshot(ws_clients: Optional[dict] = None, top: int = 40) -> dict:
    """Totals since start (or the last reset), rates per hour and the largest endpoints."""
    with STATS.lock:
        http = {k: list(v) for k, v in STATS.http.items()}
        ws = {k: list(v) for k, v in STATS.ws.items()}
        since = STATS.since
    elapsed = max(1.0, time.time() - since)
    per_hour = 3600.0 / elapsed
    http_bytes = sum(v[1] for v in http.values())
    ws_raw = sum(v[1] for v in ws.values())
    ws_wire = sum(v[2] for v in ws.values())
    rows = sorted(http.items(), key=lambda kv: kv[1][1], reverse=True)
    return {
        "since": round(since, 1),
        "elapsed_s": round(elapsed, 1),
        "http": {
            "requests": sum(v[0] for v in http.values()),
            "not_modified": sum(v[2] for v in http.values()),
            "bytes": http_bytes,
            "bytes_per_hour": int(http_bytes * per_hour),
            "by_endpoint": [
                {"endpoint": k, "requests": v[0], "not_modified": v[2], "bytes": v[1],
                 "avg_bytes": int(v[1] / v[0]) if v[0] else 0,
                 "bytes_per_hour": int(v[1] * per_hour)}
                for k, v in rows[:top]
            ],
        },
        "ws": {
            "messages": sum(v[0] for v in ws.values()),
            "raw_bytes": ws_raw,
            "est_wire_bytes": ws_wire,
            "est_wire_bytes_per_hour": int(ws_wire * per_hour),
            "by_type": {k: {"messages": v[0], "raw_bytes": v[1], "est_wire_bytes": v[2]}
                        for k, v in sorted(ws.items(), key=lambda kv: kv[1][2], reverse=True)},
            "clients": ws_clients or {},
        },
        "total_est_bytes_per_hour": int((http_bytes + ws_wire) * per_hour),
        "note": ("HTTP bytes are measured as sent: headers plus body after gzip (TLS and TCP "
                 "overhead not included). WebSocket bytes are the JSON payload per recipient; "
                 "est_wire_bytes estimates permessage-deflate per message without the shared "
                 "context, so it is an upper bound. Counters reset on restart."),
    }
