import asyncio
import os
import sqlite3
import time

import pytest

import memlog


@pytest.fixture
def volume(tmp_path, monkeypatch):
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.setattr(memlog, "_MIN_FILE_BYTES", 0)
    monkeypatch.setattr(memlog, "_kept_fds", {})
    yield tmp_path
    for fd in memlog._kept_fds.values():
        os.close(fd)


def test_release_keeps_sqlite_write_locks_in_both_journal_modes(volume):
    # Closing any descriptor of a database file drops the process's POSIX locks on it: the
    # release must keep its database descriptors open, and may open/close -wal and -journal files.
    for mode in ("wal", "delete"):
        path = str(volume / f"t_{mode}.db")
        a = sqlite3.connect(path, timeout=0.1, isolation_level=None)
        a.execute(f"PRAGMA journal_mode={mode}")
        a.execute("CREATE TABLE t (x BLOB)")
        a.execute("INSERT INTO t VALUES (?)", (os.urandom(8192),))
        a.execute("BEGIN IMMEDIATE")
        a.execute("INSERT INTO t VALUES (?)", (os.urandom(8192),))
        for _ in range(3):
            memlog.release_page_cache()
        b = sqlite3.connect(path, timeout=0.1, isolation_level=None)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            b.execute("BEGIN IMMEDIATE")
        a.execute("COMMIT")
        assert b.execute("SELECT count(*) FROM t").fetchone()[0] == 2
        assert b.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        a.close()
        b.close()
    kept = {os.path.basename(p) for p in memlog._kept_fds}
    assert kept == {"t_wal.db", "t_delete.db"}           # side files are never kept open


def test_release_reuses_one_descriptor_per_database(volume):
    path = volume / "store.db"
    sqlite3.connect(str(path)).execute("CREATE TABLE t (x)").connection.commit()
    memlog.release_page_cache()
    fd = memlog._kept_fds[str(path)]
    memlog.release_page_cache()
    assert memlog._kept_fds[str(path)] == fd


def test_release_skips_small_files_and_shm(volume, monkeypatch):
    monkeypatch.setattr(memlog, "_MIN_FILE_BYTES", 1024)
    (volume / "small.json").write_bytes(b"x" * 10)
    (volume / "big.pkl").write_bytes(b"x" * 4096)
    (volume / "x.db-shm").write_bytes(b"x" * 4096)
    out = memlog.release_page_cache()
    assert out["files"] == 1


def test_log_line_and_snapshot_have_the_volume(volume):
    (volume / "fills.db").write_bytes(b"x" * (2 * 1024 * 1024))
    line = memlog.log_line()
    assert line.startswith("memlog rss=") and "fills.db=2" in line and "up=" in line
    snap = memlog.snapshot()
    assert snap["volume"]["largest"]["fills.db"] == 2.0
    assert "process" in snap and "cgroup" in snap


def test_cgroup_v1_and_v2_readings(tmp_path, monkeypatch):
    real_exists = os.path.exists
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "memory.current").write_text(str(900 * 1024 * 1024))
    (v2 / "memory.stat").write_text(f"anon {500 * 1024 * 1024}\nfile {400 * 1024 * 1024}\ninactive_file 300\n")
    redirect = {"/sys/fs/cgroup/memory.current": str(v2 / "memory.current"),
                "/sys/fs/cgroup/memory.stat": str(v2 / "memory.stat")}
    import builtins
    real_open = builtins.open
    monkeypatch.setattr(os.path, "exists", lambda p: p in redirect or real_exists(p))
    monkeypatch.setattr(builtins, "open", lambda p, *a, **k: real_open(redirect.get(p, p), *a, **k))
    out = memlog.cgroup_stats()
    assert out["current"] == 900 and out["anon"] == 500 and out["file"] == 400


def test_release_heap_never_raises():
    assert memlog.release_heap() in ("jemalloc", "glibc", "none")


def test_trim_app_caches_drops_expired_view_answers(monkeypatch):
    import trader_profile as tp
    monkeypatch.setattr(tp, "_portfolio_cache", {"0xa": (time.time() - 10_000, {}), "0xb": (time.time(), {})})
    monkeypatch.setattr(tp, "_profile_cache", {"0xa": (time.time() - 10_000, {})})
    memlog.trim_app_caches()
    assert list(tp._portfolio_cache) == ["0xb"] and tp._profile_cache == {}


def test_run_forever_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("MEMLOG", "0")
    monkeypatch.setenv("CACHE_RELEASE", "0")
    calls = []
    monkeypatch.setattr(memlog, "release_page_cache", lambda: calls.append("release"))
    monkeypatch.setattr(memlog, "log_line", lambda: calls.append("log") or "")

    async def go():
        task = asyncio.create_task(memlog.run_forever())
        await asyncio.sleep(0.05)
        task.cancel()
    asyncio.run(go())
    assert calls == []


def test_cached_files_reports_page_cache_residency(volume):
    path = volume / "big.bin"
    with open(path, "wb") as f:
        f.write(os.urandom(4 << 20))
        f.flush()
        os.fsync(f.fileno())
    path.read_bytes()
    assert memlog.cached_files().get("big.bin", 0) >= 3.9
    memlog.release_page_cache()
    assert memlog.cached_files().get("big.bin", 0) < 1
