"""Public-data adapter for forward paper research; no account or order APIs."""

from __future__ import annotations
import asyncio
import logging
import os
import time
import aiohttp
from trading_setups import UNIVERSE, build_setups
from paper_setups import PaperLedger

log = logging.getLogger(__name__)
API = "https://api.hyperliquid.xyz/info"


def parse_book(payload):
    """Depth inside 10 bps of mid, not distant book walls."""
    try:
        bids, asks = payload["levels"]
        bid = float(bids[0]["px"])
        ask = float(asks[0]["px"])
        mid = (bid + ask) / 2
        return dict(
            bid=bid,
            ask=ask,
            observed_at=float(payload["time"]) / 1000,
            bid_depth_usd=sum(
                float(l["px"]) * float(l["sz"])
                for l in bids
                if float(l["px"]) >= mid * 0.999
            ),
            ask_depth_usd=sum(
                float(l["px"]) * float(l["sz"])
                for l in asks
                if float(l["px"]) <= mid * 1.001
            ),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def fetch_market(symbol, *, funding_start, session):
    from data_fetcher import _fetch_hl_candles

    coin = symbol.split("/")[0]

    async def info(payload):
        try:
            async with session.post(API, json=payload) as response:
                if response.status != 200:
                    return None
                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    book_task = info(dict(type="l2Book", coin=coin))
    candles_task = _fetch_hl_candles(session, coin, "4h", 120)
    funding_task = (
        info(
            dict(
                type="fundingHistory",
                coin=coin,
                startTime=int(funding_start * 1000),
                endTime=int(time.time() * 1000),
            )
        )
        if funding_start
        else asyncio.sleep(0, result=[])
    )
    book, candles, funding = await asyncio.gather(book_task, candles_task, funding_task)
    parsed = []
    for event in funding or []:
        try:
            parsed.append(
                dict(time=float(event["time"]) / 1000, rate=float(event["fundingRate"]))
            )
        except (KeyError, ValueError, TypeError):
            continue
    bars = None
    if candles is not None:
        bars = [
            dict(
                time=float(candles["timestamp"][i]) / 1000,
                **{k: float(candles[k][i]) for k in ("open", "high", "low", "close")},
            )
            for i in range(len(candles["timestamp"]))
        ]
    return dict(book=parse_book(book), candles=candles, bars=bars, funding=parsed)


def apply_research_cycle(cache, market, *, as_of):
    """Synchronous deterministic integration, independently testable with fixtures."""
    ledger = cache.paper_ledger
    # Process commitments using their original definitions before considering new context.
    ledger.advance_all(market, as_of=as_of)
    daily = {r["symbol"]: r for r in cache.results.get("1d", [])}
    for row in cache.results.get("4h", []):
        if row["symbol"] not in UNIVERSE:
            continue
        d = daily.get(row["symbol"])
        feed = market.get(row["symbol"], {})
        definitions = build_setups(
            row, d, feed.get("candles"), feed.get("book"), as_of=as_of
        )
        observed = []
        if row.get("signal") in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG") or (
            d or {}
        ).get("signal") in ("TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"):
            ledger.cancel_pending(
                row["symbol"],
                "New scanner exit warning cancelled unfilled setups",
                as_of=as_of,
            )
        elif row.get("regime") in ("MARKDOWN", "BLOWOFF") or (d or {}).get(
            "regime"
        ) in ("MARKDOWN", "BLOWOFF", "CAP"):
            ledger.cancel_pending(
                row["symbol"], "Daily context became bearish", as_of=as_of
            )
        elif any(item["status"] == "unavailable" for item in definitions):
            ledger.cancel_pending(
                row["symbol"],
                "Required context or execution feed unavailable",
                as_of=as_of,
            )
        for definition in definitions:
            observed.append(ledger.observe(definition))
        row["trading_setups"] = observed
    records = ledger.records()
    cache.paper_setup_cards = {}
    for row in cache.results.get("4h", []):
        if row["symbol"] not in UNIVERSE:
            continue
        active = {
            r["contract"]["strategy"]: r
            for r in records
            if r["contract"]["symbol"] == row["symbol"]
            and r["state"]["status"] in ("pending", "scheduled", "open")
        }
        row["trading_setups"] = [
            active.get(r["contract"]["strategy"], r)
            for r in row.get("trading_setups", [])
        ]
        cache.paper_setup_cards[row["symbol"]] = row["trading_setups"]
    for row in cache.results.get("1d", []):
        row["trading_setups"] = cache.paper_setup_cards.get(row["symbol"], [])
    cache.paper_research_updated_at = as_of
    cache.paper_research_error = None


async def update_setup_research(cache):
    if os.environ.get("PAPER_SETUPS_ENABLED", "1").lower() in ("0", "false", "off"):
        return
    if not hasattr(cache, "paper_research_lock"):
        cache.paper_research_lock = asyncio.Lock()
    if cache.paper_research_lock.locked() or time.time() < getattr(
        cache, "paper_research_next_at", 0
    ):
        for row in cache.results.get("4h", []) + cache.results.get("1d", []):
            row["trading_setups"] = getattr(cache, "paper_setup_cards", {}).get(
                row["symbol"], []
            )
        return
    async with cache.paper_research_lock:
        cache.paper_research_next_at = time.time() + 60
        try:
            if not hasattr(cache, "paper_ledger"):
                cache.paper_ledger = PaperLedger()
            records = cache.paper_ledger.records()
            now = time.time()
            starts = {}
            for symbol in UNIVERSE:
                pending = [
                    r["state"]["entry_at"]
                    for r in records
                    if r["contract"]["symbol"] == symbol
                    and r["state"].get("entry_at") is not None
                    and (
                        r["state"]["status"] == "open"
                        or (
                            r["state"]["status"] == "closed"
                            and not r["state"]["funding_complete"]
                        )
                    )
                ]
                starts[symbol] = max(now - 7 * 86400, min(pending)) if pending else None
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                responses = await asyncio.gather(
                    *(
                        fetch_market(s, funding_start=starts[s], session=session)
                        for s in UNIVERSE
                    ),
                    return_exceptions=True,
                )
            market = {s: r for s, r in zip(UNIVERSE, responses) if isinstance(r, dict)}
            apply_research_cycle(cache, market, as_of=time.time())
        except Exception as exc:
            cache.paper_research_error = type(exc).__name__
            log.exception("Forward paper research update unavailable")


def schedule_setup_research(cache):
    """Do not put public research fetch latency on the scanner/executor path."""
    for row in cache.results.get("4h", []) + cache.results.get("1d", []):
        row["trading_setups"] = getattr(cache, "paper_setup_cards", {}).get(
            row["symbol"], []
        )
    if getattr(cache, "paper_research_stopped", False):
        return
    task = getattr(cache, "paper_research_task", None)
    if task is not None and not task.done():
        return
    if time.time() < getattr(cache, "paper_research_next_at", 0):
        return
    cache.paper_research_task = asyncio.create_task(update_setup_research(cache))


async def stop_setup_research(cache):
    cache.paper_research_stopped = True
    task = getattr(cache, "paper_research_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    ledger = getattr(cache, "paper_ledger", None)
    if ledger is not None:
        ledger.close()
