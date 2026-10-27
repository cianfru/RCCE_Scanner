import asyncio
import math
import sys

import numpy as np
import pytest

import yf_source


def _bars(n, seed):
    rng = np.random.default_rng(seed)
    d = {f: rng.random(n) * 1000 for f in yf_source.FIELDS}
    d["timestamp"] = np.arange(n, dtype=np.float64) * 14_400_000 + 1.7e12
    d["volume"][3] = np.nan
    d["open"][5] = 1 / 3
    return d


def test_json_transport_is_exact_including_nan():
    src = {"GC=F": _bars(50, 1), "^VIX": None, "DX-Y.NYB": _bars(7, 2)}
    out = yf_source.decode(yf_source.encode(src))
    assert out["^VIX"] is None
    for t in ("GC=F", "DX-Y.NYB"):
        for f in yf_source.FIELDS:
            assert out[t][f].dtype == np.float64
            assert np.array_equal(out[t][f], src[t][f], equal_nan=True)
    assert math.isnan(out["GC=F"]["volume"][3]) and out["GC=F"]["open"][5] == 1 / 3


def test_child_process_answers_json_and_reports_download_failures(monkeypatch, tmp_path):
    # Run the module as the child does, with yfinance replaced by a stub that fails.
    stub = tmp_path / "yfinance.py"
    stub.write_text("def download(*a, **k):\n    print('progress bar on stdout')\n    raise RuntimeError('offline')\n")

    async def run():
        import os
        env = dict(os.environ, PYTHONPATH=f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")
        proc = await asyncio.create_subprocess_exec(sys.executable, yf_source.__file__, "1d", "GC=F",
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        out, err = await proc.communicate()
        return proc.returncode, out, err
    rc, out, err = asyncio.run(run())
    assert rc == yf_source.DOWNLOAD_FAILED and out == b"" and b"offline" in err


def test_batch_fetch_goes_through_the_child_download(monkeypatch):
    import data_fetcher as df
    calls = []

    async def fake_download(tickers, timeframe):
        calls.append((tuple(tickers), timeframe))
        return {t: _bars(10, i) for i, t in enumerate(tickers)}
    monkeypatch.setattr(df, "_yf_download", fake_download)
    monkeypatch.setattr(df._cache, "get", lambda *a: None)
    res = asyncio.run(df.fetch_batch_yfinance("1d"))
    assert len(calls) == 1 and len(calls[0][0]) == len(df.TRADFI_SYMBOLS)
    assert all(v is not None for v in res.values())
