"""
memlog.py
~~~~~~~~~

A memory log line every few minutes, and page-cache release for the volume's files.

Railway bills the container's cgroup memory, and that counts the kernel's page cache:
every page of fills.db, hyperlens.db, opportunities.db or the OHLCV pickle that was read
or written stays charged until the kernel is short of memory, which on a service without
a memory limit (a service with a volume cannot have one) is never. So the bill grew with
the files. Every CACHE_RELEASE_S (60 s: some jobs read hundreds of MB in a burst) the clean
cached pages of the volume's files (and of the
source files read at import) are dropped with posix_fadvise(DONTNEED): nothing on disk
changes and SQLite re-reads what it needs.

SQLite caveat: closing *any* descriptor of a database file releases the POSIX locks the
process holds on it, so the descriptors used here for main database files are opened once
and never closed. SQLite takes no locks on its -wal and -journal files, which can be
deleted and recreated, so those are opened and closed each time like any other file.

Log line (MEMLOG_INTERVAL_S, default 600 s), all figures in MB:
  memlog rss=.. anon=.. | cgroup=.. anon=.. file=.. | released=.. | heap=.. | volume=.. (largest files) | threads=.. up=..h
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_MB = 1024 * 1024
_START = time.time()
_SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")   # main database files (SQLite locks these)
_MIN_FILE_BYTES = 256 * 1024     # smaller files are not worth a syscall
_MAX_KEPT_FDS = 64
_MAX_DEPTH = 2

_kept_fds: Dict[str, int] = {}   # SQLite database path -> read-only fd, never closed (see module doc)
_import_files_done: set = set()
_last_release: Dict[str, float] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_on(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off")


def volume_dir() -> Optional[Path]:
    root = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or ("/data" if Path("/data").is_dir() else "")
    return Path(root) if root and Path(root).is_dir() else None


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------

def proc_status() -> Dict[str, float]:
    out: Dict[str, float] = {}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                key, _, val = line.partition(":")
                if key in ("VmRSS", "RssAnon", "RssFile", "RssShmem"):
                    out[key] = int(val.split()[0]) / 1024
                elif key == "Threads":
                    out[key] = int(val.split()[0])
    except OSError:
        pass
    return out


def _read_stat(path: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                out[parts[0]] = int(parts[1])
    return out


def cgroup_stats() -> Dict[str, float]:
    """The container's charged memory (what Railway's metric is built from), in MB."""
    try:
        if os.path.exists("/sys/fs/cgroup/memory.current"):          # cgroup v2
            st = _read_stat("/sys/fs/cgroup/memory.stat")
            out = {"current": int(open("/sys/fs/cgroup/memory.current").read()) / _MB}
            for key in ("anon", "file", "file_mapped", "file_dirty", "active_file", "inactive_file",
                        "shmem", "slab", "sock", "kernel"):
                if key in st:
                    out[key] = st[key] / _MB
            return out
        base = "/sys/fs/cgroup/memory"
        if os.path.exists(f"{base}/memory.usage_in_bytes"):           # cgroup v1
            st = _read_stat(f"{base}/memory.stat")
            out = {"current": int(open(f"{base}/memory.usage_in_bytes").read()) / _MB}
            pick = (lambda k: st.get(f"total_{k}", st.get(k)))
            for key, src in (("anon", "rss"), ("file", "cache"), ("file_mapped", "mapped_file"),
                             ("file_dirty", "dirty"), ("active_file", "active_file"),
                             ("inactive_file", "inactive_file"), ("shmem", "shmem")):
                v = pick(src)
                if v is not None:
                    out[key] = v / _MB
            return out
    except (OSError, ValueError):
        pass
    return {}


def volume_files(limit: int = 6) -> Dict[str, object]:
    root = volume_dir()
    if root is None:
        return {}
    sizes = []
    for path in _walk(root):
        try:
            sizes.append((path.stat().st_size, path))
        except OSError:
            continue
    sizes.sort(reverse=True)
    return {"total_mb": round(sum(s for s, _ in sizes) / _MB, 1),
            "largest": {str(p.relative_to(root)): round(s / _MB, 1) for s, p in sizes[:limit]}}


def _walk(root: Path, depth: int = 0):
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for e in entries:
        try:
            if e.is_file(follow_symlinks=False):
                yield Path(e.path)
            elif e.is_dir(follow_symlinks=False) and depth < _MAX_DEPTH:
                yield from _walk(Path(e.path), depth + 1)
        except OSError:
            continue


_libc = None


def _libc_calls():
    global _libc
    if _libc is None:
        lib = ctypes.CDLL(None, use_errno=True)
        lib.mmap.restype = ctypes.c_void_p
        lib.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
        lib.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
        _libc = lib
    return _libc


def _resident_mb(path: Path) -> Optional[float]:
    """MB of the file in the page cache (mincore over a read-only mapping; nothing is read)."""
    import mmap
    try:
        size = path.stat().st_size
        if size == 0:
            return 0.0
        key = str(path)
        fd = _kept_fds.get(key) if _is_sqlite(path) else None
        own = fd is None
        if own:
            if _is_sqlite(path):
                return None              # only through a kept descriptor (closing one drops locks)
            fd = os.open(key, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            lib = _libc_calls()
            addr = lib.mmap(None, size, mmap.PROT_READ, mmap.MAP_SHARED, fd, 0)
            if addr in (None, ctypes.c_void_p(-1).value):
                return None
            try:
                pages = (size + mmap.PAGESIZE - 1) // mmap.PAGESIZE
                vec = ctypes.create_string_buffer(pages)
                if lib.mincore(addr, size, vec) != 0:
                    return None
                return sum(b & 1 for b in vec.raw) * mmap.PAGESIZE / _MB
            finally:
                lib.munmap(addr, size)
        finally:
            if own:
                os.close(fd)
    except Exception:            # noqa: BLE001 - diagnostics only
        return None


def cached_files(limit: int = 6) -> Dict[str, float]:
    """The volume files with the most pages in the page cache, MB."""
    root = volume_dir()
    if root is None:
        return {}
    out = []
    for path in _walk(root):
        mb = _resident_mb(path)
        if mb:
            out.append((mb, str(path.relative_to(root))))
    out.sort(reverse=True)
    return {name: round(mb, 1) for mb, name in out[:limit]}


# ---------------------------------------------------------------------------
# Allocator (jemalloc is preloaded in the Docker image)
# ---------------------------------------------------------------------------

_je = None
_je_checked = False


def _jemalloc():
    global _je, _je_checked
    if _je_checked:
        return _je
    _je_checked = True
    try:
        with open("/proc/self/maps") as f:
            path = next((line.split()[-1] for line in f if "libjemalloc" in line), None)
        if path:
            lib = ctypes.CDLL(path)
            lib.mallctl.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                    ctypes.c_void_p, ctypes.c_size_t]
            lib.mallctl.restype = ctypes.c_int
            _je = lib
    except Exception as exc:          # noqa: BLE001 - diagnostics only
        logger.debug("jemalloc not available: %s", exc)
    return _je


def heap_stats() -> Dict[str, float]:
    """jemalloc's allocated / resident / retained bytes, MB (empty under glibc)."""
    je = _jemalloc()
    if je is None:
        return {}
    try:
        epoch = ctypes.c_uint64(1)
        sz = ctypes.c_size_t(ctypes.sizeof(epoch))
        je.mallctl(b"epoch", ctypes.byref(epoch), ctypes.byref(sz), ctypes.byref(epoch), sz)
        out = {}
        for name in ("allocated", "active", "resident", "retained"):
            val = ctypes.c_size_t(0)
            sz = ctypes.c_size_t(ctypes.sizeof(val))
            if je.mallctl(f"stats.{name}".encode(), ctypes.byref(val), ctypes.byref(sz), None, 0) == 0:
                out[name] = val.value / _MB
        return out
    except Exception:                 # noqa: BLE001
        return {}


