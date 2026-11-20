"""Compatibility exports; load queue store without requiring local storage/ package."""
from __future__ import annotations

import importlib.util
import sys
import urllib.request
from pathlib import Path

_CACHE = Path(__file__).with_name("queue_store_impl.py")


def _ensure_impl() -> object:
    if not _CACHE.is_file():
        url = (
            "https://raw.githubusercontent.com/instarrys-bit/default/main/"
            "storage/v2/queue_store.py"
        )
        try:
            body = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise ImportError(
                "queue_store_impl.py missing and failed to fetch storage.v2.queue_store: "
                f"{exc}"
            ) from exc
        _CACHE.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("queue_store_impl", _CACHE)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load queue_store_impl")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["queue_store_impl"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _ensure_impl()
ALLOWED_STATE_PATHS = _mod.ALLOWED_STATE_PATHS
DEFAULT_QUEUE_PATH = _mod.DEFAULT_QUEUE_PATH
ConcurrentUpdate = _mod.ConcurrentUpdate
GitHubAPIError = _mod.GitHubAPIError
GitHubContentsJsonStore = _mod.GitHubContentsJsonStore
GitHubContentsQueueStore = _mod.GitHubContentsQueueStore
QueueSnapshot = _mod.QueueSnapshot
QueueStoreError = _mod.QueueStoreError

__all__ = [
    "ALLOWED_STATE_PATHS",
    "DEFAULT_QUEUE_PATH",
    "ConcurrentUpdate",
    "GitHubAPIError",
    "GitHubContentsJsonStore",
    "GitHubContentsQueueStore",
    "QueueSnapshot",
    "QueueStoreError",
]
