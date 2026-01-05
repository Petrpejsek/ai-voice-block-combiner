"""
Asset quality heuristics (no heavy deps).

Goal:
- Detect obvious "bad" visuals: black frames, screen recordings / UI bars, subtitle-like overlays.
- Keep dependencies minimal: ffmpeg/ffprobe (external), Pillow + numpy (already in requirements).

This is intentionally heuristic (fast + robust) and should be treated as a gate, not as a perfect classifier.
"""

from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class MediaInfo:
    duration_sec: Optional[float]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    has_video: bool


def probe_media_info(path: str, timeout_s: int = 10) -> MediaInfo:
    """
    Best-effort ffprobe for duration + video stream info.
    Returns MediaInfo(has_video=False) on failures.
    """
    if not path:
        return MediaInfo(None, None, None, None, False)
    try:
        # JSON output keeps parsing stable across ffprobe versions.
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_entries",
                "format=duration:stream=index,codec_type,width,height,avg_frame_rate",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if r.returncode != 0 or not (r.stdout or "").strip():
            return MediaInfo(None, None, None, None, False)
        import json

        data = json.loads(r.stdout)
        duration = None
        try:
            duration = float(((data.get("format") or {}).get("duration") or "").strip() or 0) or None
        except Exception:
            duration = None

        width = height = None
        fps = None
        has_video = False
        for s in (data.get("streams") or []):
            if (s or {}).get("codec_type") != "video":
                continue
            has_video = True
            width = int(s.get("width")) if s.get("width") is not None else None
            height = int(s.get("height")) if s.get("height") is not None else None
            afr = (s.get("avg_frame_rate") or "").strip()
            if afr and afr != "0/0" and "/" in afr:
                try:
                    num, den = afr.split("/", 1)
                    num_f = float(num)
                    den_f = float(den)
                    if den_f > 0:
                        fps = num_f / den_f
                except Exception:
                    pass
            break
        return MediaInfo(duration, width, height, fps, has_video)
    except Exception:
        return MediaInfo(None, None, None, None, False)


def _ffmpeg_extract_frame_png(path: str, t_sec: float, scale_w: int = 320, timeout_s: int = 15) -> Optional[Image.Image]:
    """
    Extract a single frame as PNG over stdout and load it with PIL.
    """
    if not path:
        return None
    try:
        # -ss before -i (fast seek); good enough for sampling.
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(max(0.0, float(t_sec))),
            "-i",
            path,
            "-frames:v",
            "1",
            "-vf",
            f"scale={int(scale_w)}:-1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
        if r.returncode != 0 or not r.stdout:
            return None
        img = Image.open(io.BytesIO(r.stdout))
        img.load()
        return img.convert("RGB")
    except Exception:
        return None


def _to_gray_np(img: Image.Image) -> np.ndarray:
    a = np.asarray(img, dtype=np.float32)
    # RGB -> luma
    return (0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]).astype(np.float32)


def _edge_density(gray: np.ndarray, thresh: float = 18.0) -> float:
    """
    Cheap edge proxy: mean(|dx| + |dy| > thresh).
    thresh is in [0..255] scale.
    """
    if gray.ndim != 2 or gray.size == 0:
        return 0.0
    dx = np.abs(gray[:, 1:] - gray[:, :-1])
    dy = np.abs(gray[1:, :] - gray[:-1, :])
    # align shapes
    m = np.minimum(dx[:-1, :], dy[:, :-1])  # shape (h-1,w-1)
    e = (dx[:-1, :] + dy[:, :-1])  # shape (h-1,w-1)
    # Use e only; m is computed to keep shapes consistent (and reduce artifacts).
    return float(np.mean(e > float(thresh)))


def _red_ratio_bottom_strip(img: Image.Image, strip_frac: float = 0.08) -> float:
    a = np.asarray(img, dtype=np.uint8)
    h = a.shape[0]
    y0 = int(max(0, h - int(h * strip_frac)))
    strip = a[y0:, :, :]
    if strip.size == 0:
        return 0.0
    r = strip[:, :, 0].astype(np.int16)
    g = strip[:, :, 1].astype(np.int16)
    b = strip[:, :, 2].astype(np.int16)
    # crude "youtube-like red bar" pixels
    red = (r > 180) & (g < 110) & (b < 110)
    return float(np.mean(red))


def analyze_frame(img: Image.Image) -> Dict[str, Any]:
    """
    Returns frame-level metrics.
    """
    gray = _to_gray_np(img)
    h, w = gray.shape[:2]
    mean_luma = float(np.mean(gray)) if gray.size else 0.0
    p_dark = float(np.mean(gray < 16.0)) if gray.size else 1.0

    # regions
    bot_h = max(1, int(h * 0.25))
    top_h = max(1, int(h * 0.15))
    bottom = gray[h - bot_h :, :]
    top = gray[:top_h, :]

    edge_all = _edge_density(gray)
    edge_bottom = _edge_density(bottom)
    edge_top = _edge_density(top)
    red_bottom = _red_ratio_bottom_strip(img)

    return {
        "w": int(w),
        "h": int(h),
        "mean_luma": round(mean_luma, 2),
        "p_dark": round(p_dark, 4),
        "edge_density": round(edge_all, 4),
        "edge_bottom": round(edge_bottom, 4),
        "edge_top": round(edge_top, 4),
        "red_ratio_bottom": round(red_bottom, 5),
    }