def release_heap() -> str:
    """Give freed heap pages back to the OS: a jemalloc purge, or glibc malloc_trim without it."""
    je = _jemalloc()
    try:
        if je is not None:
            je.mallctl(b"arena.4096.purge", None, None, None, 0)    # 4096 = all arenas
            return "jemalloc"
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        return "glibc"
    except Exception as exc:          # noqa: BLE001
        logger.debug("heap release unavailable: %s", exc)
        return "none"


# ---------------------------------------------------------------------------
# Page-cache release
# ---------------------------------------------------------------------------

def _is_sqlite(path: Path) -> bool:
    return path.name.endswith(_SQLITE_SUFFIXES)


def _drop(path: Path) -> bool:
    """posix_fadvise(DONTNEED) on one file. Returns True when the hint was given."""
    key = str(path)
    try:
        if _is_sqlite(path):
            fd = _kept_fds.get(key)
            if fd is not None:
                try:
                    if os.fstat(fd).st_ino != os.stat(key).st_ino:
                        fd = None          # replaced database: open the new one, leave the old fd open
                except FileNotFoundError:
                    # Deleted: no other process can open it, so no lock that matters goes with it.
                    os.close(_kept_fds.pop(key))
                    return False
                except OSError:
                    return False
            if fd is None:
                if len(_kept_fds) >= _MAX_KEPT_FDS:
                    return False
                fd = os.open(key, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
                _kept_fds[key] = fd
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            return True
        fd = os.open(key, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)
        return True
    except (OSError, AttributeError):
        return False


def drop_file_cache(path) -> bool:
    """For writers: drop one file's cached pages right after writing it (not for SQLite files)."""
    p = Path(path)
    return False if _is_sqlite(p) else _drop(p)


def _import_files():
    """Source and bytecode files read at import: read once, then cached for the process life."""
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if not f or f in _import_files_done:
            continue
        _import_files_done.add(f)
        yield Path(f)
        cached = getattr(getattr(mod, "__spec__", None), "cached", None)
        if cached:
            yield Path(cached)


def release_page_cache() -> Dict[str, float]:
    """Drop clean cached pages of the volume's files and of newly imported modules."""
    before = cgroup_stats().get("file")
    files = 0
    root = volume_dir()
    if root is not None:
        for path in _walk(root):
            if path.name.endswith("-shm"):
                continue                     # memory-mapped by SQLite; the hint does not apply
            try:
                if path.stat().st_size < _MIN_FILE_BYTES:
                    continue
            except OSError:
                continue
            files += _drop(path)
    for path in _import_files():
        if path.suffix in (".py", ".pyc"):
            _drop(path)
    after = cgroup_stats().get("file")
    out = {"files": files, "at": time.time()}
    if before is not None and after is not None:
        out["released_mb"] = round(max(0.0, before - after), 1)
    _last_release.clear()
    _last_release.update(out)
    return out


def trim_app_caches() -> None:
    """Expired entries of the view caches, which otherwise wait for their next use or a size cap.
    Runs on the event loop (the caches are used there); only modules already imported."""
    for mod_name, fn_name in (("trader_profile", "trim_caches"), ("trader_entries", "_prune")):
        fn = getattr(sys.modules.get(mod_name), fn_name, None)
        if fn is not None:
            try:
                fn()
            except Exception as exc:      # noqa: BLE001
                logger.debug("memlog: %s.%s failed: %s", mod_name, fn_name, exc)


# ---------------------------------------------------------------------------
# Report and loop
# ---------------------------------------------------------------------------

def snapshot() -> Dict[str, object]:
    """Everything the log line shows, for /api/admin/memory-snapshot."""
    return {
        "process": proc_status(),
        "cgroup": cgroup_stats(),
        "heap": heap_stats(),
        "volume": volume_files(),
        "cached": cached_files(),
        "last_release": dict(_last_release),
        "kept_fds": len(_kept_fds),
        "uptime_h": round((time.time() - _START) / 3600, 2),
    }


def _fmt(v) -> str:
    return "-" if v is None else f"{v:.0f}"


def log_line() -> str:
    p, c, h = proc_status(), cgroup_stats(), heap_stats()
    vol = volume_files(limit=4)
    parts = [f"memlog rss={_fmt(p.get('VmRSS'))} anon={_fmt(p.get('RssAnon'))}"]
    if c:
        parts.append(f"cgroup={_fmt(c.get('current'))} anon={_fmt(c.get('anon'))} file={_fmt(c.get('file'))}"
                     f" (active {_fmt(c.get('active_file'))}, inactive {_fmt(c.get('inactive_file'))},"
                     f" mapped {_fmt(c.get('file_mapped'))})")
    if _last_release:
        parts.append(f"released={_fmt(_last_release.get('released_mb'))} in {int(_last_release.get('files', 0))} files")
    if h:
        parts.append(f"heap allocated={_fmt(h.get('allocated'))} resident={_fmt(h.get('resident'))}"
                     f" retained={_fmt(h.get('retained'))}")
    if vol:
        largest = " ".join(f"{k}={v:.0f}" for k, v in vol["largest"].items())
        parts.append(f"volume={vol['total_mb']:.0f} ({largest})")
    hot = cached_files(limit=3)
    if hot:
        parts.append("cached " + " ".join(f"{k}={v:.0f}" for k, v in hot.items()))
    parts.append(f"threads={int(p.get('Threads', 0))} up={(time.time() - _START) / 3600:.1f}h")
    return " | ".join(parts)


_pool = None


async def _off_loop(fn):
    """Run on memlog's own thread: the shared default pool (IO_WORKERS) can be busy with long
    jobs for minutes, which would delay the release and the log line."""
    global _pool
    if _pool is None:
        import concurrent.futures
        _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="memlog")
    return await asyncio.get_running_loop().run_in_executor(_pool, fn)


async def run_forever() -> None:
    """Every CACHE_RELEASE_S (default 60): trim the view caches and drop the volume's page cache;
    every MEMLOG_INTERVAL_S (default 600): one log line. MEMLOG=0 / CACHE_RELEASE=0 turn either off."""
    release = _env_on("CACHE_RELEASE")
    every = _env_int("CACHE_RELEASE_S", 60) or 60
    log_every = _env_int("MEMLOG_INTERVAL_S", 600) if _env_on("MEMLOG") else 0
    next_pass = time.time() + 60             # first pass once startup reads are done
    next_log = time.time() + 90
    while True:
        try:
            now = time.time()
            if now >= next_pass:
                trim_app_caches()
                if release:
                    await _off_loop(release_page_cache)
                next_pass = now + every
            if log_every and now >= next_log:
                logger.info(await _off_loop(log_line))
                next_log = now + log_every
        except asyncio.CancelledError:
            raise
        except Exception as exc:     # noqa: BLE001 - the log must never take the app down
            logger.warning("memlog: %s", exc)
        await asyncio.sleep(30)
