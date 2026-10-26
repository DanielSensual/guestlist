"""Files API: upload a proxy once (deduplicated by content hash), reference it by file_id."""

from __future__ import annotations

from pathlib import Path

from . import cache
from .client import client

DEFAULT_EXPIRY_DAYS = 7


def upload(path: str | Path, *, expires_days: int = DEFAULT_EXPIRY_DAYS) -> str:
    """Upload `path` with purpose=user_data and an expiry; return the file id. Re-uploads are skipped."""
    path = Path(path)
    sha = cache.sha256_file(path)
    hit = cache.get("files", sha)
    if hit:
        return hit["id"]
    with open(path, "rb") as f:
        fo = client().files.create(
            file=(path.name, f, "video/mp4" if path.suffix.lower() == ".mp4" else "application/octet-stream"),
            purpose="user_data",
            expires_after={"anchor": "created_at", "seconds": expires_days * 86400},
        )
    cache.put("files", sha, {"id": fo.id, "path": str(path), "bytes": getattr(fo, "bytes", None),
                             "expires_at": getattr(fo, "expires_at", None)})
    return fo.id


def delete(path: str | Path) -> bool:
    """Delete the uploaded copy of `path` (if any) and forget it."""
    sha = cache.sha256_file(path)
    hit = cache.get("files", sha)
    if not hit:
        return False
    client().files.delete(hit["id"])
    cache.drop("files", sha)
    return True
