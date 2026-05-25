import os
import shutil
import tempfile
from typing import Optional

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BACKEND_DIR, "data", "uploads")


def ensure_uploads_dir() -> str:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    return UPLOADS_DIR


def persist_upload(file_id: str, source_path: str) -> str:
    """Copy uploaded h5ad into durable storage; return final path."""
    ensure_uploads_dir()
    dest = os.path.join(UPLOADS_DIR, f"{file_id}.h5ad")
    shutil.copy2(source_path, dest)
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
