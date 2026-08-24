"""Simple file-backed cache for external API responses.

Uses `shelve` to store timestamped entries per cache name.
Provides get/set with TTL semantics.
"""
from pathlib import Path
import shelve
import time
from typing import Any, Optional


CACHE_DIR = Path.cwd() / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(name: str) -> str:
    return str(CACHE_DIR / f"{name}.db")


def cache_get(name: str, key: str, ttl: int) -> Optional[Any]:
    path = _cache_path(name)
    try:
        with shelve.open(path) as db:
            entry = db.get(key)
            if not entry:
                return None
            ts, value = entry
            if (time.time() - ts) <= ttl:
                return value
            # expired
            try:
                del db[key]
            except Exception:
                pass
            return None
    except Exception:
        return None


def cache_set(name: str, key: str, value: Any) -> None:
    path = _cache_path(name)
    try:
        with shelve.open(path) as db:
            db[key] = (time.time(), value)
    except Exception:
        # best-effort, ignore cache failures
        return
