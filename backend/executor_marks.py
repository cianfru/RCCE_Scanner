"""Cached reference marks for explicitly mapped legacy paper positions only.
These prices never feed scanner signals or order execution.
"""
import asyncio
import time
import math
import aiohttp

KRAKEN_PAIRS = {'MOG/USDT':'MOGUSD', 'ZEREBRO/USDT':'ZEREBROUSD',
                'TON/USDT':'TONUSD', 'MANA/USDT':'MANAUSD', 'VINE/USDT':'VINEUSD'}
# These two entry units were verified against the corresponding native daily
# candle: token entry * 1,000 lies inside the k-contract candle range.
VERIFIED_TOKEN_ENTRIES = {'BONK/USDT': (1786637063, .00000234, 'KBONK/USDT'),
                          'FLOKI/USDT': (1787256048, .00002317, 'KFLOKI/USDT')}
_cached = {}
_refreshed = 0.0
_lock = asyncio.Lock()


def converted_native_mark(position, marks):
    audit = VERIFIED_TOKEN_ENTRIES.get(position['symbol'])
    if not audit or int(position['entry_time']) != audit[0] or position['entry_price'] != audit[1]:
        return None
    native = marks.get(audit[2])
    if not native:
        return None
    return {**native, 'price': native['price'] / 1000,
            'source': f'Hyperliquid {audit[2]} / 1,000', 'entry_unit_verified': True}


def midpoint(bid, ask, volume):
    try:
        bid, ask, volume = float(bid), float(ask), float(volume)
        if all(math.isfinite(v) for v in (bid, ask, volume)) and bid > 0 and ask >= bid and volume > 0 and (ask-bid)/bid <= .1:
            return (bid+ask)/2
    except (ValueError, TypeError):
        pass
    return None


async def external_marks(symbols):
    global _refreshed, _cached
    supported = set(KRAKEN_PAIRS) | {'CHILLGUY/USDT'}
    if not (set(symbols) & supported):
        return {}
    async with _lock:
        if _refreshed and time.monotonic() - _refreshed < 900:
            return dict(_cached)
        # Cache failures as well: outages must not become one request per viewer.
        _refreshed = time.monotonic()
        found = {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async def kraken():
                try:
                    async with session.get('https://api.kraken.com/0/public/Ticker', params={'pair':','.join(KRAKEN_PAIRS.values())}) as response:
                        response.raise_for_status()
                        data = await response.json()
                    for symbol, pair in KRAKEN_PAIRS.items():
                        row = data.get('result', {}).get(pair, {})
                        price = midpoint(row.get('b',[None])[0], row.get('a',[None])[0], row.get('v',[0,0])[-1])
                        if price:
                            found[symbol] = {'price':price, 'observed_at':time.time(), 'source':f'Kraken {pair} spot midpoint (reference)'}
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, IndexError):
                    pass
            async def bybit():
                try:
                    async with session.get('https://api.bybit.com/v5/market/tickers', params={'category':'spot','symbol':'CHILLGUYUSDT'}) as response:
                        response.raise_for_status()
                        data = await response.json()
                    observed = float(data.get('time', 0))/1000
                    if abs(time.time()-observed) > 300:
                        return
                    for row in data.get('result',{}).get('list',[]):
                        if row.get('symbol') != 'CHILLGUYUSDT': continue
                        price = midpoint(row.get('bid1Price'), row.get('ask1Price'), row.get('turnover24h'))
                        if price:
                            found['CHILLGUY/USDT'] = {'price':price, 'observed_at':observed, 'source':'Bybit CHILLGUYUSDT spot midpoint (reference)'}
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    pass
            await asyncio.gather(kraken(), bybit())
        _cached = found
        return dict(_cached)
