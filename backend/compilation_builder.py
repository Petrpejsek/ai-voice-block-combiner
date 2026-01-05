"""
Compilation Builder (CB) - 8. krok v pipeline

Stahuje assety z archive.org a sestavuje finální video.
- Download s cache (aby se nestahovalo znovu)
- Subclipy podle recommended_subclips
- Timeline assembly podle scene timings
- Export do MP4
"""

import json
import os
import time
import hashlib
import subprocess
from collections import deque
from typing import Dict, List, Any, Tuple, Optional, Callable
from datetime import datetime, timezone
import requests
import random
from werkzeug.utils import secure_filename

from asset_quality import probe_media_info, should_reject_media, sample_and_classify


def _now_iso() -> str:
    """Vrací ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def has_video_stream(path: str) -> bool:
    """
    Checks if a file has a valid video stream using ffprobe.
    
    This is critical to prevent black screen issues - FFmpeg can create "valid" files
    without actual video streams. We must verify each clip has visual content.
    
    Args:
        path: Path to video file to check
        
    Returns:
        True if file has at least one video stream, False otherwise
    """
    if not path or not os.path.exists(path):
        return False
    
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return bool(result.stdout.strip())
    except Exception as e:
        print(f"⚠️  has_video_stream check failed for {path}: {e}")
        return False


class CompilationBuilder:
    """
    Builder pro kompilaci videa z archive.org assetů.
    - Download cache (persistent)
    - FFmpeg-based video assembly
    - Scene-based timeline
    - Real-time progress tracking
    """
    
    def __init__(self, storage_dir: str, output_dir: str, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Args:
            storage_dir: Složka pro stažené soubory (cache)
            output_dir: Složka pro finální výstupy
            progress_callback: Optional callback for real-time progress updates
                               Called with: {"phase": str, "message": str, "percent": float, "details": dict}
        """
        self.storage_dir = storage_dir
        self.output_dir = output_dir
        self.progress_callback = progress_callback
        
        # Progress tracking state
        self._progress_state = {
            "phase": "init",
            "total_downloads": 0,
            "completed_downloads": 0,
            "current_download": None,
            "total_clips": 0,
            "completed_clips": 0,
            "current_clip": None,
            "download_bytes": 0,
            "download_speed": 0,
        }
        
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _emit_progress(self, phase: str, message: str, percent: float, **details):
        """Emit progress update to callback if registered."""
        self._progress_state["phase"] = phase
        update = {
            "phase": phase,
            "message": message,
            "percent": min(100.0, max(0.0, percent)),
            "details": {**self._progress_state, **details},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.progress_callback:
            try:
                self.progress_callback(update)
            except Exception as e:
                print(f"⚠️  Progress callback error: {e}")
    
    def _calculate_overall_percent(self) -> float:
        """Calculate overall compilation progress (0-100)."""
        phase = self._progress_state.get("phase", "init")
        
        # Phase weights: downloading (0-50%), cutting (50-90%), assembly (90-100%)
        if phase == "init":
            return 0.0
        elif phase == "downloading":
            total = max(1, self._progress_state.get("total_downloads", 1))
            done = self._progress_state.get("completed_downloads", 0)
            return (done / total) * 50.0
        elif phase == "cutting":
            total = max(1, self._progress_state.get("total_clips", 1))
            done = self._progress_state.get("completed_clips", 0)
            return 50.0 + (done / total) * 40.0
        elif phase == "assembly":
            return 90.0
        elif phase == "done":
            return 100.0
        return 0.0
    
    def _asset_cache_key(self, asset_url: str) -> str:
        """Generuje cache filename z asset URL"""
        url_hash = hashlib.md5(asset_url.encode('utf-8')).hexdigest()[:16]
        return f"asset_{url_hash}"

    def _split_source_prefix(self, archive_item_id: str) -> Tuple[str, str]:
        """
        Normalize AAR multi-source IDs to (source, raw_id).
        Examples:
        - "archive_org:LaLiberationdeParis1944" -> ("archive_org", "LaLiberationdeParis1944")
        - "wikimedia:Some_File.webm"          -> ("wikimedia", "Some_File.webm")
        - "europeana:/9200479/XYZ"            -> ("europeana", "/9200479/XYZ")
        - "LaLiberationdeParis1944"           -> ("archive_org", "LaLiberationdeParis1944")  # legacy
        """
        s = str(archive_item_id or "").strip()
        if not s:
            return "archive_org", ""
        if ":" in s:
            prefix, rest = s.split(":", 1)
            prefix_n = prefix.strip().lower()
            rest_n = rest.strip()
            if prefix_n in ("archive_org", "archiveorg", "archive.org", "archive"):
                return "archive_org", rest_n
            if prefix_n in ("wikimedia", "commons", "wikimedia_commons"):
                return "wikimedia", rest_n
            if prefix_n in ("europeana",):
                return "europeana", rest_n
        return "archive_org", s

    def _wikimedia_fileinfo(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch Wikimedia Commons fileinfo (direct URL + size + mime).
        file_id: e.g. "Some_File.webm" (without "File:")
        """
        try:
            fid = str(file_id or "").strip()
            if not fid:
                return None
            # Normalize title
            fid = fid.replace("File:", "").replace(" ", "_")
            title = f"File:{fid}"
            api_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|size|mime|mediatype",
            }
            headers = {
                "User-Agent": "PodcastVideoBot/1.0 (Documentary compilation; contact: local)"
            }
            r = requests.get(api_url, params=params, headers=headers, timeout=15, verify=False)
            r.raise_for_status()
            data = r.json() or {}
            pages = (data.get("query") or {}).get("pages") or {}
            # pages is dict keyed by pageid
            for _pid, page in pages.items():
                if not isinstance(page, dict):
                    continue
                ii = page.get("imageinfo")
                if not isinstance(ii, list) or not ii:
                    continue
                info = ii[0] if isinstance(ii[0], dict) else None
                if not info:
                    continue
                url = str(info.get("url") or "").strip()
                if not url:
                    continue
                size = int(info.get("size") or 0)
                mime = str(info.get("mime") or "").strip().lower()
                mediatype = str(info.get("mediatype") or "").strip().lower()
                return {"download_url": url, "size_bytes": size, "mime_type": mime, "mediatype": mediatype}
            return None
        except Exception as e:
            print(f"⚠️  CB: Wikimedia fileinfo fetch failed for {file_id}: {e}")
            return None

    def _europeana_download_url(self, record_id: str) -> Optional[str]:
        """
        Best-effort: get a playable URL from Europeana record API.
        NOTE: Europeana often returns viewer pages; some will not be directly downloadable.
        """
        try:
            wskey = (os.getenv("EUROPEANA_API_KEY") or "").strip()
            if not wskey:
                return None
            rid = str(record_id or "").strip()
            if not rid:
                return None
            # recordId for API is without leading slash
            rid = rid.lstrip("/")
            api_url = f"https://api.europeana.eu/record/v2/{rid}.json"
            params = {"wskey": wskey, "profile": "rich"}
            r = requests.get(api_url, params=params, timeout=20, verify=False)
            r.raise_for_status()
            data = r.json() or {}
            obj = data.get("object") if isinstance(data.get("object"), dict) else {}
            aggs = obj.get("aggregations") if isinstance(obj.get("aggregations"), list) else []
            # Prefer edmIsShownBy (often direct media), then edmIsShownAt (viewer)
            def _pick_url(v: Any) -> Optional[str]:
                if isinstance(v, str) and v.strip():
                    return v.strip()
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, str) and x.strip():
                            return x.strip()
                return None
            for agg in aggs:
                if not isinstance(agg, dict):
                    continue
                u = _pick_url(agg.get("edmIsShownBy"))
                if u:
                    return u
            for agg in aggs:
                if not isinstance(agg, dict):
                    continue
                u = _pick_url(agg.get("edmIsShownAt"))
                if u:
                    return u
            # Fallback: sometimes top-level provides these
            for key in ("edmIsShownBy", "edmIsShownAt"):
                u = _pick_url(obj.get(key))
                if u:
                    return u
            return None
        except Exception as e:
            print(f"⚠️  CB: Europeana record fetch failed for {record_id}: {e}")
            return None
    
    def _get_download_url(self, archive_item_id: str) -> Optional[str]:
        """
        Zjistí přímý download URL pro archive.org item.
        Preferuje MP4 format, pak MP3/image podle mediatype.
        
        Args:
            archive_item_id: Archive.org identifier
        
        Returns:
            Direct download URL nebo None
        """
        source, raw_id = self._split_source_prefix(archive_item_id)

        # Multi-source: Wikimedia Commons
        if source == "wikimedia":
            info = self._wikimedia_fileinfo(raw_id)
            return (info or {}).get("download_url")

        # Multi-source: Europeana (best-effort)
        if source == "europeana":
            return self._europeana_download_url(raw_id)

        # Default: archive.org (legacy)
        archive_item_id = raw_id
        
        # Archive.org metadata API
        metadata_url = f"https://archive.org/metadata/{archive_item_id}"
        
        try:
            response = requests.get(metadata_url, timeout=10)
            response.raise_for_status()
            metadata = response.json()
            
            files = metadata.get("files", [])
            
            # Preferuj MP4 formát pro video
            for f in files:
                name = f.get("name", "")
                format_type = f.get("format", "")
                if format_type in ["MPEG4", "h.264"] or name.lower().endswith(".mp4"):
                    download_url = f"https://archive.org/download/{archive_item_id}/{name}"
                    return download_url
            
            # Fallback: hledej cokoliv video (rozšířené formáty: ogv, mpeg, avi, mov, mkv)
            for f in files:
                name = f.get("name", "")
                format_type = f.get("format", "")
                # Archive.org často používá "Ogg Video" (ogv), "MPEG2", "MPEG1", "h.264 IA"
                if format_type in ["MPEG4", "MPEG2", "MPEG1", "h.264", "h.264 IA", "Ogg Video", "Matroska", "QuickTime"] or name.lower().endswith((".mp4", ".avi", ".ogv", ".mpeg", ".mpg", ".mov", ".mkv")):
                    download_url = f"https://archive.org/download/{archive_item_id}/{name}"
                    return download_url
            
            # Last resort: images (for Ken Burns fallback)
            for f in files:
                name = f.get("name", "")
                format_type = f.get("format", "")
                if format_type in ["JPEG", "PNG"] or name.lower().endswith((".jpg", ".png")):
                    download_url = f"https://archive.org/download/{archive_item_id}/{name}"
                    return download_url
            
            print(f"⚠️  CB: No suitable format found for {archive_item_id} (checked formats: {set(f.get('format', 'unknown') for f in files[:10])})")
            return None
        
        except Exception as e:
            print(f"❌ CB: Metadata fetch failed for {archive_item_id}: {e}")
            return None
    
    def _get_asset_info(self, archive_item_id: str) -> Dict[str, Any]:
        """
        NEW: Fetch metadata (size, duration) without breaking existing code.
        Returns: {"size_bytes": int, "duration_sec": float, "download_url": str}
        """
        source, raw_id = self._split_source_prefix(archive_item_id)

        # Wikimedia
        if source == "wikimedia":
            info = self._wikimedia_fileinfo(raw_id) or {}
            return {
                "size_bytes": int(info.get("size_bytes") or 0),
                "duration_sec": 0,
                "download_url": str(info.get("download_url") or ""),
                "mime_type": str(info.get("mime_type") or ""),
            }

        # Europeana (size often unknown)
        if source == "europeana":
            url = self._europeana_download_url(raw_id) or ""
            return {"size_bytes": 0, "duration_sec": 0, "download_url": url}

        # Default: archive.org
        archive_item_id = raw_id
        
        metadata_url = f"https://archive.org/metadata/{archive_item_id}"
        try:
            response = requests.get(metadata_url, timeout=10)
            response.raise_for_status()
            metadata = response.json()
            
            files = metadata.get("files", [])
            for f in files:
                fmt = f.get("format", "")
                name = f.get("name", "")
                # Rozšířená podpora formátů (stejná logika jako _get_download_url)
                if fmt in ["MPEG4", "MPEG2", "MPEG1", "h.264", "h.264 IA", "Ogg Video", "Matroska", "QuickTime"] or name.lower().endswith((".mp4", ".avi", ".ogv", ".mpeg", ".mpg", ".mov", ".mkv")):
                    return {
                        "size_bytes": int(f.get("size", "0")),
                        "duration_sec": float(f.get("length", "0") or "0"),
                        "download_url": f"https://archive.org/download/{archive_item_id}/{name}"
                    }
            # Fallback: images
            for f in files:
                fmt = f.get("format", "")
                name = f.get("name", "")
                if fmt in ["JPEG", "PNG"] or name.lower().endswith((".jpg", ".png")):
                    return {
                        "size_bytes": int(f.get("size", "0")),
                        "duration_sec": 0,
                        "download_url": f"https://archive.org/download/{archive_item_id}/{name}"
                    }
            return {"size_bytes": 0, "duration_sec": 0, "download_url": ""}
        except Exception:
            return {"size_bytes": 0, "duration_sec": 0, "download_url": ""}
    
    def download_asset(self, asset: Dict[str, Any]) -> Optional[str]:
        """
        Stáhne asset (s cache) a vrátí cestu k souboru.
        
        Args:
            asset: Asset dict z enriched shot_plan
        
        Returns:
            Path k staženému souboru nebo None při selhání
        """
        # LOCAL SAFETY PACK SUPPORT (never-fail policy):
        # AAR may inject local assets with local_path. These must be accepted.
        local_path = asset.get("local_path")
        if local_path and isinstance(local_path, str) and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            return local_path

        archive_item_id = asset.get("archive_item_id", "")
        if not archive_item_id:
            print(f"⚠️  CB: Missing archive_item_id and no local_path - skipping asset")
            return None
        # Legacy placeholder/fallback ids are skipped ONLY if they are not backed by local_path.
        if str(archive_item_id).startswith("fallback_"):
            print(f"⚠️  CB: Skipping legacy fallback asset {archive_item_id}")
            return None
        
        # Cache check
        # Cache key should be stable even if asset_url is missing
        base_key = asset.get("asset_url", "") or str(archive_item_id)
        cache_key = self._asset_cache_key(str(base_key))
        
        # Zkus najít existující soubor v cache (*.mp4, *.jpg, *.png)
        for ext in [".mp4", ".webm", ".mkv", ".ogv", ".avi", ".mov", ".jpg", ".png"]:
            cached_file = os.path.join(self.storage_dir, cache_key + ext)
            if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
                print(f"✅ CB: Cache hit for {archive_item_id}")
                return cached_file
        
        # Download with size pre-check
        print(f"📥 CB: Downloading {archive_item_id}...")
        
        # Use a browser-like User-Agent.
        # Wikimedia and some CDNs return 403 for default "python-requests" UA.
        _http_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }

        # FAST PATH: direct media URL provided by AAR (e.g., Wikimedia direct URL, Pexels/Pixabay CDN).
        # This makes new providers plug-and-play without adding per-provider download code.
        asset_url = str(asset.get("asset_url") or "").strip()
        def _is_direct_media_url(u: str) -> bool:
            if not u or not isinstance(u, str):
                return False
            if not (u.startswith("http://") or u.startswith("https://")):
                return False
            # ignore querystring when checking extension
            p = u.split("?", 1)[0].lower()
            return p.endswith((".mp4", ".webm", ".mkv", ".ogv", ".avi", ".mov", ".jpg", ".jpeg", ".png", ".webp"))

        use_direct_url = _is_direct_media_url(asset_url)
        if use_direct_url:
            download_url = asset_url
            # Best-effort: HEAD for Content-Length
            size_mb = 0.0
            duration_sec = 0.0
            try:
                hr = requests.head(download_url, timeout=15, allow_redirects=True, verify=False, headers=_http_headers)
                clen = hr.headers.get("Content-Length") or hr.headers.get("content-length")
                if clen:
                    size_mb = int(clen) / (1024 * 1024)
            except Exception:
                pass
        else:
            # NEW: Pre-check size to avoid downloading huge assets
            info = self._get_asset_info(archive_item_id)
            size_mb = info.get("size_bytes", 0) / (1024 * 1024)
            duration_sec = info.get("duration_sec", 0)
        
        # Size filtering (skip huge assets unless explicitly marked as primary & reusable)
        MAX_SIZE_MB = 500  # Increased from 200MB to 500MB per user request
        is_primary = asset.get("pool_priority") == "primary"
        if size_mb > MAX_SIZE_MB and not is_primary:
            print(f"⚠️  CB: Skipping {archive_item_id}: {size_mb:.1f} MB exceeds limit ({MAX_SIZE_MB} MB)")
            return None
        
        if not use_direct_url:
            download_url = self._get_download_url(archive_item_id)
            if not download_url:
                return None

            # If size is unknown (0), try HEAD for Content-Length to enforce MAX_SIZE_MB
            if not size_mb or size_mb <= 0:
                try:
                    hr = requests.head(download_url, timeout=15, allow_redirects=True, verify=False, headers=_http_headers)
                    clen = hr.headers.get("Content-Length") or hr.headers.get("content-length")
                    if clen:
                        size_bytes = int(clen)
                        size_mb = size_bytes / (1024 * 1024)
                        if size_mb > MAX_SIZE_MB and not is_primary:
                            print(f"⚠️  CB: Skipping {archive_item_id}: {size_mb:.1f} MB exceeds limit ({MAX_SIZE_MB} MB) [HEAD]")
                            return None
                except Exception:
                    pass
        
        print(f"📥 CB: Downloading {archive_item_id} ({size_mb:.1f} MB, {duration_sec:.1f}s)...")
        
        # Emit download start progress
        self._progress_state["current_download"] = archive_item_id
        self._emit_progress(
            "downloading", 
            f"📥 Stahuji: {archive_item_id[:40]}... ({size_mb:.1f} MB)",
            self._calculate_overall_percent(),
            current_file=archive_item_id,
            file_size_mb=round(size_mb, 1),
        )
        
        try:
            # Stream download (může být velký soubor)
            response = requests.get(
                download_url,
                stream=True,
                timeout=180,
                allow_redirects=True,
                verify=False,
                headers=_http_headers,
            )
            response.raise_for_status()
            
            # Detekce přípony z URL
            ext = ".mp4"  # default
            dl_lower = (download_url.split("?", 1)[0] or "").lower()
            if dl_lower.endswith(".jpeg"):
                ext = ".jpg"
            elif dl_lower.endswith(".jpg"):
                ext = ".jpg"
            elif dl_lower.endswith(".png"):
                ext = ".png"
            elif dl_lower.endswith(".webp"):
                ext = ".webp"
            elif dl_lower.endswith(".webm"):
                ext = ".webm"
            elif dl_lower.endswith(".mkv"):
                ext = ".mkv"
            elif dl_lower.endswith(".ogv"):
                ext = ".ogv"
            elif dl_lower.endswith(".avi"):
                ext = ".avi"
            elif dl_lower.endswith(".mov"):
                ext = ".mov"
            
            output_file = os.path.join(self.storage_dir, cache_key + ext)
            
            # Download with progress tracking
            total_size = int(response.headers.get('content-length', 0)) or int(size_mb * 1024 * 1024)
            downloaded = 0
            start_time = time.time()
            last_progress_time = start_time
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):  # Increased chunk size
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Emit progress every 0.5 seconds
                    now = time.time()
                    if now - last_progress_time >= 0.5:
                        elapsed = now - start_time
                        speed_mbps = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        pct = (downloaded / total_size * 100) if total_size > 0 else 0
                        self._progress_state["download_bytes"] = downloaded
                        self._progress_state["download_speed"] = round(speed_mbps, 2)
                        self._emit_progress(
                            "downloading",
                            f"📥 {archive_item_id[:30]}... {pct:.0f}% ({speed_mbps:.1f} MB/s)",
                            self._calculate_overall_percent(),
                            current_file=archive_item_id,
                            downloaded_mb=round(downloaded / (1024 * 1024), 1),
                            total_mb=round(total_size / (1024 * 1024), 1),
                            speed_mbps=round(speed_mbps, 2),
                            download_percent=round(pct, 1),
                        )
                        last_progress_time = now
            
            # Kontrola velikosti
            if os.path.getsize(output_file) == 0:
                os.remove(output_file)
                print(f"❌ CB: Downloaded file is empty: {archive_item_id}")
                return None
            
            # Update completed downloads counter
            self._progress_state["completed_downloads"] += 1
            self._progress_state["current_download"] = None
            
            print(f"✅ CB: Downloaded {archive_item_id} → {output_file}")
            return output_file
        
        except Exception as e:
            # #region agent log (hypothesis CB-403)
            try:
                import time as _time
                import json as _json
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "cb-fix",
                        "hypothesisId": "CB-403",
                        "location": "backend/compilation_builder.py:download_asset",
                        "message": "Download failed",
                        "data": {
                            "archive_item_id": str(archive_item_id),
                            "download_url": str(download_url),
                            "error": str(e)[:240],
                        },
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            print(f"❌ CB: Download failed for {archive_item_id}: {e}")
            return None
    
    def create_subclip(
        self,
        source_file: str,
        in_sec: float,
        out_sec: float,
        output_file: str,
        target_fps: int = 30,
        resolution: str = "1920x1080",
    ) -> bool:
        """
        Vytvoří subclip pomocí FFmpeg.
        
        Args:
            source_file: Cesta k source souboru
            in_sec: Start time v sekundách
            out_sec: End time v sekundách
            output_file: Výstupní soubor
        
        Returns:
            True při úspěchu, False při chybě
        """
        duration = out_sec - in_sec
        if duration <= 0:
            print(f"❌ CB: Invalid subclip duration: {duration}s")
            return False
        
        try:
            # Normalize all clips to target resolution/fps to make concat demuxer reliable.
            try:
                w, h = resolution.lower().split("x", 1)
                target_w = int(w)
                target_h = int(h)
            except Exception:
                target_w, target_h = 1920, 1080

            is_image = source_file.lower().endswith((".jpg", ".jpeg", ".png"))

            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
            ]

            if is_image:
                # ════════════════════════════════════════════════════════════════════════════
                # KEN BURNS EFFECT FOR IMAGES (FIXED: smooth zoom/pan animation)
                # ════════════════════════════════════════════════════════════════════════════
                # PROBLEM: Choppy movement due to:
                #   1) Too small zoom increments
                #   2) Integer rounding in x/y expressions
                #   3) Missing interpolation quality settings
                #
                # SOLUTION:
                #   - Render at exact target FPS (30), no intermediate 60 FPS
                #   - Use linear interpolation in expressions
                #   - Add high-quality scaling flags
                # ════════════════════════════════════════════════════════════════════════════
                cmd.extend(["-loop", "1", "-i", source_file, "-t", str(duration)])
                
                # Ken Burns zoompan filter - SMOOTH version with HIGH QUALITY
                # Key fixes:
                #   - Render at 2x FPS internally (60) for smoother interpolation
                #   - All expressions use internal_frames for proper timing
                #   - Downsample to target FPS at the end
                internal_fps = target_fps * 2  # 60 FPS internal for 30 FPS output
                internal_frames = int(duration * internal_fps)
                
                # Randomize effect type based on output filename hash for variety
                effect_hash = hash(output_file) % 6  # 6 variants
                
                # Zoom amount per frame: total zoom is ~15% over full duration
                # Formula: zoom_per_frame = (1.15 - 1.0) / internal_frames = 0.15 / frames
                zoom_per_frame = 0.15 / max(1, internal_frames)
                
                if effect_hash == 0:
                    # ZOOM IN center (1.0 → 1.15)
                    zoom_expr = f"min(1+on*{zoom_per_frame:.8f},1.15)"
                    x_expr = f"iw/2-(iw/zoom/2)"
                    y_expr = f"ih/2-(ih/zoom/2)"
                elif effect_hash == 1:
                    # ZOOM OUT center (1.15 → 1.0)
                    zoom_expr = f"max(1.15-on*{zoom_per_frame:.8f},1.0)"
                    x_expr = f"iw/2-(iw/zoom/2)"
                    y_expr = f"ih/2-(ih/zoom/2)"
                elif effect_hash == 2:
                    # PAN LEFT→RIGHT (constant zoom 1.15, use full visible range)
                    zoom_expr = "1.15"
                    x_expr = f"(iw-iw/zoom)*(on/{internal_frames})"
                    y_expr = f"(ih-ih/zoom)/2"
                elif effect_hash == 3:
                    # PAN RIGHT→LEFT (constant zoom 1.15)
                    zoom_expr = "1.15"
                    x_expr = f"(iw-iw/zoom)*(1-on/{internal_frames})"
                    y_expr = f"(ih-ih/zoom)/2"
                elif effect_hash == 4:
                    # DIAGONAL TOP-LEFT → BOTTOM-RIGHT with slight zoom
                    zoom_expr = f"min(1+on*{zoom_per_frame*0.7:.8f},1.10)"
                    x_expr = f"(iw-iw/zoom)*(on/{internal_frames})"
                    y_expr = f"(ih-ih/zoom)*(on/{internal_frames})"
                else:
                    # DIAGONAL BOTTOM-RIGHT → TOP-LEFT with slight zoom
                    zoom_expr = f"min(1+on*{zoom_per_frame*0.7:.8f},1.10)"
                    x_expr = f"(iw-iw/zoom)*(1-on/{internal_frames})"
                    y_expr = f"(ih-ih/zoom)*(1-on/{internal_frames})"
                
                vf = (
                    f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
                    f"d={internal_frames}:s={target_w}x{target_h}:fps={internal_fps},"
                    f"fps={target_fps},setsar=1"
                )
            else:
                cmd.extend(["-ss", str(in_sec), "-i", source_file, "-t", str(duration)])
                # Standard scale/crop for videos
                vf = (
                    f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                    f"crop={target_w}:{target_h},setsar=1"
                )

            cmd.extend(
                [
                    "-vf",
                    vf,
                    "-r",
                    str(target_fps),
                    "-pix_fmt",
                    "yuv420p",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-an",  # keep subclips silent; final audio is added in concat step
                ]
            )

            cmd.extend(
                [
                output_file
                ]
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minut timeout
            )
            
            if result.returncode != 0:
                print(f"❌ CB: FFmpeg subclip failed: {result.stderr[:500]}")
                return False
            
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                print(f"❌ CB: Subclip output is empty or missing")
                return False
            
            return True
        
        except subprocess.TimeoutExpired:
            print(f"❌ CB: FFmpeg subclip timeout")
            return False
        except Exception as e:
            print(f"❌ CB: Subclip creation error: {e}")
            return False

    def create_color_clip(
        self,
        duration_sec: float,
        output_file: str,
        color: str = "black",
        target_fps: int = 30,
        resolution: str = "1920x1080",
    ) -> bool:
        """
        DEPRECATED: This method is deprecated and must never be called.
        Black screen fallbacks are not allowed in production pipeline.
        
        Raises:
            RuntimeError: Always raises error to prevent black screen generation.
        """
        raise RuntimeError(
            "create_color_clip is DEPRECATED and must never be called. "
            "Black screen fallbacks are not allowed in production pipeline. "
            "If you see this error, it indicates a bug in the compilation logic."
        )
    
    def concatenate_clips(
        self,
        clip_files: List[str],
        output_file: str,
        target_fps: int = 30,
        resolution: str = "1920x1080",
        audio_file: Optional[str] = None
    ) -> bool:
        """
        Spojí klipy do jednoho videa pomocí FFmpeg concat.
        
        Args:
            clip_files: List cest k clip souborům
            output_file: Výstupní soubor
            target_fps: Target FPS
            resolution: Target resolution
            audio_file: Cesta k audio souboru (voiceover MP3)
        
        Returns:
            True při úspěchu
        """
        # Keep last concat error details for caller (build_compilation) / script_state diagnostics.
        # This is intentionally small + grep-friendly (trim stderr).
        self._last_concat_error = None

        if not clip_files:
            print(f"❌ CB: No clips to concatenate")
            self._last_concat_error = {
                "reason": "no_clips",
            }
            return False
        
        # CRITICAL GUARD: Verify all clips have video streams
        # This is the final defense against black screen output
        print(f"🔍 CB concat: Validating {len(clip_files)} clips before concatenation...")
        for clip_path in clip_files:
            if not has_video_stream(clip_path):
                print(f"❌ CRITICAL: Attempted to concat clip without video stream: {clip_path}")
                self._last_concat_error = {
                    "reason": "clip_without_video_stream",
                    "invalid_clip": clip_path
                }
                raise RuntimeError(
                    f"Attempted to concatenate clip without video stream: {clip_path}. "
                    "This would create black screen output. Failing immediately."
                )
        # If we got here, all clips have video streams.

        # Filter missing / empty clips early (avoid FFmpeg hard fail)
        filtered = []
        for p in clip_files:
            try:
                if not p or not os.path.exists(p) or os.path.getsize(p) <= 0:
                    print(f"⚠️  CB: Skipping missing/empty clip: {p}")
                    continue
            except Exception:
                print(f"⚠️  CB: Skipping unreadable clip: {p}")
                continue
            filtered.append(p)

        if not filtered:
            print("❌ CB: All clips were missing/empty - cannot concatenate")
            self._last_concat_error = {
                "reason": "all_clips_missing_or_empty",
            }
            return False

        clip_files = filtered
        
        # Vytvoř concat file list (unique per run to avoid concurrency stomping)
        concat_list_file = os.path.join(
            self.storage_dir,
            f"concat_list_{int(time.time()*1000)}_{os.getpid()}.txt",
        )
        
        try:
            with open(concat_list_file, 'w', encoding='utf-8') as f:
                for clip in clip_files:
                    # FFmpeg concat format: file '/path/to/file.mp4'
                    f.write(f"file '{os.path.realpath(os.path.abspath(clip))}'\n")
            
            # Parse resolution once for filter_complex (needs w:h, not "wxh")
            try:
                w_s, h_s = resolution.lower().split("x", 1)
                res_w = int(w_s)
                res_h = int(h_s)
            except Exception:
                res_w, res_h = 1920, 1080

            def _run_ffmpeg(cmd: List[str], timeout: int) -> Tuple[bool, str, int]:
                try:
                    r = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    return (r.returncode == 0, (r.stderr or ""), int(r.returncode))
                except subprocess.TimeoutExpired:
                    return (False, "FFmpeg timeout", 124)

            # Deterministic single-path concat:
            # Always use filter_complex concat (more robust than concat demuxer),
            # so we do NOT have any fallback behavior.
            has_audio = bool(audio_file and os.path.exists(audio_file))
            if has_audio:
                print(f"🎤 CB: Adding voiceover audio: {audio_file}")
            else:
                # Never-fail policy: allow silent output (emit warning via diagnostics).
                print(f"⚠️  CB: No audio file provided - generating silent video (never-fail policy)")

            # Build filter concat command
            # Note: This can be heavier, but is reliable for small (<~80) clips typical for 1–2 min episodes.
            fc_cmd = ["ffmpeg", "-y", "-fflags", "+genpts"]
            for p in clip_files:
                fc_cmd.extend(["-i", p])
            if has_audio:
                fc_cmd.extend(["-i", audio_file])

            n = len(clip_files)
            filters = []
            for i in range(n):
                filters.append(
                    f"[{i}:v]scale={res_w}:{res_h}:force_original_aspect_ratio=increase,"
                    f"crop={res_w}:{res_h},setsar=1,fps={target_fps},format=yuv420p[v{i}]"
                )
            concat_inputs = "".join([f"[v{i}]" for i in range(n)])
            filters.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vcat]")
            filters.append("[vcat]tpad=stop_mode=clone:stop_duration=3600[vout]")
            filter_complex = ";".join(filters)

            fc_cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]"])
            if has_audio:
                fc_cmd.extend(
                    [
                        "-map",
                        f"{n}:a:0",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-shortest",
                    ]
                )
            else:
                fc_cmd.extend(["-an"])

            fc_cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "23",
                    "-movflags",
                    "+faststart",
                    output_file,
                ]
            )

            ok, stderr, rc = _run_ffmpeg(fc_cmd, timeout=1800)
            if not ok:
                err_snip = (stderr or "")[:2000]
                print(f"❌ CB: FFmpeg filter-concat failed (rc={rc}): {err_snip[:500]}")
                self._last_concat_error = {
                    "attempt": "filter_complex_concat",
                    "returncode": rc,
                    "stderr": err_snip,
                }
                return False
            
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                print(f"❌ CB: Concat output is empty or missing")
                self._last_concat_error = {
                    "attempt": "post_check",
                    "reason": "output_missing_or_empty",
                }
                return False
            
            print(f"✅ CB: Concatenated {len(clip_files)} clips → {output_file}")
            # Success → clear any previous error
            self._last_concat_error = None
            return True
        
        except Exception as e:
            print(f"❌ CB: Concatenation error: {e}")
            self._last_concat_error = {
                "attempt": "python_exception",
                "error": str(e),
            }
            return False
        finally:
            # Cleanup concat list
            if os.path.exists(concat_list_file):
                try:
                    os.remove(concat_list_file)
                except:
                    pass
    
    def build_compilation(
        self,
        manifest_path: str,
        episode_id: str,
        target_duration_sec: Optional[float] = None
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Sestaví finální video z archive_manifest.json.
        
        Args:
            manifest_path: Cesta k archive_manifest.json souboru
            episode_id: ID epizody (pro naming)
            target_duration_sec: Target délka videa (pokud None, použije se z scenes)
        
        Returns:
            (output_video_path, metadata) - path je None při selhání
        """
        # Load manifest
        if not os.path.exists(manifest_path):
            print(f"❌ CB: Manifest file not found: {manifest_path}")
            return None, {"error": f"Manifest not found: {manifest_path}"}
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"❌ CB: Failed to load manifest: {e}")
            return None, {"error": f"Manifest load failed: {e}"}
        
        # Validate manifest structure
        if "scenes" not in manifest:
            print(f"❌ CB: Manifest missing 'scenes' key")
            return None, {"error": "Manifest missing 'scenes'"}
        
        if "compile_plan" not in manifest:
            print(f"❌ CB: Manifest missing 'compile_plan' key")
            return None, {"error": "Manifest missing 'compile_plan'"}
        
        scenes = manifest.get("scenes", [])
        compile_plan = manifest.get("compile_plan", {})
        
        if not scenes:
            print(f"❌ CB: No scenes in fda_package")
            return None, {"error": "No scenes"}
        
        # Extrakce compile_plan parametrů
        target_fps = compile_plan.get("target_fps", 30)
        resolution = compile_plan.get("resolution", "1920x1080")
        
        # Výstupní soubor
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"episode_{episode_id}_compilation_{timestamp}.mp4"
        output_path = os.path.join(self.output_dir, output_filename)
        
        print(f"🎬 CB: Building compilation for {len(scenes)} scenes...")
        
        all_clips = []
        clips_metadata = []  # Global metadata pro všechny subclips
        scenes_metadata = []
        # Count "no-visual" situations (used for diagnostics + hard validation logging).
        # NOTE: This must exist regardless of beat-based vs legacy scene-based mode.
        fallback_count = 0

        # CB DEBUG INFO COLLECTION (for zero-clips diagnostics)
        # Initialized here to be available for both beat-based and legacy paths
        cb_debug_info: Dict[str, Any] = {
            "scenes_with_zero_candidates": [],
            "beats_with_zero_assets": [],
            "quality_gate_reject_reasons": {},
            "most_common_reject_reason": None,
            "last_successful_asset": None,
        }

        # ------------------------------------------------------------
        # NEW: Block-level compilation (1 narration_block = 1 visual beat)
        # ------------------------------------------------------------
        beats = []
        for scene in scenes:
            vb = scene.get("visual_beats")
            if isinstance(vb, list) and vb:
                for b in vb:
                    if isinstance(b, dict):
                        # CRITICAL FIX: AAR stores assets in beat["asset_candidates"], not beat["assets"]
                        # Merge: prefer beat-level asset_candidates, then fall back to scene-level assets
                        beat_candidates = b.get("asset_candidates") or []
                        scene_assets = scene.get("assets") or []
                        # Combine both sources - beat candidates take priority
                        combined_assets = list(beat_candidates)
                        existing_ids = {a.get("archive_item_id") for a in combined_assets if isinstance(a, dict)}
                        for sa in scene_assets:
                            if isinstance(sa, dict) and sa.get("archive_item_id") not in existing_ids:
                                combined_assets.append(sa)
                        beats.append(
                            {
                                "scene_id": scene.get("scene_id", "unknown"),
                                "block_id": b.get("block_id"),
                                "block_index": b.get("block_index"),
                                "target_duration_sec": b.get("target_duration_sec"),
                                "selected_asset_id": b.get("selected_asset_id") or "",
                                "asset_candidates": beat_candidates,
                                "assets": combined_assets,  # Now includes beat-level candidates!
                            }
                        )

        # If beats exist, we switch to beat-based cutting. Otherwise, keep legacy scene-based logic.
        use_beats = len(beats) > 0
        if use_beats:
            # Ensure deterministic order aligned with voiceover (block_index)
            beats.sort(key=lambda x: (x.get("block_index") is None, x.get("block_index") or 10**9))
            print(f"🎬 CB: Using block-level beats: {len(beats)} beats")

            used_subclip_ranges = {}  # Track used segments per asset
            asset_duration_cache: Dict[str, float] = {}
            # Avoid "loopy" feeling: try not to use the same archive item in consecutive beats
            # INCREASED from 3 to cover more beats (reduces repetition in longer videos)
            recent_asset_ids = deque(maxlen=8)
            # Global diversity: track how many times each asset has been used in this compilation
            asset_use_counts: Dict[str, int] = {}

            def _probe_media_duration(path: str) -> Optional[float]:
                if not path or not os.path.exists(path):
                    return None
                # For images, duration is defined by us; treat as unknown here.
                if path.lower().endswith((".jpg", ".jpeg", ".png")):
                    return None
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
                            path,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if r.returncode != 0:
                        return None
                    s = (r.stdout or "").strip()
                    if not s:
                        return None
                    return float(s)
                except Exception:
                    return None

            def _clamp_out(in_sec: float, desired_duration: float, media_duration: Optional[float]) -> float:
                """
                Clamp out_sec so that:
                - out_sec > in_sec
                - out_sec - in_sec is as close as possible to desired_duration
                - does not exceed media_duration if known
                """
                out_sec = float(in_sec) + float(desired_duration)
                if media_duration and media_duration > 0:
                    # keep a tiny headroom to avoid exact-end issues
                    max_out = max(0.0, float(media_duration) - 0.05)
                    if out_sec > max_out:
                        out_sec = max_out
                # ensure minimal positive duration
                if out_sec <= in_sec:
                    out_sec = in_sec + 0.5
                return out_sec

            def _find_asset_by_id(scene_assets: List[dict], archive_item_id: str) -> Optional[dict]:
                """
                E: Strict invariant - asset MUST be in scene_assets (from manifest).
                Out-of-manifest access is hard error.
                """
                for a in scene_assets or []:
                    if not isinstance(a, dict):
                        continue
                    if a.get("archive_item_id") == archive_item_id:
                        return a
                # E: INVARIANT VIOLATION
                print(f"❌ CB INVARIANT: Asset {archive_item_id} NOT in manifest! This should never happen.")
                return None
            
            def _determine_subclip_count(target_duration_sec: float) -> int:
                """
                Determine how many subclips per beat.
                Goal: avoid jittery pacing -> prefer 1 stable shot per narration block,
                and only split long blocks.
                """
                if target_duration_sec <= 14.0:
                    return 1
                if target_duration_sec <= 28.0:
                    return 2
                return 3
            
            def _generate_multi_subclipy(
                source_file: str,
                asset_id: str,
                beat_total_duration: float,
                num_subclipy: int,
                used_ranges: List[Tuple[float, float]],
                media_duration: Optional[float]
            ) -> List[Dict[str, Any]]:
                """
                Generate multiple non-overlapping subclips from one asset.
                Returns: [{"in_sec": float, "out_sec": float, "duration": float}, ...]
                """
                # D1 FIX: NO TITLECARDS - increase safe_head from 2.0 to 30.0
                # Most archive videos have logos/titles/credits in first 20-30s
                safe_head = 30.0  # Changed from 2.0
                safe_tail = 2.0
                if media_duration and media_duration > 0:
                    safe_max = max(0.0, float(media_duration) - safe_tail)
                else:
                    safe_max = None

                def _clamp_in(in_sec: float) -> float:
                    in_sec = max(float(in_sec), safe_head)
                    if safe_max is not None:
                        # ensure at least 1s of room
                        in_sec = min(in_sec, max(safe_head, safe_max - 1.0))
                    return in_sec

                if num_subclipy <= 1:
                    # Single clip - stable visual for the whole beat (preferred).
                    last_out = max([o for _, o in used_ranges], default=0.0) if used_ranges else 0.0
                    # D1 FIX: Ensure we start after safe_head (30s)
                    in_sec = _clamp_in(max(last_out + 1.0, safe_head))

                    out_sec = _clamp_out(in_sec, beat_total_duration, media_duration)
                    # Minimum duration floor to avoid micro-cuts (even if beat is short, keep >=3s)
                    if (out_sec - in_sec) < 3.0:
                        out_sec = _clamp_out(in_sec, 3.0, media_duration)
                    return [{"in_sec": in_sec, "out_sec": out_sec, "duration": max(0.001, out_sec - in_sec)}]
                
                # Multi-clip: divide beat duration evenly, enforce min per-shot duration.
                target_clip_dur = max(5.0, beat_total_duration / num_subclipy)
                actual_media_dur = media_duration if media_duration and media_duration > 0 else 600.0  # assume 10min
                
                # Segment the video into non-overlapping regions
                segments = []
                if actual_media_dur > beat_total_duration:
                    segment_size = actual_media_dur / num_subclipy
                    for i in range(num_subclipy):
                        seg_start = i * segment_size
                        seg_end = min((i + 1) * segment_size, actual_media_dur)
                        # Apply safe head/tail
                        seg_start = max(seg_start, safe_head)
                        seg_end = min(seg_end, actual_media_dur - safe_tail)
                        # Find unused window in this segment
                        window_start = seg_start
                        for used_in, used_out in sorted(used_ranges):
                            if used_out > seg_start and used_in < seg_end:
                                window_start = max(window_start, used_out + 0.5)
                        window_start = _clamp_in(window_start)
                        window_end = min(window_start + target_clip_dur + 1.0, seg_end)
                        if window_end > window_start:
                            segments.append((window_start, window_end))
                
                if len(segments) < num_subclipy:
                    # Fallback: sequential non-overlapping
                    last_out = max([o for _, o in used_ranges], default=0.0) if used_ranges else 0.0
                    for i in range(num_subclipy):
                        start = _clamp_in(last_out + 1.0 + (i * (target_clip_dur + 0.5)))
                        end = start + target_clip_dur
                        if media_duration:
                            end = min(end, float(media_duration) - safe_tail)
                        if end > start:
                            segments.append((start, end))
                
                # Build subclip specs
                result = []
                for seg_start, seg_end in segments[:num_subclipy]:
                    seg_start = _clamp_in(seg_start)
                    clip_dur = min(target_clip_dur, max(0.001, seg_end - seg_start))
                    result.append({
                        "in_sec": seg_start,
                        "out_sec": _clamp_out(seg_start, clip_dur, media_duration),
                        "duration": clip_dur
                    })
                    used_ranges.append((seg_start, seg_start + clip_dur))
                
                return result

            def _is_subclip_blackish(path: str, t_rel: float) -> bool:
                """
                Quick guard: sample a frame in the produced subclip to detect black flash.
                """
                try:
                    m, c = sample_and_classify(path, t_rel)
                    if not c:
                        return False
                    return bool(c.get("is_blackish"))
                except Exception:
                    return False

            def _pick_acceptable_asset_for_beat(beat: Dict[str, Any]) -> Tuple[Optional[dict], Optional[str], Dict[str, Any]]:
                """
                Pick a usable asset for a beat.
                
                USER POLICY (Dec 2025):
                - Do NOT block assets based on resolution thresholds (remove strict/relaxed gates).
                - Prefer "something usable" over rejecting everything and ending up with no visuals.
                
                We keep only HARD technical checks:
                - file must download / exist
                - for videos: must have a real video stream
                
                Returns (asset_obj, downloaded_path, debug_report).
                """
                quality_debug: Dict[str, Any] = {"attempts": []}

                # Candidate list: beat.asset_candidates (ranked by AAR/LLM) -> fallback to scene assets by priority
                candidate_ids = []
                # Respect Visual Assistant guidance: never use candidates explicitly marked as "skip".
                # This prevents "LLM chose good visuals, but CB compiled something else/off-topic".
                use_ids = []
                fallback_ids = []
                unknown_ids = []
                for cand in beat.get("asset_candidates") or []:
                    if not isinstance(cand, dict):
                        continue
                    aid = (cand or {}).get("archive_item_id")
                    if not aid or str(aid).startswith("fallback_"):
                        continue
                    va = cand.get("_visual_analysis") if isinstance(cand.get("_visual_analysis"), dict) else {}
                    rec = str(va.get("recommendation") or "").strip().lower()
                    has_text = va.get("has_text_overlay", False) is True
                    # HARD REJECT: assets marked as "skip" OR with text overlay
                    if rec == "skip":
                        continue
                    if has_text:
                        # Text overlay is a HARD reject for documentary footage
                        continue
                    if rec == "use":
                        use_ids.append(str(aid))
                    elif rec == "fallback":
                        fallback_ids.append(str(aid))
                    else:
                        unknown_ids.append(str(aid))
                candidate_ids = use_ids + fallback_ids + unknown_ids

                if not candidate_ids:
                    # Fallback to scene assets, but STILL apply visual analysis filtering!
                    # Build lookup of visual analysis from asset_candidates (they have the LLM verdict)
                    va_lookup = {}
                    for cand in beat.get("asset_candidates") or []:
                        if isinstance(cand, dict):
                            cand_id = str(cand.get("archive_item_id") or "")
                            if cand_id:
                                va_lookup[cand_id] = cand.get("_visual_analysis") or {}
                    
                    scene_assets = [a for a in (beat.get("assets") or []) if isinstance(a, dict)]
                    scene_assets = sorted(scene_assets, key=lambda x: x.get("priority", 99))
                    for a in scene_assets:
                        aid = str(a.get("archive_item_id") or "")
                        if not aid or aid.startswith("fallback_"):
                            continue
                        # CRITICAL: Look up visual analysis from asset_candidates if not on scene asset
                        va = a.get("_visual_analysis") if isinstance(a.get("_visual_analysis"), dict) else {}
                        if not va:
                            va = va_lookup.get(aid, {})
                        rec = str(va.get("recommendation") or "").strip().lower()
                        has_text = va.get("has_text_overlay", False) is True
                        if rec == "skip":
                            continue
                        if has_text:
                            continue
                        candidate_ids.append(aid)
                
                # ════════════════════════════════════════════════════════════════════════════
                # STABILITY FALLBACK: If ALL candidates were filtered out, use ANY available
                # asset rather than having zero visuals. Some visual is better than black screen.
                # ════════════════════════════════════════════════════════════════════════════
                if not candidate_ids:
                    # Last resort: collect ALL asset IDs from any source, ignore filters
                    all_asset_ids = []
                    for cand in beat.get("asset_candidates") or []:
                        if isinstance(cand, dict):
                            aid = str(cand.get("archive_item_id") or "")
                            if aid and not aid.startswith("fallback_"):
                                all_asset_ids.append(aid)
                    for a in beat.get("assets") or []:
                        if isinstance(a, dict):
                            aid = str(a.get("archive_item_id") or "")
                            if aid and not aid.startswith("fallback_") and aid not in all_asset_ids:
                                all_asset_ids.append(aid)
                    if all_asset_ids:
                        # Use the first available (stability > quality when desperate)
                        candidate_ids = all_asset_ids[:3]
                        quality_debug["stability_fallback"] = True

                # De-dupe while preserving order
                seen = set()
                deduped = []
                for aid in candidate_ids:
                    if aid in seen:
                        continue
                    seen.add(aid)
                    deduped.append(aid)
                candidate_ids = deduped

                # Manual selection: if user selected a specific asset for this beat, prefer it first.
                preferred = str(beat.get("selected_asset_id") or "").strip()
                if preferred:
                    if preferred in candidate_ids:
                        candidate_ids = [preferred] + [x for x in candidate_ids if x != preferred]
                    else:
                        # If selected isn't in asset_candidates, still try it if it's present in scene assets.
                        if _find_asset_by_id(beat.get("assets") or [], preferred):
                            candidate_ids = [preferred] + candidate_ids

                # Diversity (strong): prefer assets that were used fewer times in this compilation.
                # This prevents obvious repetition when AAR returns a small set of good candidates.
                if candidate_ids:
                    head = []
                    tail = candidate_ids
                    if preferred and candidate_ids and candidate_ids[0] == preferred:
                        head = [preferred]
                        tail = candidate_ids[1:]
                    # Stable sort by usage count; preserves AAR rank among equal counts.
                    tail = sorted(tail, key=lambda x: asset_use_counts.get(x, 0))
                    # Soft avoid recently used assets if alternatives exist
                    if len(tail) > 1 and len(recent_asset_ids) > 0:
                        recent_set = set(recent_asset_ids)
                        non_recent = [x for x in tail if x not in recent_set]
                        recent = [x for x in tail if x in recent_set]
                        if non_recent:
                            tail = non_recent + recent
                    candidate_ids = head + tail

                # Single-pass: accept the first technically-usable asset.
                # Keep bounded for runtime and diversity handling above.
                for aid in candidate_ids[:10]:
                    aobj = _find_asset_by_id(beat.get("assets") or [], aid)
                    if not aobj:
                        continue
                    source_file = self.download_asset(aobj)
                    if not source_file:
                        quality_debug["attempts"].append(
                            {"archive_item_id": aid, "accepted": False, "reason": "download_failed"}
                        )
                        continue

                    is_image = source_file.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
                    if not is_image and not has_video_stream(source_file):
                        quality_debug["attempts"].append(
                            {"archive_item_id": aid, "accepted": False, "reason": "no_video_stream"}
                        )
                        continue

                    quality_debug["attempts"].append(
                        {"archive_item_id": aid, "accepted": True, "reason": "accepted_technical_ok"}
                    )
                    return aobj, source_file, quality_debug

                return None, None, quality_debug

            def _compact_quality_debug(qd: Dict[str, Any]) -> Dict[str, Any]:
                """
                Compilation reports should stay readable and not explode in size.
                Keep only the essential decision signals from the quality gate.
                """
                out = {"attempts": []}
                for a in (qd or {}).get("attempts") or []:
                    if not isinstance(a, dict):
                        continue
                    mi = a.get("media_info") if isinstance(a.get("media_info"), dict) else {}
                    bv = a.get("bad_votes") if isinstance(a.get("bad_votes"), dict) else {}
                    out["attempts"].append(
                        {
                            "archive_item_id": a.get("archive_item_id"),
                            "accepted": a.get("accepted"),
                            "reason": a.get("reason"),
                            "media_info": {
                                "duration_sec": mi.get("duration_sec"),
                                "width": mi.get("width"),
                                "height": mi.get("height"),
                                "has_video": mi.get("has_video"),
                            }
                            if mi
                            else None,
                            "bad_votes": bv if bv else None,
                        }
                    )
                return out

            # Initialize progress tracking for cutting phase
            self._progress_state["total_clips"] = len(beats)
            self._progress_state["completed_clips"] = 0
            self._progress_state["phase"] = "cutting"
            self._emit_progress(
                "cutting",
                f"✂️ Stříhám video: 0/{len(beats)} beatů",
                self._calculate_overall_percent(),
                total_beats=len(beats),
            )

            for beat_idx, beat in enumerate(beats, start=1):
                scene_id = beat.get("scene_id", "unknown")
                block_id = beat.get("block_id") or f"b_{beat_idx:04d}"
                
                # Emit cutting progress
                self._progress_state["current_clip"] = block_id
                self._emit_progress(
                    "cutting",
                    f"✂️ Stříhám: {block_id} ({beat_idx}/{len(beats)})",
                    self._calculate_overall_percent(),
                    current_beat=block_id,
                    beat_index=beat_idx,
                    total_beats=len(beats),
                )
                dur = beat.get("target_duration_sec")
                try:
                    dur = float(dur)
                except Exception:
                    dur = 4.5  # conservative fallback
                if dur <= 0:
                    dur = 3.5

                # Track beats with zero candidates
                beat_candidates = beat.get("asset_candidates") or []
                if len(beat_candidates) == 0:
                    cb_debug_info["beats_with_zero_assets"].append({
                        "beat_id": block_id,
                        "scene_id": scene_id,
                        "reason": "no_asset_candidates",
                    })

                chosen_asset, source_file, quality_dbg = _pick_acceptable_asset_for_beat(beat)
                quality_dbg = _compact_quality_debug(quality_dbg)

                # Collect reject reasons from quality gate
                for attempt in (quality_dbg.get("attempts") or []):
                    if not attempt.get("accepted") and attempt.get("reason"):
                        reason = attempt.get("reason")
                        cb_debug_info["quality_gate_reject_reasons"][reason] = \
                            cb_debug_info["quality_gate_reject_reasons"].get(reason, 0) + 1
                
                # C2 FIX: Track override decisions
                override_info = None

                # NEW: Multi-clip per beat
                beat_subclipy = []  # Will store metadata for each subclip in this beat
                
                if chosen_asset and source_file:
                    asset_id = chosen_asset.get("archive_item_id", "")
                    
                    # Track last successful asset for debug info
                    cb_debug_info["last_successful_asset"] = {
                        "asset_id": asset_id,
                        "beat_id": block_id,
                        "scene_id": scene_id,
                        "query_used": chosen_asset.get("query_used", ""),
                    }
                    
                    # C2: Check if this asset is from asset_candidates (deterministic) or override
                    candidate_ids = [c.get("archive_item_id") for c in beat.get("asset_candidates", []) if c]
                    if asset_id and candidate_ids and asset_id not in candidate_ids:
                        override_info = {
                            "override": True,
                            "override_reason": "fallback_to_scene_assets",
                            "original_candidates": candidate_ids[:3],
                            "final_asset_id": asset_id
                        }
                    
                    # Cache media duration for clamping (per asset file)
                    if asset_id and asset_id not in asset_duration_cache:
                        md = _probe_media_duration(source_file)
                        if isinstance(md, (int, float)) and md > 0:
                            asset_duration_cache[asset_id] = float(md)

                    if asset_id not in used_subclip_ranges:
                        used_subclip_ranges[asset_id] = []

                    media_dur = asset_duration_cache.get(asset_id)
                    
                    # Determine how many subclipy for this beat
                    num_subclipy = _determine_subclip_count(dur)
                    
                    # Generate multi-clip specs
                    subclip_specs = _generate_multi_subclipy(
                        source_file, asset_id, dur, num_subclipy,
                        used_subclip_ranges[asset_id], media_dur
                    )
                    
                    # Create each subclip
                    for sub_idx, spec in enumerate(subclip_specs):
                        clip_counter = len(all_clips) + 1
                        subclip_filename = f"beat_{clip_counter:05d}_{scene_id}_{block_id}_sub{sub_idx+1}.mp4"
                        subclip_path = os.path.join(self.storage_dir, subclip_filename)
                        
                        # Guard against black intros: robustly escape long black segments (not just a 1s shift).
                        in0 = float(spec["in_sec"])
                        out0 = float(spec["out_sec"])
                        desired_len = max(3.0, out0 - in0)

                        def _is_black_intro(path: str, dur_sec: float) -> bool:
                            """
                            Detect long/obvious black intro inside a produced subclip.
                            Sample multiple timestamps to catch cases like 10s+ black.
                            """
                            try:
                                dur_sec = float(dur_sec or 0.0)
                            except Exception:
                                dur_sec = 0.0
                            samples = [0.25]
                            if dur_sec >= 3.0:
                                samples.append(1.5)
                            if dur_sec >= 8.0:
                                samples.append(4.0)
                            votes = 0
                            total = 0
                            for t in samples:
                                if dur_sec > 0 and t >= max(0.25, dur_sec - 0.25):
                                    continue
                                total += 1
                                if _is_subclip_blackish(path, float(t)):
                                    votes += 1
                            return total > 0 and votes >= max(1, int(round(total * 0.66)))

                        success = False
                        final_in = in0
                        final_out = out0
                        # Try shifts (sec) to escape long black intros
                        for shift in (0.0, 1.0, 3.0, 7.0, 12.0):
                            in_try = float(in0) + float(shift)
                            out_try = _clamp_out(in_try, desired_len, media_dur)
                            if (out_try - in_try) < 3.0:
                                out_try = _clamp_out(in_try, 3.0, media_dur)
                            try:
                                if os.path.exists(subclip_path):
                                    os.remove(subclip_path)
                            except Exception:
                                pass
                            ok = self.create_subclip(
                                source_file,
                                in_try,
                                out_try,
                                subclip_path,
                                target_fps=target_fps,
                                resolution=resolution,
                            )
                            if not ok:
                                continue
                            if _is_black_intro(subclip_path, float(out_try - in_try)):
                                continue
                            success = True
                            final_in = in_try
                            final_out = out_try
                            break

                        # Update spec for metadata if succeeded
                        if success:
                            spec["in_sec"] = float(final_in)
                            spec["out_sec"] = float(final_out)
                            spec["duration"] = float(final_out - final_in)
                        if success:
                            # CRITICAL: Validate clip has actual video stream before adding
                            if not has_video_stream(subclip_path):
                                print(f"❌ INVALID CLIP (NO VIDEO STREAM): {subclip_path}")
                                print(f"   Beat {block_id}, subclip {sub_idx+1} - REJECTING clip without video stream")
                                # Do not append to all_clips - this would create black screen
                                continue
                            
                            all_clips.append(subclip_path)
                            
                            # CRITICAL FIX: Track used segment to prevent repetition
                            used_range = (spec["in_sec"], spec["out_sec"])
                            used_subclip_ranges[asset_id].append(used_range)
                            
                            subclip_meta = {
                                "scene_id": scene_id,
                                "block_id": block_id,
                                "beat_index": beat.get("block_index"),
                                "subclip_index": sub_idx + 1,
                                "asset_id": asset_id,
                                "subclip_file": subclip_path,
                                "in_sec": spec["in_sec"],
                                "out_sec": spec["out_sec"],
                                "duration": round(spec["duration"], 3),
                                "mode": "multi_clip",
                                "quality_gate": quality_dbg,
                            }
                            # C2: Add override info if present
                            if override_info:
                                subclip_meta["override_info"] = override_info
                            clips_metadata.append(subclip_meta)
                            beat_subclipy.append(subclip_meta)
                    
                    if beat_subclipy:
                        # Track last used asset to avoid immediate repetition on next beat
                        if asset_id:
                            recent_asset_ids.append(str(asset_id))
                            asset_use_counts[str(asset_id)] = asset_use_counts.get(str(asset_id), 0) + 1
                        # Update progress after successful beat
                        self._progress_state["completed_clips"] += 1
                        self._emit_progress(
                            "cutting",
                            f"✂️ Stříhám: {beat_idx}/{len(beats)} beatů hotovo",
                            self._calculate_overall_percent(),
                            completed_beats=beat_idx,
                            total_beats=len(beats),
                        )
                        continue

                # NO FALLBACK: If no acceptable asset found, this beat will have no visual.
                # Global validation below will catch insufficient coverage and fail if needed.
                fallback_count += 1
                print(f"⚠️  CB: Beat {block_id} has no acceptable assets (quality gate failed all candidates)")
                print(f"    Quality gate attempts: {len(quality_dbg.get('attempts', []))}")
                # Continue to next beat without creating black screen clip

            # Scenes metadata (aggregate)
            scenes_metadata = []
            by_scene = {}
            for c in clips_metadata:
                sid = c.get("scene_id", "unknown")
                by_scene.setdefault(sid, []).append(c)
            for sid, items in by_scene.items():
                scenes_metadata.append(
                    {
                        "scene_id": sid,
                        "scene_target_duration_sec": None,
                        "scene_actual_duration_sec": sum(float(x.get("duration", 0) or 0) for x in items),
                        "subclips_count": len(items),
                        "clips_metadata": items,
                        "mode": "block_level",
                    }
                )

            # Proceed to audio stage below (shared)

        if not use_beats:
            # Pro každou scénu (legacy scene-level fill)
            for scene in scenes:
                scene_id = scene.get("scene_id", "unknown")
                target_scene_duration = scene.get("end_sec", 0) - scene.get("start_sec", 0)

                if target_scene_duration <= 0:
                    print(f"⚠️  CB: Scene {scene_id} has invalid duration, skipping")
                    continue

                assets = scene.get("assets", [])
                if not assets:
                    print(f"⚠️  CB: Scene {scene_id} has no assets, skipping")
                    fallback_count += 1
                    continue

                print(f"🎬 CB: Processing scene {scene_id} (target: {target_scene_duration:.1f}s)")

                # Seřaď assety podle priority (1=best, 2=backup, 3=emergency)
                assets_sorted = sorted(assets, key=lambda x: x.get("priority", 99))

                scene_clips = []
                scene_clips_duration = 0.0
                used_asset_indices = set()  # Track které assety už byly použity
                used_subclip_ranges = {}  # Track které úseky už byly použity per asset

                # Pokračuj dokud nemáme dostatečnou délku
                asset_idx = 0
                while scene_clips_duration < target_scene_duration and asset_idx < len(assets_sorted):
                    selected_asset = assets_sorted[asset_idx]
                    asset_id = selected_asset.get("archive_item_id", "")

                    # Download asset (jen jednou)
                    source_file = self.download_asset(selected_asset)
                    if not source_file:
                        print(f"⚠️  CB: Failed to download asset {asset_id}, trying next")
                        asset_idx += 1
                        continue

                    # Inicializuj tracking pro tento asset
                    if asset_id not in used_subclip_ranges:
                        used_subclip_ranges[asset_id] = []

                    # Zkus najít další subclip z tohoto assetu
                    recommended_subclips = selected_asset.get("recommended_subclips", [])

                    # Pokud nemáme recommended_subclips, vytvoř default
                    if not recommended_subclips:
                        # Zkus zjistit délku videa
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
                                    source_file,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )
                            video_duration = float(result.stdout.strip())
                        except Exception:
                            video_duration = 30.0  # Fallback

                        # Vytvoř subclip z dostupné části
                        clip_length = min(5.0, target_scene_duration - scene_clips_duration, video_duration)
                        if clip_length > 0:
                            recommended_subclips = [{"in_sec": 0, "out_sec": clip_length, "reason": "Default"}]

                    # Najdi subclip, který ještě nebyl použit
                    subclip_used = None
                    for subclip in recommended_subclips:
                        in_sec = subclip.get("in_sec", 0)
                        out_sec = subclip.get("out_sec", 5)
                        subclip_range = (in_sec, out_sec)

                        # Zkontroluj, jestli tento úsek už nebyl použit
                        if subclip_range not in used_subclip_ranges[asset_id]:
                            subclip_used = subclip
                            used_subclip_ranges[asset_id].append(subclip_range)
                            break

                    # Pokud všechny recommended_subclips byly použity, zkus vytvořit nový úsek
                    if subclip_used is None:
                        # Najdi další dostupný úsek z tohoto assetu
                        clip_length_range = [4, 7]  # Default z shot_strategy
                        clip_length = min(clip_length_range[1], target_scene_duration - scene_clips_duration)

                        if clip_length > 0:
                            # Najdi volný úsek (posuň se dopředu)
                            last_used_out = max([out for _, out in used_subclip_ranges[asset_id]], default=0)
                            new_in = last_used_out + 1.0  # Gap 1s
                            new_out = new_in + clip_length

                            # Zkontroluj, jestli máme dost místa v assetu
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
                                        source_file,
                                    ],
                                    capture_output=True,
                                    text=True,
                                    timeout=10,
                                )
                                video_duration = float(result.stdout.strip())
                            except Exception:
                                video_duration = 30.0

                            if new_out <= video_duration:
                                subclip_used = {
                                    "in_sec": new_in,
                                    "out_sec": new_out,
                                    "reason": f"Additional segment from {asset_id}",
                                }
                                used_subclip_ranges[asset_id].append((new_in, new_out))
                            else:
                                # Asset je vyčerpán, zkus další asset
                                asset_idx += 1
                                continue
                        else:
                            # Už máme dostatek, break
                            break

                    if subclip_used:
                        # Vytvoř subclip
                        in_sec = subclip_used.get("in_sec", 0)
                        out_sec = subclip_used.get("out_sec", 5)

                        # Pokud je to poslední subclip a potřebujeme přesně target_duration, ořízni
                        remaining = target_scene_duration - scene_clips_duration
                        if remaining < (out_sec - in_sec):
                            out_sec = in_sec + remaining

                        subclip_duration = out_sec - in_sec
                        if subclip_duration <= 0:
                            asset_idx += 1
                            continue

                        clip_counter = len(scene_clips) + 1
                        subclip_filename = f"scene_{scene_id}_clip_{clip_counter:02d}.mp4"
                        subclip_path = os.path.join(self.storage_dir, subclip_filename)

                        success = self.create_subclip(
                            source_file,
                            in_sec,
                            out_sec,
                            subclip_path,
                            target_fps=target_fps,
                            resolution=resolution,
                        )

                        if success:
                            # CRITICAL: Validate clip has actual video stream before adding
                            if not has_video_stream(subclip_path):
                                print(f"❌ INVALID CLIP (NO VIDEO STREAM): {subclip_path}")
                                print(f"   Scene {scene_id}, clip {clip_counter} - REJECTING clip without video stream")
                                # Do not append to scene_clips - this would create black screen
                                continue
                            
                            scene_clips.append(subclip_path)
                            scene_clips_duration += subclip_duration
                            clips_metadata.append(
                                {
                                    "scene_id": scene_id,
                                    "asset_id": asset_id,
                                    "subclip_file": subclip_path,
                                    "in_sec": in_sec,
                                    "out_sec": out_sec,
                                    "duration": subclip_duration,
                                    "reason": subclip_used.get("reason", ""),
                                }
                            )
                            print(
                                f"   ✅ Added subclip {clip_counter}: {subclip_duration:.1f}s "
                                f"(total: {scene_clips_duration:.1f}s / {target_scene_duration:.1f}s)"
                            )
                        else:
                            print(f"   ⚠️  Failed to create subclip from {asset_id}")

                    # Pokud jsme dosáhli target_duration, break
                    if scene_clips_duration >= target_scene_duration:
                        break

                    # Pokud jsme vyčerpali všechny subclips z tohoto assetu, zkus další
                    if subclip_used is None:
                        asset_idx += 1

                # Přidej všechny klipy z této scény
                for clip_path in scene_clips:
                    all_clips.append(clip_path)

                # Metadata pro scénu
                scene_clips_metadata = [c for c in clips_metadata if c.get("scene_id") == scene_id]
                scenes_metadata.append(
                    {
                        "scene_id": scene_id,
                        "scene_target_duration_sec": target_scene_duration,
                        "scene_actual_duration_sec": scene_clips_duration,
                        "subclips_count": len(scene_clips),
                        "clips_metadata": scene_clips_metadata,
                    }
                )

                print(
                    f"   ✅ Scene {scene_id} complete: {scene_clips_duration:.1f}s / "
                    f"{target_scene_duration:.1f}s ({len(scene_clips)} subclips)"
                )
        
        # Najdi MP3 soubory pro voiceover (per-episode: projects/<ep>/voiceover/*.mp3)
        audio_file = None
        episode_dir = os.path.dirname(self.storage_dir)  # projects/ep_xxx/
        import glob
        voiceover_dir = os.path.join(episode_dir, "voiceover")
        mp3_files = sorted(glob.glob(os.path.join(voiceover_dir, "*.mp3")))
        
        if mp3_files:
            print(f"🎤 CB: Found {len(mp3_files)} MP3 files for voiceover")
            # Spojit MP3 soubory do jednoho (re-encode to AAC for reliability)
            combined_audio_path = os.path.join(self.storage_dir, "combined_voiceover.m4a")
            
            try:
                # Vytvoř concat file pro audio
                audio_concat_file = os.path.join(
                    self.storage_dir,
                    f"audio_concat_list_{int(time.time()*1000)}_{os.getpid()}.txt",
                )
                with open(audio_concat_file, 'w', encoding='utf-8') as f:
                    for mp3 in mp3_files:
                        f.write(f"file '{os.path.realpath(os.path.abspath(mp3))}'\n")
                
                # Spojit MP3 soubory pomocí FFmpeg
                concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", audio_concat_file,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    combined_audio_path
                ]
                
                result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0 and os.path.exists(combined_audio_path):
                    audio_file = combined_audio_path
                    print(f"✅ CB: Combined audio created: {audio_file}")
                else:
                    print(f"⚠️  CB: Failed to combine audio: {result.stderr}")
            except Exception as e:
                print(f"⚠️  CB: Error combining audio: {e}")
        else:
            print(f"⚠️  CB: No MP3 files found in {voiceover_dir} - will create minimal silent video (NO ERROR)")
            audio_file = None

        # ========================================================================
        # HARD VALIDATION: Check visual coverage before proceeding to render
        # ========================================================================
        clips_count = len(all_clips)
        beats_count = len(beats) if beats else len(scenes)
        coverage_percent = (100.0 * clips_count / beats_count) if beats_count > 0 else 0.0
        
        MIN_COVERAGE_PERCENT = 50.0  # Minimum 50% visual coverage required
        
        print(f"📊 CB: Visual coverage: {clips_count}/{beats_count} beats ({coverage_percent:.1f}%)")
        print(f"📊 CB: Black fallbacks used: {fallback_count}")
        
        # ========================================================================
        # CRITICAL: NO BLACK FALLBACKS POLICY
        # User has repeatedly requested: NEVER create black fallback clips.
        # If we have zero clips, we MUST fail compilation, not inject black screens.
        # ========================================================================
        if not all_clips:
            error_detail = {
                "error": "CB_CRITICAL_NO_VISUAL_ASSETS",
                "reason": "Zero visual clips were created from manifest assets. BLACK FALLBACKS ARE DISABLED.",
                "total_beats": beats_count,
                "clips_created": 0,
                "policy": "NO_BLACK_FALLBACKS - Compilation fails if no valid visuals found",
                "debug_info": cb_debug_info,
            }
            print(f"❌ CB CRITICAL FAILURE (NO FALLBACKS): {json.dumps(error_detail, indent=2)}")
            return None, error_detail
        
        # OLD CODE (DISABLED - kept for reference):
        # if not all_clips:
        #     try:
        #         enable_safety_pack = str(os.getenv("CB_ENABLE_SAFETY_PACK_FALLBACK", "0")).strip().lower() in ("1", "true", "yes")
        #         subclip_path = os.path.join(self.storage_dir, f"black_fallback_{episode_id}.mp4")
        #
        #                 # (OLD BLACK FALLBACK CODE - PERMANENTLY DISABLED)
        #         if enable_safety_pack:
        #             ...safety pack code...
        #         else:
        #             ...black screen creation code...
        # REMOVED: User explicitly forbids black fallbacks
        
        # Coverage is informative only in v3 (never-fail). Low coverage → warnings, continue.
        if coverage_percent < MIN_COVERAGE_PERCENT:
            print(f"⚠️  CB: Low visual coverage ({coverage_percent:.1f}% < {MIN_COVERAGE_PERCENT}%), continuing (never-fail policy)")
        
        if coverage_percent >= MIN_COVERAGE_PERCENT:
            print(f"✅ CB: Visual coverage validation passed ({coverage_percent:.1f}% >= {MIN_COVERAGE_PERCENT}%)")

        # Background music (priority: selected_global_music > per-episode > auto-select global)
        # Voiceover is reference (0 dB). Background music gain is configurable via script_state.json.
        # Load default from global preferences (persists across sessions)
        music_gain_db = -18.0  # fallback if settings_store unavailable
        try:
            from settings_store import SettingsStore
            settings_store = SettingsStore(
                base_dir=os.path.dirname(os.path.dirname(self.storage_dir)),  # podcasts/
                backend_dir=os.path.join(os.path.dirname(os.path.dirname(self.storage_dir)), "backend")
            )
            music_gain_db = settings_store.get_music_bg_gain_db()
            print(f"🎵 CB: Loaded default music gain from global preferences: {music_gain_db} dB")
        except Exception as e:
            print(f"⚠️  CB: Could not load global music gain preference, using fallback: {e}")
        
        music_report = {"enabled": False, "selected_track": None}
        try:
            from global_music_store import load_global_music_manifest, get_music_file_path, select_music_auto
            
            episode_dir = os.path.dirname(self.storage_dir)  # projects/ep_xxx/
            
            # 1) Check if user selected global music via script_state
            selected_global = None
            state_path = os.path.join(episode_dir, "script_state.json")
            if os.path.exists(state_path):
                try:
                    with open(state_path, "r", encoding="utf-8") as f:
                        state = json.load(f)
                        selected_global = state.get("selected_global_music")
                        # Optional: background music gain (in dB). Typical safe range: -40..-6
                        raw_gain = state.get("music_bg_gain_db")
                        if raw_gain is not None:
                            try:
                                g = float(raw_gain)
                                # Clamp to avoid extreme values; UI typically limits further.
                                g = max(-60.0, min(0.0, g))
                                music_gain_db = g
                                # Save to global preferences for future projects
                                try:
                                    settings_store.set_music_bg_gain_db(g)
                                    print(f"🎵 CB: Saved music gain {g} dB to global preferences")
                                except Exception as save_err:
                                    print(f"⚠️  CB: Could not save gain to global prefs: {save_err}")
                            except Exception:
                                pass
                except Exception:
                    pass
            
            chosen = None
            music_path = None
            
            # Priority 1: User-selected global music
            if selected_global and isinstance(selected_global, dict):
                chosen = selected_global
                music_path = get_music_file_path(secure_filename(chosen.get("filename")))
                if music_path and os.path.exists(music_path):
                    print(f"🎵 CB: Using user-selected global music: {chosen.get('filename')}")
                else:
                    chosen = None
                    music_path = None
            
            # Priority 2: Per-episode music (legacy)
            if not chosen:
                music_manifest_path = os.path.join(episode_dir, "assets", "music", "music_manifest.json")
                if os.path.exists(music_manifest_path):
                    with open(music_manifest_path, "r", encoding="utf-8") as f:
                        mm = json.load(f)
                    tracks = mm.get("tracks") if isinstance(mm, dict) else None
                    tracks = tracks if isinstance(tracks, list) else []
                    active_tracks = [t for t in tracks if isinstance(t, dict) and t.get("active") is True and t.get("filename")]

                    if active_tracks:
                        # Choose by predominant emotion if possible (MVP heuristic)
                        emotion_counts = {}
                        for sc in scenes:
                            emo = sc.get("emotion")
                            if isinstance(emo, str) and emo.strip():
                                emotion_counts[emo.strip().lower()] = emotion_counts.get(emo.strip().lower(), 0) + 1
                        predominant = None
                        if emotion_counts:
                            predominant = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)[0][0]
                        tag_pref = "neutral"
                        if predominant in ("tension", "tragedy", "mystery"):
                            tag_pref = "dark"
                        elif predominant in ("hope", "victory"):
                            tag_pref = "hopeful"

                        tagged = [t for t in active_tracks if str(t.get("tag") or "").strip().lower() == tag_pref]
                        pool = tagged if tagged else active_tracks
                        chosen = random.choice(pool)

                        music_path = os.path.join(episode_dir, "assets", "music", secure_filename(chosen.get("filename")))
                        if os.path.exists(music_path):
                            print(f"🎵 CB: Using per-episode music: {chosen.get('filename')}")
                        else:
                            chosen = None
                            music_path = None
            
            # Priority 3: Auto-select from global library
            if not chosen:
                print(f"🎵 CB: No per-episode music found, trying auto-select from global library")
                # Determine mood from scenes
                emotion_counts = {}
                for sc in scenes:
                    emo = sc.get("emotion")
                    if isinstance(emo, str) and emo.strip():
                        emotion_counts[emo.strip().lower()] = emotion_counts.get(emo.strip().lower(), 0) + 1
                
                preferred_mood = "neutral"
                preferred_tags = []
                
                if emotion_counts:
                    predominant = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)[0][0]
                    if predominant in ("tension", "tragedy", "mystery"):
                        preferred_mood = "dark"
                        preferred_tags = ["cinematic", "dramatic"]
                    elif predominant in ("hope", "victory"):
                        preferred_mood = "uplifting"
                        preferred_tags = ["ambient", "electronic"]
                    else:
                        preferred_mood = "peaceful"
                        preferred_tags = ["ambient", "minimal"]
                
                print(f"   Preferred mood: {preferred_mood}, tags: {preferred_tags}")
                chosen = select_music_auto(
                    preferred_mood=preferred_mood,
                    preferred_tags=preferred_tags,
                    # IMPORTANT: do NOT filter by duration.
                    # We loop background music with FFmpeg (-stream_loop -1), so even short tracks work.
                    min_duration_sec=None
                )
                
                if chosen:
                    music_path = get_music_file_path(secure_filename(chosen.get("filename")))
                    if music_path and os.path.exists(music_path):
                        print(f"🎵 CB: Auto-selected global music: {chosen.get('filename')} (mood={preferred_mood})")
                    else:
                        chosen = None
                        music_path = None
                        print(f"⚠️  CB: Auto-selected music file not found: {chosen.get('filename') if chosen else 'N/A'}")
                else:
                    print(f"⚠️  CB: No global music found for mood={preferred_mood}")
            
            if not chosen:
                print(f"⚠️  CB: No background music available - video will have voiceover only")
            
            # Mix music if chosen
            if chosen and music_path and os.path.exists(music_path):
                print(f"🎵 CB: Attempting to mix background music...")
                print(f"   Music file: {music_path}")
                print(f"   Audio file (voiceover): {audio_file}")
                
                # Compute voiceover duration
                vo_dur = None
                try:
                    r = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", audio_file],
                        capture_output=True, text=True, timeout=10
                    )
                    if r.returncode == 0 and (r.stdout or "").strip():
                        vo_dur = float((r.stdout or "").strip())
                        print(f"   Voiceover duration: {vo_dur:.2f}s")
                except Exception as e:
                    print(f"   ⚠️  Failed to probe voiceover duration: {e}")
                    vo_dur = None

                if vo_dur and vo_dur > 0:
                    fade = 1.5
                    if vo_dur < 6:
                        fade = 1.0
                    fade = max(1.0, min(2.0, fade))
                    fade_out_start = max(0.0, vo_dur - fade)
                    mixed_audio_path = os.path.join(self.storage_dir, "combined_voiceover_with_music.m4a")

                    # Voiceover is reference (0 dB). Music at configurable dB, with fade-in/out.
                    cmd = [
                        "ffmpeg", "-y", "-i", audio_file,
                        "-stream_loop", "-1", "-i", music_path,
                        "-filter_complex",
                        (f"[1:a]volume={music_gain_db}dB,"
                         f"afade=t=in:st=0:d={fade},"
                         f"afade=t=out:st={fade_out_start}:d={fade}[bg];"
                         f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[a]"),
                        "-map", "[a]", "-vn", "-c:a", "aac", "-b:a", "192k",
                        "-t", str(vo_dur), mixed_audio_path
                    ]
                    print(f"   Running FFmpeg command: {' '.join(cmd[:5])}...")
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    if result.returncode == 0 and os.path.exists(mixed_audio_path) and os.path.getsize(mixed_audio_path) > 0:
                        audio_file = mixed_audio_path
                        music_report = {
                            "enabled": True,
                            "selected_track": {
                                "filename": chosen.get("filename"),
                                "mood": chosen.get("mood", chosen.get("tag")),  # Fallback to tag for legacy
                                "tags": chosen.get("tags", []),
                                "gain_db": music_gain_db,
                                "fade_in_sec": fade,
                                "fade_out_sec": fade,
                            },
                        }
                        print(f"🎵 CB: Background music mixed in: {chosen.get('filename')}")
                    else:
                        # FFmpeg mixing failed
                        print(f"❌ CB: FFmpeg music mixing failed (return code: {result.returncode})")
                        print(f"   stderr: {result.stderr[:500]}")
                        print(f"   Audio file will NOT have background music")
        except Exception as e:
            print(f"⚠️  CB: Background music mix skipped: {e}")
            import traceback
            traceback.print_exc()
        
        # ========================================================================
        # FINAL GUARD: Verify all clips have valid video streams before concat
        # ========================================================================
        print(f"🔍 CB: Validating {len(all_clips)} clips have video streams...")
        invalid_clips = []
        for clip_path in all_clips:
            if not has_video_stream(clip_path):
                invalid_clips.append(clip_path)
                print(f"❌ CRITICAL: Clip without video stream detected: {clip_path}")
        
        if invalid_clips:
            error_detail = {
                "error": "CB_INVALID_CLIPS_NO_VIDEO_STREAM",
                "reason": "Attempted to concatenate clips without video streams - would result in black screen",
                "invalid_clips_count": len(invalid_clips),
                "total_clips": len(all_clips),
                "invalid_clips": [os.path.basename(c) for c in invalid_clips[:5]]  # First 5 for debugging
            }
            print(f"❌ CB CRITICAL FAILURE: {json.dumps(error_detail, indent=2)}")
            raise RuntimeError(
                f"Attempted to concat {len(invalid_clips)} clips without video streams. "
                "This would create black screen output. Failing immediately."
            )
        
        print(f"✅ CB: All {len(all_clips)} clips validated - have video streams")
        
        # Emit assembly phase progress
        self._progress_state["phase"] = "assembly"
        self._emit_progress(
            "assembly",
            f"🎬 Finalizuji video: spojuji {len(all_clips)} klipů...",
            90.0,
            total_clips=len(all_clips),
            has_audio=bool(audio_file),
        )
        
        # Concatenate všechny klipy s audio
        success = self.concatenate_clips(all_clips, output_path, target_fps, resolution, audio_file)
        
        if not success:
            return None, {
                "error": "Concatenation failed",
                "details": getattr(self, "_last_concat_error", None),
            }
        
        # Metadata s compilation_report
        # NEW: Calculate extended stats
        unique_assets_used = set()
        subclips_per_beat_list = []
        beat_to_subclips = {}
        
        for clip in clips_metadata:
            asset_id = clip.get("asset_id")
            if asset_id and not asset_id.startswith("fallback_"):
                unique_assets_used.add(asset_id)
            block_id = clip.get("block_id")
            if block_id:
                beat_to_subclips.setdefault(block_id, []).append(clip)
        
        for block_id, subclipy in beat_to_subclips.items():
            subclips_per_beat_list.append(len(subclipy))
        
        avg_subclips_per_beat = sum(subclips_per_beat_list) / len(subclips_per_beat_list) if subclips_per_beat_list else 0
        reuse_ratio = len(beats) / len(unique_assets_used) if unique_assets_used and use_beats else 0
        
        metadata = {
            "timestamp": _now_iso(),
            "episode_id": episode_id,
            "output_file": output_path,
            "total_scenes": len(scenes),
            "clips_used": len(all_clips),
            "compile_plan": compile_plan,
            "output_size_bytes": os.path.getsize(output_path) if os.path.exists(output_path) else 0,
            "compilation_report": {
                "scenes": scenes_metadata,
                "total_target_duration_sec": sum((s.get("scene_target_duration_sec") or 0) for s in scenes_metadata),
                "total_actual_duration_sec": sum((s.get("scene_actual_duration_sec") or 0) for s in scenes_metadata),
                "total_subclips": sum((s.get("subclips_count") or 0) for s in scenes_metadata),
                "music": music_report,
                "visual_beats": {
                    "mode": "block_level" if use_beats else "scene_level",
                    "beats_count": len(beats) if use_beats else None,
                },
                # NEW: Extended stats
                "unique_assets_used": len(unique_assets_used),
                "reuse_ratio": round(reuse_ratio, 2),
                "avg_subclips_per_beat": round(avg_subclips_per_beat, 2),
                "subclips_per_beat_distribution": subclips_per_beat_list,
            }
        }
        
        # Save compilation_report.json
        report_path = os.path.join(os.path.dirname(output_path), f"compilation_report_{episode_id}_{timestamp}.json")
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(metadata["compilation_report"], f, ensure_ascii=False, indent=2)
            print(f"📊 CB: Compilation report saved to {report_path}")
        except Exception as e:
            print(f"⚠️  CB: Failed to save compilation report: {e}")
        
        total_target = metadata["compilation_report"]["total_target_duration_sec"]
        total_actual = metadata["compilation_report"]["total_actual_duration_sec"]
        print(f"✅ CB: Compilation complete → {output_path}")
        print(f"   Duration: {total_actual:.1f}s / {total_target:.1f}s (target)")
        print(f"   Total subclips: {metadata['compilation_report']['total_subclips']}")
        
        # Emit final done progress
        self._progress_state["phase"] = "done"
        self._emit_progress(
            "done",
            f"✅ Video hotovo! {total_actual:.0f}s, {metadata['compilation_report']['total_subclips']} klipů",
            100.0,
            output_file=output_path,
            duration_sec=total_actual,
            total_subclips=metadata['compilation_report']['total_subclips'],
        )
        
        return output_path, metadata


def build_episode_compilation(
    manifest_path: str,
    episode_id: str,
    storage_dir: str,
    output_dir: str,
    target_duration_sec: Optional[float] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Entry point pro CB krok v pipeline.
    
    Args:
        manifest_path: Cesta k archive_manifest.json
        episode_id: ID epizody
        storage_dir: Cache storage pro downloads
        output_dir: Output složka pro finální video
        target_duration_sec: Target délka (optional)
        progress_callback: Optional callback for real-time progress updates
    
    Returns:
        (output_video_path, metadata)
    """
    builder = CompilationBuilder(storage_dir, output_dir, progress_callback=progress_callback)
    return builder.build_compilation(manifest_path, episode_id, target_duration_sec)

