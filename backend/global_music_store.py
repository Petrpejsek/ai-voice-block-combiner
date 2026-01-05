"""
Global Music Library Store - Sdílená knihovna podkresové hudby pro všechny projekty.

Source of truth:
  podcasts/uploads/global_music/music_manifest.json
  podcasts/uploads/global_music/<music_files>
"""

import json
import os
import random
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from werkzeug.utils import secure_filename


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def global_music_dir() -> str:
    """
    Absolutní cesta ke globální music library.
    DŮLEŽITÉ: používáme `uploads/global_music/` (viz projektová struktura).
    """
    base = os.path.join(os.path.dirname(__file__), "..", "uploads", "global_music")
    return os.path.abspath(base)


def global_music_manifest_path() -> str:
    return os.path.join(global_music_dir(), "music_manifest.json")


def load_global_music_manifest() -> Dict[str, Any]:
    """Načte global music manifest (vytvoří prázdný, pokud chybí)."""
    path = global_music_manifest_path()
    if not os.path.exists(path):
        return {"version": "global_music_manifest_v1", "updated_at": _now_iso(), "tracks": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": "global_music_manifest_v1", "updated_at": _now_iso(), "tracks": []}
        if "version" not in data:
            data["version"] = "global_music_manifest_v1"
        if "tracks" not in data or not isinstance(data.get("tracks"), list):
            data["tracks"] = []
        return data
    except Exception:
        return {"version": "global_music_manifest_v1", "updated_at": _now_iso(), "tracks": []}


def save_global_music_manifest(manifest: Dict[str, Any]) -> None:
    """Uloží global music manifest."""
    os.makedirs(global_music_dir(), exist_ok=True)
    if "version" not in manifest:
        manifest["version"] = "global_music_manifest_v1"
    manifest["updated_at"] = _now_iso()
    path = global_music_manifest_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _probe_audio_duration(filepath: str) -> float:
    """Probe audio duration using ffprobe."""
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return float((r.stdout or "").strip())
    except Exception:
        pass
    return 0.0


def _size_mb(filepath: str) -> float:
    try:
        return round(os.path.getsize(filepath) / (1024 * 1024), 2)
    except Exception:
        return 0.0


def _next_music_filename(existing_filenames: List[str], original_name: str) -> str:
    """
    Generates music_XXX_<sanitized>.<ext>
    """
    original = (original_name or "").strip()
    ext = "mp3"
    m = re.search(r"\.(mp3|wav)$", original, flags=re.IGNORECASE)
    if m:
        ext = m.group(1).lower()
    base = re.sub(r"\.(mp3|wav)$", "", original, flags=re.IGNORECASE).strip() or "track"
    base_safe = secure_filename(base)[:40] or "track"

    max_idx = 0
    for fn in existing_filenames or []:
        mm = re.match(r"^music_(\d+)_.*\.(mp3|wav)$", (fn or "").strip(), flags=re.IGNORECASE)
        if mm:
            try:
                max_idx = max(max_idx, int(mm.group(1)))
            except Exception:
                pass
    return f"music_{max_idx + 1:03d}_{base_safe}.{ext}"


def add_global_music_files(files: List[Any], tags: Optional[List[str]] = None, mood: str = "neutral") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Přidá 1..N uploaded files do globální music library.
    Vrací: (added_tracks, updated_manifest)
    """
    os.makedirs(global_music_dir(), exist_ok=True)
    manifest = load_global_music_manifest()
    tracks = manifest.get("tracks") if isinstance(manifest.get("tracks"), list) else []

    existing_names = [t.get("filename") for t in tracks if isinstance(t, dict) and t.get("filename")]

    added: List[Dict[str, Any]] = []
    for f in files or []:
        if not f:
            continue
        original_name = getattr(f, "filename", "") or ""
        new_name = _next_music_filename(existing_names, original_name)
        out_path = os.path.join(global_music_dir(), new_name)

        f.save(out_path)
        dur = _probe_audio_duration(out_path)
        track = {
            "filename": new_name,
            "original_name": original_name,
            "duration_sec": round(dur, 2) if dur else 0.0,
            "size_mb": _size_mb(out_path),
            "active": True,
            "tags": [str(x).strip() for x in (tags or []) if str(x).strip()],
            "mood": (mood or "neutral").strip() or "neutral",
            "uploaded_at": _now_iso(),
            "usage_count": 0,
        }
        tracks.append(track)
        existing_names.append(new_name)
        added.append(track)

    manifest["tracks"] = tracks
    save_global_music_manifest(manifest)
    return added, manifest


def update_global_music_track(
    filename: str,
    active: Optional[bool] = None,
    tag: Optional[str] = None,  # legacy (single tag)
    mood: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update global music track metadata. Returns updated manifest."""
    safe = secure_filename(filename or "")
    if not safe:
        raise FileNotFoundError("Invalid filename")

    manifest = load_global_music_manifest()
    tracks = manifest.get("tracks") if isinstance(manifest.get("tracks"), list) else []

    updated = False
    for t in tracks:
        if not isinstance(t, dict):
            continue
        if secure_filename(t.get("filename") or "") != safe:
            continue
        if active is not None:
            t["active"] = bool(active)
        if mood is not None:
            t["mood"] = (str(mood).strip() or "neutral")
        if tags is not None:
            t["tags"] = [str(x).strip() for x in (tags or []) if str(x).strip()]
        if tag is not None:
            t["tag"] = (str(tag).strip() or None)
        updated = True
        break

    if not updated:
        raise FileNotFoundError(f"Track not found: {safe}")

    manifest["tracks"] = tracks
    save_global_music_manifest(manifest)
    return manifest


def delete_global_music_track(filename: str) -> Dict[str, Any]:
    """Delete global music track (soubor + metadata). Returns updated manifest."""
    safe = secure_filename(filename or "")
    if not safe:
        raise FileNotFoundError("Invalid filename")

    manifest = load_global_music_manifest()
    tracks = manifest.get("tracks") if isinstance(manifest.get("tracks"), list) else []
    new_tracks = [t for t in tracks if not (isinstance(t, dict) and secure_filename(t.get("filename") or "") == safe)]
    if len(new_tracks) == len(tracks):
        raise FileNotFoundError(f"Track not found: {safe}")

    file_path = os.path.join(global_music_dir(), safe)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass

    manifest["tracks"] = new_tracks
    save_global_music_manifest(manifest)
    return manifest


def get_music_file_path(filename: str) -> Optional[str]:
    """Vrací absolutní cestu k music souboru z global library."""
    safe = secure_filename(filename or "")
    if not safe:
        return None
    path = os.path.join(global_music_dir(), safe)
    return path if os.path.exists(path) else None


def select_music_auto(
    context: Optional[dict] = None,
    preferred_mood: Optional[str] = None,
    preferred_tags: Optional[List[str]] = None,
    min_duration_sec: Optional[float] = None,
) -> Optional[dict]:
    """
    Automatický výběr hudby.
    - Pokud `preferred_tags` nevyhoví žádný track (např. tracky nemají tagy), automaticky uvolní filtr a vybere aspoň dle mood / fallback.
    """
    manifest = load_global_music_manifest()
    tracks = [t for t in (manifest.get("tracks") or []) if isinstance(t, dict)]
    if not tracks:
        return None

    pref_mood = (preferred_mood or "").strip().lower() or None
    pref_tags = [str(x).strip().lower() for x in (preferred_tags or []) if str(x).strip()]

    # Only active + existing files
    def _exists_track(t: dict) -> bool:
        fn = secure_filename(t.get("filename") or "")
        return bool(fn) and (get_music_file_path(fn) is not None)

    active_tracks = [t for t in tracks if t.get("active") is True and _exists_track(t)]
    if not active_tracks:
        # fallback: allow inactive if nothing else (better than silence)
        active_tracks = [t for t in tracks if _exists_track(t)]
    if not active_tracks:
        return None

    def _duration_ok(t: dict) -> bool:
        if min_duration_sec is None:
            return True
        try:
            return float(t.get("duration_sec") or 0) >= float(min_duration_sec)
        except Exception:
            return True

    cand = [t for t in active_tracks if _duration_ok(t)]
    if not cand:
        cand = active_tracks[:]

    def _tags_match(t: dict) -> bool:
        if not pref_tags:
            return True
        tags = t.get("tags") if isinstance(t.get("tags"), list) else []
        tags_norm = {str(x).strip().lower() for x in tags if str(x).strip()}
        return bool(tags_norm.intersection(pref_tags))

    cand_tagged = [t for t in cand if _tags_match(t)]
    # IMPORTANT: if tags filter yields nothing, relax it (avoid "no music" just because tags are empty)
    pool = cand_tagged if cand_tagged else cand

    def _score(t: dict) -> float:
        score = 0.0
        mood = (str(t.get("mood") or "").strip().lower() or "neutral")
        if pref_mood:
            if mood == pref_mood:
                score += 10.0
            elif mood == "neutral":
                score += 4.0
        else:
            if mood == "neutral":
                score += 2.0

        # Prefer some reasonable durations for short videos (optional heuristic)
        try:
            d = float(t.get("duration_sec") or 0)
            if 60 <= d <= 240:
                score += 2.0
        except Exception:
            pass

        # Slight random jitter to avoid picking same track forever if same score
        score += random.random() * 0.01
        return score

    pool.sort(key=_score, reverse=True)
    return pool[0] if pool else None

