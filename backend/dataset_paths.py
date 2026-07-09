import os
import shutil
import tempfile
from typing import Optional

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# Uploads can be large (GB-scale .h5ad). Allow pointing them at a roomy drive via
# SENESCENCE_UPLOADS_DIR (e.g. D:\senescence_uploads) so they don't fill C:.
UPLOADS_DIR = os.environ.get("SENESCENCE_UPLOADS_DIR") or os.path.join(
    BACKEND_DIR, "data", "uploads"
)


def ensure_uploads_dir() -> str:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    return UPLOADS_DIR


def persist_upload(file_id: str, source_path: str) -> str:
    """Move uploaded h5ad into durable storage; return final path.

    Uses move (not copy) so we never need 2x the file size on disk. shutil.move
    renames within the same drive (instant, no extra space) and falls back to
    copy+delete only across drives."""
    ensure_uploads_dir()
    dest = os.path.join(UPLOADS_DIR, f"{file_id}.h5ad")
    if os.path.exists(dest):
        os.remove(dest)
    shutil.move(source_path, dest)
    return dest


def resolve_dataset_path(file_id: str) -> Optional[str]:
    """Uploaded file path (persistent), then legacy temp path."""
    persistent = os.path.join(UPLOADS_DIR, f"{file_id}.h5ad")
    if os.path.exists(persistent):
        return persistent

    temp_path = os.path.join(tempfile.gettempdir(), f"{file_id}.h5ad")
    if os.path.exists(temp_path):
        return temp_path

    return None