def classify_frame(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Heuristic labels for a single frame.
    """
    mean_luma = float(metrics.get("mean_luma", 0) or 0)
    p_dark = float(metrics.get("p_dark", 1) or 1)
    edge_bottom = float(metrics.get("edge_bottom", 0) or 0)
    edge_top = float(metrics.get("edge_top", 0) or 0)
    red_ratio_bottom = float(metrics.get("red_ratio_bottom", 0) or 0)

    is_blackish = (mean_luma < 18.0 and p_dark > 0.85) or (p_dark > 0.93)
    # Subtitle/UI heuristic: lots of edges confined to bottom band (common for captions)
    has_caption_like_overlay = edge_bottom > 0.18 and mean_luma > 25.0
    has_ui_like_bars = edge_top > 0.16 and mean_luma > 25.0
    looks_like_youtube_ui = red_ratio_bottom > 0.003

    return {
        "is_blackish": bool(is_blackish),
        "caption_like_overlay": bool(has_caption_like_overlay),
        "ui_like_bars": bool(has_ui_like_bars),
        "youtube_like_ui": bool(looks_like_youtube_ui),
    }


def sample_and_classify(
    path: str,
    t_sec: float,
    scale_w: int = 320,
    timeout_s: int = 15,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    img = _ffmpeg_extract_frame_png(path, t_sec=t_sec, scale_w=scale_w, timeout_s=timeout_s)
    if img is None:
        return None, None
    m = analyze_frame(img)
    c = classify_frame(m)
    return m, c


def should_reject_media(
    path: str,
    media_type: str,
    *,
    min_width: int = 960,
    min_height: int = 540,
    sample_times_sec: Optional[Tuple[float, ...]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Returns (reject, report).
    - For images: only frame heuristics apply (no duration probing needed).
    - For videos: uses ffprobe + a few sampled frames.
    """
    report: Dict[str, Any] = {"path": path, "media_type": media_type}
    media_type = (media_type or "").strip().lower()

    if media_type == "image" or (path or "").lower().endswith((".jpg", ".jpeg", ".png")):
        try:
            img = Image.open(path)
            img.load()
            img = img.convert("RGB")
        except Exception:
            return True, {**report, "reason": "image_load_failed"}
        # Resolution gate (kept consistent with video checks)
        try:
            w, h = img.size
            report["media_info"] = {"width": int(w), "height": int(h), "has_video": False, "duration_sec": None, "fps": None}
            if w < int(min_width) or h < int(min_height):
                return True, {**report, "reason": "low_resolution"}
        except Exception:
            pass
        m = analyze_frame(img)
        c = classify_frame(m)
        report["frame_metrics"] = m
        report["frame_class"] = c
        # Strong reject: mostly black, or youtube-like ui.
        reject = bool(c.get("is_blackish") or c.get("youtube_like_ui"))
        if reject:
            report["reason"] = "image_bad_visuals"
        return reject, report

    info = probe_media_info(path)
    report["media_info"] = {
        "duration_sec": info.duration_sec,
        "width": info.width,
        "height": info.height,
        "fps": info.fps,
        "has_video": info.has_video,
    }
    if not info.has_video:
        return True, {**report, "reason": "no_video_stream"}
    if info.width and info.height:
        if info.width < min_width or info.height < min_height:
            # Soft reject: low-res is usually low quality for full HD output.
            report["reason"] = "low_resolution"
            return True, report

    # Sample frames (default: 3 points)
    dur = info.duration_sec or 0.0
    if not sample_times_sec:
        if dur > 8:
            sample_times_sec = (max(0.5, dur * 0.15), dur * 0.5, max(0.5, dur * 0.85))
        else:
            sample_times_sec = (0.5,)

    frames = []
    bad_votes = {"blackish": 0, "caption": 0, "ui": 0, "youtube": 0, "total": 0}
    for t in sample_times_sec:
        m, c = sample_and_classify(path, float(t))
        if m is None or c is None:
            continue
        frames.append({"t": round(float(t), 3), "metrics": m, "class": c})
        bad_votes["total"] += 1
        if c.get("is_blackish"):
            bad_votes["blackish"] += 1
        if c.get("caption_like_overlay"):
            bad_votes["caption"] += 1
        if c.get("ui_like_bars"):
            bad_votes["ui"] += 1
        if c.get("youtube_like_ui"):
            bad_votes["youtube"] += 1

    report["frame_samples"] = frames
    report["bad_votes"] = bad_votes

    # Decision: reject if obvious.
    if bad_votes["youtube"] >= 1:
        report["reason"] = "youtube_like_ui_detected"
        return True, report
    if bad_votes["blackish"] >= max(1, int(round(bad_votes["total"] * 0.6))):
        report["reason"] = "mostly_black_frames"
        return True, report
    if bad_votes["caption"] >= max(2, int(round(bad_votes["total"] * 0.7))):
        report["reason"] = "subtitle_like_overlays"
        return True, report

    # Otherwise accept.
    report["reason"] = "ok"
    return False, report


