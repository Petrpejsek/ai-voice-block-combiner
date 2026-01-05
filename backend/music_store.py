import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from werkzeug.utils import secure_filename


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def music_dir_for_episode(episode_dir: str) -> str:
    return os.path.join(episode_dir, "assets", "music")


def music_manifest_path_for_episode(episode_dir: str) -> str:
    return os.path.join(music_dir_for_episode(episode_dir), "music_manifest.json")


def _default_manifest() -> dict:
    return {
        "version": "music_manifest_v1",
        "updated_at": _now_iso(),
        "tracks": [],
    }


def load_music_manifest(episode_dir: str) -> dict:
    path = music_manifest_path_for_episode(episode_dir)
    if not os.path.exists(path):
        return _default_manifest()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_manifest()
        if not isinstance(data.get("tracks"), list):
            data["tracks"] = []
        if "version" not in data:
            data["version"] = "music_manifest_v1"
        if "updated_at" not in data:
            data["updated_at"] = _now_iso()
        return data
    except Exception:
        return _default_manifest()


def save_music_manifest(episode_dir: str, manifest: dict) -> None:
    os.makedirs(music_dir_for_episode(episode_dir), exist_ok=True)
    manifest = manifest or {}
    if "version" not in manifest:
        manifest["version"] = "music_manifest_v1"
    manifest["updated_at"] = _now_iso()
    path = music_manifest_path_for_episode(episode_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def probe_audio_duration_seconds(audio_path: str) -> Optional[float]:
    """
    Returns duration in seconds using ffprobe, or None if unknown.
    """
    if not audio_path or not os.path.exists(audio_path):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        val = (result.stdout or "").strip()
        if not val:
            return None
        return float(val)
    except Exception:
        return None


def _next_user_music_filename(existing_filenames: List[str], ext: str) -> str:
    """
    Generates user_music_XX.<ext>, where XX is 2-digit sequential, based on existing files.
    """
    ext = (ext or "").lower().lstrip(".")
    if ext not in ("mp3", "wav"):
        ext = "mp3"
    max_idx = 0
    for fn in existing_filenames or []:
        m = re.match(r"^user_music_(\d+)\.(mp3|wav)$", (fn or "").strip(), flags=re.IGNORECASE)
        if m:
            try:
                max_idx = max(max_idx, int(m.group(1)))
            except Exception:
                pass
    return f"user_music_{max_idx + 1:02d}.{ext}"


def add_music_files(
    episode_dir: str,
    incoming_files: List[Any],
) -> Tuple[List[dict], dict]:
    """
    Adds 1..N uploaded files into projects/<ep>/assets/music/ as user_music_XX.ext,
    and persists metadata into music_manifest.json.

    Returns: (added_tracks, updated_manifest)
    """
    manifest = load_music_manifest(episode_dir)
    tracks = manifest.get("tracks") or []
    if not isinstance(tracks, list):
        tracks = []

    existing_names = [t.get("filename") for t in tracks if isinstance(t, dict)]
    existing_names = [x for x in existing_names if isinstance(x, str)]

    os.makedirs(music_dir_for_episode(episode_dir), exist_ok=True)
    added: List[dict] = []

    for f in incoming_files or []:
        if not f:
            continue

        original_name = secure_filename(getattr(f, "filename", "") or "")
        if not original_name:
            continue

        _, ext = os.path.splitext(original_name)
        ext = (ext or "").lower().lstrip(".")
        if ext not in ("mp3", "wav"):
            # refuse silently; caller validates extensions, but keep safe
            continue

        new_name = _next_user_music_filename(existing_names, ext)
        existing_names.append(new_name)

        out_path = os.path.join(music_dir_for_episode(episode_dir), new_name)
        f.save(out_path)

        dur = probe_audio_duration_seconds(out_path)
        track = {
            "filename": new_name,
            "original_name": original_name,
            "duration_sec": round(float(dur), 2) if isinstance(dur, (int, float)) else None,
            "active": True,
            "tag": None,  # optional: neutral/dark/hopeful
            "uploaded_at": _now_iso(),
        }
        tracks.append(track)
        added.append(track)

    manifest["tracks"] = tracks
    save_music_manifest(episode_dir, manifest)
    return added, manifest


def update_music_track(
    episode_dir: str,
    filename: str,
    active: Optional[bool] = None,
    tag: Optional[str] = None,
) -> dict:
    """
    Updates a single track in music_manifest.json.
    """
    filename = secure_filename(filename or "")
    manifest = load_music_manifest(episode_dir)
    tracks = manifest.get("tracks") or []
    if not isinstance(tracks, list):
        tracks = []

    found = False
    for t in tracks:
        if not isinstance(t, dict):
            continue
        if secure_filename(t.get("filename") or "") != filename:
            continue
        if active is not None:
            t["active"] = bool(active)
        if tag is not None:
            tag_norm = (tag or "").strip().lower()
            if tag_norm in ("", "none", "null"):
                t["tag"] = None
            elif tag_norm in ("neutral", "dark", "hopeful"):
                t["tag"] = tag_norm
            else:
                # keep unknown tag as-is to be forward-compatible, but store trimmed string
                t["tag"] = tag_norm
        found = True
        break

    if not found:
        raise FileNotFoundError(f"Music track not found: {filename}")

    manifest["tracks"] = tracks
    save_music_manifest(episode_dir, manifest)
    return manifest




