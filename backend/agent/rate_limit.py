"""
Simple global throttle for LLM API calls.

Set GEMINI_MAX_RPM to cap requests per minute across the process (default 0 =
unlimited). Used to respect provider rate limits during batch/ablation runs.
"""

from __future__ import annotations

import os
import time
import threading

_lock = threading.Lock()
_last_call = [0.0]


def throttle() -> None:
    """Block until at least (60 / GEMINI_MAX_RPM) seconds have passed since the
    previous throttled call. No-op when GEMINI_MAX_RPM is unset or <= 0."""
    try:
        rpm = float(os.getenv("GEMINI_MAX_RPM", "0") or 0)
    except ValueError:
        rpm = 0.0
    if rpm <= 0:
        return
    min_interval = 60.0 / rpm
    with _lock:
        now = time.monotonic()
        wait = _last_call[0] + min_interval - now
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
