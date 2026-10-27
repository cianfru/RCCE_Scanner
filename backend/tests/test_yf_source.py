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
    answer = yf_source.decode(yf_source.encode(src, None, ["/x/a.pyc"]))
    out = answer["bars"]
    assert answer["ok"] and answer["files"] == ["/x/a.pyc"] and out["^VIX"] is None
    for t in ("GC=F", "DX-Y.NYB"):
        for f in yf_source.FIELDS:
            assert out[t][f].dtype == np.float64
            assert np.array_equal(out[t][f], src[t][f], equal_nan=True)
    assert math.isnan(out["GC=F"]["volume"][3]) and out["GC=F"]["open"][5] == 1 / 3


def _stub(tmp_path, body):
    (tmp_path / "yfinance.py").write_text(body)


def _run_child(tmp_path, *args):
    import os

    async def run():
        env = dict(os.environ, PYTHONPATH=f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")
        proc = await asyncio.create_subprocess_exec(sys.executable, yf_source.__file__, *args,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        out, err = await proc.communicate()
        return proc.returncode, out, err
    return asyncio.run(run())


def test_child_reports_a_failed_download_and_the_files_it_read(tmp_path):
    _stub(tmp_path, "def download(*a, **k):\n    print('progress bar on stdout')\n    raise RuntimeError('offline')\n")
    rc, out, err = _run_child(tmp_path, "1d", "GC=F")
    answer = yf_source.decode(out.decode())
    assert rc == 0 and not answer["ok"] and "offline" in answer["error"]
    assert any(f.endswith("yfinance.py") for f in answer["files"])        # the stub was imported
    assert b"progress bar" in err                                           # stdout stays clean JSON


def test_a_failed_download_is_not_retried_in_the_server(tmp_path, monkeypatch):
    import data_fetcher as df
    _stub(tmp_path, "def download(*a, **k):\n    raise RuntimeError('offline')\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    dropped = []
    monkeypatch.setattr(df, "_drop_cached_pages", lambda paths: dropped.extend(paths))
    monkeypatch.setattr(yf_source, "download_batch", lambda *a: pytest.fail("retried in the server"))
    with pytest.raises(df._YFDownloadFailed, match="offline"):
        asyncio.run(df._yf_download(["GC=F"], "1d"))
    assert dropped                                                          # the child's files are dropped


def test_a_child_that_cannot_start_falls_back_in_process(monkeypatch):
    import data_fetcher as df

    async def no_spawn(*a, **k):
        raise OSError("cannot spawn")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", no_spawn)
    monkeypatch.setattr(yf_source, "download_batch", lambda tickers, tf: {t: _bars(10, 0) for t in tickers})
    out = asyncio.run(df._yf_download(["GC=F"], "1d"))
    assert set(out) == {"GC=F"}


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
