import time

_adata_cache = {}
CACHE_TTL_SECONDS = 3600
MAX_CACHE_SIZE = 3


def cache_adata(file_id: str, adata) -> None:
    now = time.time()

    # Remove expired entries
    expired = [
        k for k, v in _adata_cache.items()
        if now - v["timestamp"] > CACHE_TTL_SECONDS
    ]
    for k in expired:
        del _adata_cache[k]

    # Evict oldest if over limit
    if len(_adata_cache) >= MAX_CACHE_SIZE:
        oldest = min(_adata_cache, key=lambda k: _adata_cache[k]["timestamp"])
        del _adata_cache[oldest]

    _adata_cache[file_id] = {
        "adata": adata,
        "timestamp": now
    }


def get_adata(file_id: str):
    entry = _adata_cache.get(file_id)

    if not entry:
        return None

    if time.time() - entry["timestamp"] > CACHE_TTL_SECONDS:
        del _adata_cache[file_id]
        return None

    entry["timestamp"] = time.time()
    return entry["adata"]