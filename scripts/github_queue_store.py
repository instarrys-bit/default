"""Compatibility exports; durable JSON persistence is owned by storage.v2.queue_store."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from storage.v2.queue_store import (
    ALLOWED_STATE_PATHS,
    DEFAULT_QUEUE_PATH,
    ConcurrentUpdate,
    GitHubAPIError,
    GitHubContentsJsonStore,
    GitHubContentsQueueStore,
    QueueSnapshot,
    QueueStoreError,
)
__all__ = [
    "ALLOWED_STATE_PATHS", "DEFAULT_QUEUE_PATH", "ConcurrentUpdate",
    "GitHubAPIError", "GitHubContentsJsonStore", "GitHubContentsQueueStore",
    "QueueSnapshot", "QueueStoreError",
]
