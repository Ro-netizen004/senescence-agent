"""Lightweight, dependency-free text matching used by routing.

Kept free of scanpy/matplotlib so the intent router (pure Python) can resolve
cell-type names without importing the heavy analysis stack.
"""

import re
from typing import Optional

# Words that don't distinguish one cell type from another.
_GENERIC_TOKENS = {"cell", "cells", "of", "the", "a", "an"}


def resolve_cell_type(requested: str, available: list) -> Optional[str]:
    """Resolve a user-typed cell-type name to an exact value in ``available``,
    tolerating case and simple singular/plural differences. Returns None if no
    match."""
    req = str(requested).strip()
    if req in available:
        return req

    lower_map = {str(a).lower(): a for a in available}
    key = req.lower()
    if key in lower_map:
        return lower_map[key]

    if key.endswith("s") and key[:-1] in lower_map:
        return lower_map[key[:-1]]
    if key + "s" in lower_map:
        return lower_map[key + "s"]

    # Token-subset match: the query's distinctive words all appear in exactly one
    # available type (e.g. "fibroblast" / "fibroblast cells" -> "fibroblast of
    # cardiac tissue"). Ambiguous queries (e.g. "cell") match nothing.
    req_tokens = {t for t in re.findall(r"[a-z0-9]+", key) if t not in _GENERIC_TOKENS}
    if req_tokens:
        matches = [
            a for a in available
            if req_tokens <= set(re.findall(r"[a-z0-9]+", str(a).lower()))
        ]
        if len(matches) == 1:
            return matches[0]

    return None
