"""Cache Hyperliquid's published token SVGs. Run manually, never during scans."""
import concurrent.futures
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'frontend/public/token-logos'
API = 'https://rccescanner-production.up.railway.app/api/universe'


def fetch(market):
    # Resolve exact native market identity; do not lowercase or guess aliases.
    name = market['coin'] if market['kind'] == 'perpetual' else market['base']
    got = fetch_svg(market, name)
    # A "k" market (kPEPE: per 1,000 tokens) has no artwork of its own; the token's is used.
    if got is None and market['kind'] == 'perpetual' and re.fullmatch(r'k[A-Z0-9]+', name):
        got = fetch_svg(market, name[1:])
    return got


def fetch_svg(market, name):
    source = f'https://app.hyperliquid.xyz/coins/{quote(name, safe="")}.svg'
    try:
        with urlopen(source, timeout=15) as response:
            if 'image/svg+xml' not in response.headers.get('Content-Type', ''):
                return None
            data = response.read(262145)
        if len(data) > 262144:
            return None
        root = ET.fromstring(data)
        if root.tag.rsplit('}', 1)[-1] != 'svg':
            return None
        for element in root.iter():
            if element.tag.rsplit('}', 1)[-1].lower() in ('script', 'foreignobject'):
                return None
            for key, value in element.attrib.items():
                if key.lower().startswith('on') or ('href' in key.lower() and not value.startswith('#')):
                    return None
        filename = hashlib.sha256(data).hexdigest()[:16] + '.svg'
        (OUT / filename).write_bytes(data)
        return market['symbol'], {'src': '/token-logos/' + filename, 'source': source}
    except Exception:
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with urlopen(API, timeout=30) as response:
        markets = json.load(response)['markets']
    markets = [m for m in markets if not m.get('exclusion_reason')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        manifest = dict(item for item in pool.map(fetch, markets) if item)
    path = ROOT / 'frontend/src/data/tokenLogos.json'
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(f'{len(manifest)}/{len(markets)} markets have verified Hyperliquid SVGs; others use monograms.')


def main_xyz():
    """The TradFi (xyz builder dex) markets' SVGs, keyed by Hyperliquid's coin name ("xyz:NVDA"),
    for the Portfolio page. The universe comes from Hyperliquid's public info endpoint."""
    OUT.mkdir(parents=True, exist_ok=True)
    body = json.dumps({'type': 'meta', 'dex': 'xyz'}).encode()
    req = Request('https://api.hyperliquid.xyz/info', data=body, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=30) as response:
        names = [u['name'] for u in json.load(response)['universe'] if not u.get('isDelisted')]
    markets = [{'symbol': name, 'kind': 'perpetual', 'coin': name} for name in names]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        manifest = {k: v['src'] for k, v in (item for item in pool.map(lambda m: fetch_svg(m, m['coin']), markets) if item)}
    path = ROOT / 'frontend/src/data/xyzLogos.json'
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(f'{len(manifest)}/{len(markets)} xyz markets have verified Hyperliquid SVGs; others use monograms.')


if __name__ == '__main__':
    import sys
    main_xyz() if sys.argv[1:] == ['--xyz'] else main()
