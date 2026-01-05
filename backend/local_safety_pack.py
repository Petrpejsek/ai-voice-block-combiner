"""
Local Public Domain Safety Pack

Purpose:
- Last-resort visuals to guarantee the pipeline always completes (AAR/CB never fail due to 0 results).
- Assets are local files (images/video textures) bundled on disk.

Default implementation:
- Uses the repo-level `images/` directory as the safety pack source.
  (This repo already contains a set of PNG images.)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_pack_dirs() -> List[Path]:
    root = _repo_root()
    # Primary: repo/images (already present)
    return [
        root / "images",
        root / "uploads" / "safety_pack",
        root / "uploads" / "safety_pack" / "images",
    ]


def list_safety_pack_files() -> List[Path]:
    files: List[Path] = []
    for d in _safe_pack_dirs():
        try:
            if not d.exists() or not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"):
                    files.append(p)
        except Exception:
            continue
    # De-dupe
    uniq: List[Path] = []
    seen = set()
    for p in files:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def _stable_pick(items: List[Path], seed: str) -> Optional[Path]:
    if not items:
        return None
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(items)
    return items[idx]


def make_local_fallback_asset(
    *,
    scene_id: str,
    block_id: str,
    reason: str = "AAR_EMPTY_RESULTS",
) -> Optional[Dict[str, Any]]:
    """
    Returns a manifest asset dict that CB can render without network:
    - local_path is an absolute filesystem path
    - source="local_safety_pack"
    - is_fallback=true
    """
    files = list_safety_pack_files()
    if not files:
        return None

    seed = f"{scene_id}::{block_id}"
    chosen = _stable_pick(files, seed=seed)
    if not chosen:
        return None

    p = chosen.resolve()
    media_type = "image" if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else "video"
    archive_item_id = f"local_safety_pack:{p.name}"

    return {
        "archive_item_id": archive_item_id,
        "asset_url": str(p),  # local path string (CB special-cases local_path)
        "local_path": str(p),
        "media_type": media_type,
        "title": f"Local safety pack ({p.name})",
        "priority": 99,
        "pool_priority": "fallback",
        "source": "local_safety_pack",
        "is_fallback": True,
        "reason": reason,
    }




