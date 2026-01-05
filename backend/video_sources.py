"""
Video Sources - abstraktní interface a konkrétní providery pro multi-source video search.

Podporované zdroje:
- Archive.org (movies/movingimage)
- Wikimedia Commons (video files)
- Europeana (video records)
- Stock providers (optional, API key required): Pexels, Pixabay

Všechny zdroje MUSÍ vracet pouze legally usable content (PD / CC-BY / CC-BY-SA).
"""

import requests
import time
import os
from urllib.parse import urlencode
from typing import Dict, List, Any, Optional, Tuple
from abc import ABC, abstractmethod


# === YOUTUBE-SAFE LICENCE WHITELIST ===
# Pouze licence, které lze legálně použít na YouTube (včetně monetizace)
YOUTUBE_SAFE_LICENSES = {
    "public_domain",
    "cc0",
    "pd",
    "cc-by",
    "cc-by-2.0",
    "cc-by-3.0",
    "cc-by-4.0",
    "cc-by-sa",
    "cc-by-sa-2.0",
    "cc-by-sa-3.0",
    "cc-by-sa-4.0",
    # Stock providers (explicitly enabled by API key presence)
    "pexels",
    "pixabay",
}

# Licence priority pro scoring (PD/CC0 preferovanější než CC-BY)
LICENSE_PRIORITY = {
    "public_domain": 10,
    "cc0": 10,
    "pd": 10,
    "cc-by": 5,
    "cc-by-sa": 5,
    # Stock (high quality, but not archival)
    "pexels": 6,
    "pixabay": 6,
    # Unknown license is discouraged (kept low priority), but can be optionally allowed as a last resort
    # to avoid "0 results" episodes. Downstream can surface warnings to the user.
    "unknown": 0,
}


class VideoSource(ABC):
    """
    Abstraktní base class pro video source providery.
    """
    
    def __init__(self, throttle_delay_sec: float = 0.2, verbose: bool = False, timeout_sec: float = 12):
        self.throttle_delay_sec = throttle_delay_sec
        self.last_request_time = 0.0
        self.verbose = verbose
        self.source_name = self.__class__.__name__
        # Telemetry for circuit-breakers / diagnostics (set by subclasses)
        self.last_http_status: Optional[int] = None
        self.last_error: Optional[str] = None
        try:
            self.timeout_sec = float(timeout_sec)
        except Exception:
            self.timeout_sec = 12.0
    
    def _throttle(self) -> None:
        """Rate limiting mezi requesty"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.throttle_delay_sec:
            time.sleep(self.throttle_delay_sec - elapsed)
        self.last_request_time = time.time()

    def _record_success(self, http_status: Optional[int] = None) -> None:
        self.last_http_status = int(http_status) if isinstance(http_status, int) else http_status
        self.last_error = None

    def _record_error(self, http_status: Optional[int], err: Exception) -> None:
        try:
            self.last_http_status = int(http_status) if isinstance(http_status, int) else http_status
        except Exception:
            self.last_http_status = None
        self.last_error = str(err)
    
    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Vyhledá videa podle query.
        
        Returns:
            List of standardized video items:
            {
                "source": "archive_org" | "wikimedia" | "europeana",
                "item_id": str,
                "title": str,
                "description": str,
                "url": str,
                "license": str,  # normalized (public_domain, cc-by, cc-by-sa, unknown)
                "license_raw": str,  # original from API
                "attribution": str | None,  # required for CC-BY
                "thumbnail_url": str | None,
                "duration_sec": float | None,
                "downloads": int | None,  # popularity proxy
            }
        """
        pass
    
    @abstractmethod
    def get_download_url(self, item_id: str) -> Optional[str]:
        """
        Vrátí direct download URL pro video item.
        """
        pass


class ArchiveOrgSource(VideoSource):
    """
    Archive.org movies/movingimage search.
    Stejná logika jako současný AAR, ale s explicitním licence checkingem.
    """
    
    def __init__(
        self,
        throttle_delay_sec: float = 0.2,
        verbose: bool = False,
        timeout_sec: float = 12,
        allow_unknown_license_fallback: bool = False,
    ):
        super().__init__(throttle_delay_sec, verbose, timeout_sec=timeout_sec)
        self.base_url = "https://archive.org/advancedsearch.php"
        self.allow_unknown_license_fallback = bool(allow_unknown_license_fallback)
    
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search archive.org for videos matching query.
        """
        q_expr = f"({query}) AND mediatype:(movies OR movingimage)"
        params = {
            "q": q_expr,
            "fl[]": ["identifier", "title", "description", "licenseurl", "downloads", "date", "mediatype", "collection", "subject", "creator"],
            "rows": min(max_results, 50),
            "output": "json",
            # NO SORT = default relevance sort (better for topic-specific queries)
            # "sort[]": "downloads desc",  # REMOVED: popularity sort returns off-topic mega-popular videos
        }
        
        try:
            self._throttle()
            resp = requests.get(self.base_url, params=params, timeout=self.timeout_sec, verify=False)
            self._record_success(resp.status_code)
            resp.raise_for_status()
            data = resp.json() or {}
            docs = data.get("response", {}).get("docs", []) or []
            
            # #region agent log
            try:
                import time as _time, json as _json
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps({
                        "sessionId": "debug-session", "runId": "aar-v1", "hypothesisId": "API-1",
                        "location": "backend/video_sources.py:ArchiveOrgSource.search",
                        "message": "Archive.org API call + response",
                        "data": {
                            "query": query[:120], "q_expr": q_expr[:180],
                            "response_status": resp.status_code,
                            "docs_returned": len(docs),
                            "numFound": data.get("response", {}).get("numFound"),
                        },
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            
            safe_results = []
            unknown_results = []
            dropped_mediatype = 0
            for doc in docs:
                item_id = doc.get("identifier", "")
                if not item_id:
                    continue
                
                # Mediatype filter (VIDEO context: only "movies" allowed, fail-closed)
                mediatype = str(doc.get("mediatype", "")).strip().lower()
                if not mediatype:
                    dropped_mediatype += 1
                    if self.verbose:
                        print(f"  🚫 Archive.org: Dropped {item_id} (DROP_UNKNOWN_MEDIATYPE)")
                    continue
                if mediatype not in ("movies", "movingimage"):
                    dropped_mediatype += 1
                    if self.verbose:
                        print(f"  🚫 Archive.org: Dropped {item_id} (DROP_MEDIATYPE_NOT_ALLOWED: {mediatype})")
                    continue
                
                license_raw = str(doc.get("licenseurl", "")).strip()
                license_normalized = self._normalize_license(license_raw)
                
                # LICENCE GATE: pouze YouTube-safe licence
                if license_normalized not in YOUTUBE_SAFE_LICENSES:
                    # Collect unknown separately; optionally allow only if nothing safe exists.
                    if license_normalized == "unknown":
                        unknown_results.append({
                            "source": "archive_org",
                            "item_id": item_id,
                            "title": str(doc.get("title", "Untitled"))[:240],
                            "description": str(doc.get("description", ""))[:1200],
                            "url": f"https://archive.org/details/{item_id}",
                            "license": license_normalized,
                            "license_raw": license_raw,
                            "attribution": None,  # Archive.org usually PD
                            "thumbnail_url": f"https://archive.org/services/img/{item_id}",
                            "duration_sec": None,  # Need metadata fetch
                            "downloads": int(doc.get("downloads", 0) or 0),
                            "mediatype": mediatype,
                            "collection": str(doc.get("collection", ""))[:400],
                            "subject": str(doc.get("subject", ""))[:400],
                            "creator": str(doc.get("creator", ""))[:200],
                        })
                        continue
                    if self.verbose:
                        print(f"⚠️  Archive.org: Skipping {item_id} (unsafe license: {license_normalized})")
                    continue
                
                safe_results.append({
                    "source": "archive_org",
                    "item_id": item_id,
                    "title": str(doc.get("title", "Untitled"))[:240],
                    "description": str(doc.get("description", ""))[:1200],
                    "url": f"https://archive.org/details/{item_id}",
                    "license": license_normalized,
                    "license_raw": license_raw,
                    "attribution": None,  # Archive.org usually PD
                    "thumbnail_url": f"https://archive.org/services/img/{item_id}",
                    "duration_sec": None,  # Need metadata fetch
                    "downloads": int(doc.get("downloads", 0) or 0),
                    "mediatype": mediatype,
                    "collection": str(doc.get("collection", ""))[:400],
                    "subject": str(doc.get("subject", ""))[:400],
                    "creator": str(doc.get("creator", ""))[:200],
                })

            # #region agent log
            try:
                import time as _time, json as _json
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps({
                        "sessionId": "debug-session", "runId": "aar-v1", "hypothesisId": "API-2",
                        "location": "backend/video_sources.py:ArchiveOrgSource.search",
                        "message": "Archive.org license gate filtering",
                        "data": {
                            "query": query[:120],
                            "safe_results": len(safe_results),
                            "unknown_results": len(unknown_results),
                            "allow_unknown_fallback": self.allow_unknown_license_fallback,
                        },
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            
            # Telemetry: mediatype filter
            if dropped_mediatype > 0 and self.verbose:
                total_before = len(docs)
                total_after = len(safe_results) + len(unknown_results)
                print(f"📊 Archive.org Mediatype Filter: before={total_before}, after={total_after}, dropped={dropped_mediatype}")
            
            if safe_results:
                return safe_results[:max_results]

            # Optional: if nothing passes strict license gate, allow unknown as a last resort
            if self.allow_unknown_license_fallback and unknown_results:
                if self.verbose:
                    print(f"⚠️  Archive.org: No YouTube-safe results for '{query[:40]}', allowing UNKNOWN license fallback ({len(unknown_results)} items)")
                return unknown_results[:max_results]

            return []
        
        except Exception as e:
            # Best-effort: if the exception has a response, store status code
            status = None
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            self._record_error(status, e)
            if self.verbose:
                print(f"⚠️  Archive.org search error: {e}")
            return []
    
    def get_download_url(self, item_id: str) -> Optional[str]:
        """
        Vrátí URL pro MP4 download z archive.org.
        """
        return f"https://archive.org/download/{item_id}/{item_id}.mp4"
    
    def _normalize_license(self, license_url: str) -> str:
        """
        Normalizuje archive.org licenseurl na standardní kategorie.
        """
        if not license_url:
            return "unknown"
        
        l = license_url.lower()
        
        if "publicdomain" in l or "public-domain" in l or "pd" in l:
            return "public_domain"
        if "cc0" in l or "zero" in l:
            return "cc0"
        if "creativecommons.org/licenses/by-sa" in l:
            return "cc-by-sa"
        if "creativecommons.org/licenses/by" in l:
            return "cc-by"
        
        return "unknown"


class WikimediaSource(VideoSource):
    """
    Wikimedia Commons video search via MediaWiki API.
    Obrovský zdroj historických videí, map, ilustrací.
    """
    
    def __init__(self, throttle_delay_sec: float = 0.2, verbose: bool = False, timeout_sec: float = 12):
        super().__init__(throttle_delay_sec, verbose, timeout_sec=timeout_sec)
        self.api_url = "https://commons.wikimedia.org/w/api.php"
    
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search Wikimedia Commons for videos.
        Uses MediaWiki API with generator=search.
        """
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            # NOTE: Commons CirrusSearch supports filemime:* filters, not filetype:video.
            # filemime:video returns real video files in File: namespace.
            "gsrsearch": f"filemime:video {query}",
            "gsrnamespace": 6,  # File: namespace
            "gsrlimit": min(max_results, 50),
            "prop": "imageinfo|info",
            "iiprop": "url|size|mediatype|extmetadata",
            "iiurlwidth": 320,
        }
        
        # CRITICAL: Wikimedia requires proper User-Agent to avoid 403
        headers = {
            "User-Agent": "PodcastVideoBot/1.0 (Educational/Documentary video research; contact: research@example.com)"
        }
        
        try:
            self._throttle()
            resp = requests.get(self.api_url, params=params, headers=headers, timeout=self.timeout_sec, verify=False)
            self._record_success(resp.status_code)
            resp.raise_for_status()
            data = resp.json() or {}
            pages = data.get("query", {}).get("pages", {}) or {}
            
            results = []
            for page_id, page in pages.items():
                if page_id == "-1":  # Invalid page
                    continue
                
                title = page.get("title", "")
                imageinfo = page.get("imageinfo", [])
                if not imageinfo:
                    continue
                
                info = imageinfo[0]
                
                # Extract license from extmetadata
                extmeta = info.get("extmetadata", {})
                license_raw = extmeta.get("LicenseShortName", {}).get("value", "")
                license_normalized = self._normalize_license(license_raw)
                
                # LICENCE GATE
                if license_normalized not in YOUTUBE_SAFE_LICENSES:
                    if self.verbose:
                        print(f"⚠️  Wikimedia: Skipping {title} (unsafe license: {license_normalized})")
                    continue
                
                # Attribution (required for CC-BY)
                attribution = None
                if license_normalized.startswith("cc-by"):
                    artist = extmeta.get("Artist", {}).get("value", "")
                    attribution = artist if artist else "Wikimedia Commons"
                
                results.append({
                    "source": "wikimedia",
                    "item_id": title.replace("File:", "").replace(" ", "_"),
                    "title": title,
                    "description": extmeta.get("ImageDescription", {}).get("value", "")[:1200],
                    # Use DIRECT media URL for fast downloading (CB can download without extra API call)
                    "url": info.get("url") or info.get("descriptionurl", ""),
                    "license": license_normalized,
                    "license_raw": license_raw,
                    "attribution": attribution,
                    "thumbnail_url": info.get("thumburl"),
                    "duration_sec": info.get("duration"),
                    "downloads": None,  # Wikimedia doesn't track downloads
                })
            
            return results
        
        except Exception as e:
            status = None
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            self._record_error(status, e)
            if self.verbose:
                print(f"⚠️  Wikimedia search error: {e}")
            return []
    
    def get_download_url(self, item_id: str) -> Optional[str]:
        """
        Vrátí direct download URL pro Wikimedia video.
        Musíme nejdřív získat imageinfo.
        """
        params = {
            "action": "query",
            "format": "json",
            "titles": f"File:{item_id}",
            "prop": "imageinfo",
            "iiprop": "url",
        }
        
        headers = {
            "User-Agent": "PodcastVideoBot/1.0 (Educational/Documentary video research; contact: research@example.com)"
        }
        
        try:
            resp = requests.get(self.api_url, params=params, headers=headers, timeout=self.timeout_sec, verify=False)
            resp.raise_for_status()
            data = resp.json() or {}
            resp.raise_for_status()
            data = resp.json() or {}
            pages = data.get("query", {}).get("pages", {}) or {}
            
            for page in pages.values():
                imageinfo = page.get("imageinfo", [])
                if imageinfo:
                    return imageinfo[0].get("url")
            
            return None
        
        except Exception:
            return None
    
    def _normalize_license(self, license_short: str) -> str:
        """
        Normalizuje Wikimedia licence název.
        """
        if not license_short:
            return "unknown"
        
        l = license_short.lower()
        
        if "public domain" in l or "pd" in l:
            return "public_domain"
        if "cc0" in l or "cc-zero" in l:
            return "cc0"
        if "cc-by-sa" in l or "cc by-sa" in l:
            return "cc-by-sa"
        if "cc-by" in l or "cc by" in l:
            return "cc-by"
        
        return "unknown"


class EuropeanaSource(VideoSource):
    """
    Europeana API - evropské kulturní dědictví.
    VYŽADUJE API KEY (získat na https://pro.europeana.eu/page/get-api).
    """
    
    def __init__(self, api_key: str, throttle_delay_sec: float = 0.5, verbose: bool = False, timeout_sec: float = 12):
        super().__init__(throttle_delay_sec, verbose, timeout_sec=timeout_sec)
        self.api_key = api_key
        self.api_url = "https://api.europeana.eu/record/v2/search.json"
    
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search Europeana for videos.
        """
        if not self.api_key or self.api_key == "EUROPEANA_API_KEY_HERE":
            if self.verbose:
                print("⚠️  Europeana: API key not configured, skipping")
            return []
        params = {
            "wskey": self.api_key,
            "query": query,
            "media": "true",        # Only items with media
            "qf": "TYPE:VIDEO",     # Only video type (Europeana also has images, but this source is 'video' oriented)
            "rows": min(max_results, 100),
            "profile": "rich",      # Include metadata
        }
        
        try:
            self._throttle()
            resp = requests.get(self.api_url, params=params, timeout=self.timeout_sec, verify=False)
            self._record_success(resp.status_code)
            resp.raise_for_status()
            data = resp.json() or {}
            items = data.get("items", []) or []
            
            results = []
            for item in items:
                item_id = item.get("id", "")
                if not item_id:
                    continue
                
                # Extract license
                rights = item.get("rights", [])
                if not rights:
                    continue
                
                license_raw = rights[0] if isinstance(rights, list) else str(rights)
                license_normalized = self._normalize_license(license_raw)
                
                # LICENCE GATE (YouTube-safe only)
                if license_normalized not in YOUTUBE_SAFE_LICENSES:
                    if self.verbose:
                        print(f"⚠️  Europeana: Skipping {item_id} (unsafe license: {license_normalized})")
                    continue
                
                # Attribution
                attribution = None
                if license_normalized.startswith("cc-by"):
                    dc_creator = item.get("dcCreator", [])
                    if dc_creator:
                        attribution = dc_creator[0] if isinstance(dc_creator, list) else str(dc_creator)
                
                title = item.get("title", ["Untitled"])
                title = title[0] if isinstance(title, list) else str(title)
                
                description = item.get("dcDescription", [""])
                description = description[0] if isinstance(description, list) else str(description)
                
                results.append(
                    {
                    "source": "europeana",
                    "item_id": item_id,
                    "title": title[:240],
                    "description": description[:1200],
                    "url": f"https://www.europeana.eu/item{item_id}",
                    "license": license_normalized,
                    "license_raw": license_raw,
                    "attribution": attribution,
                    "thumbnail_url": item.get("edmPreview", [None])[0] if item.get("edmPreview") else None,
                    "duration_sec": None,
                    "downloads": None,
                    }
                )
            
            return results
        
        except Exception as e:
            status = None
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            self._record_error(status, e)
            if self.verbose:
                print(f"⚠️  Europeana search error: {e}")
            return []

    def get_download_url(self, item_id: str) -> Optional[str]:
        """
        Europeana generally does NOT provide a single stable direct-download URL at search time.
        Download/playable URLs are resolved best-effort in CompilationBuilder via Europeana record API.
        """
        return None


class PexelsSource(VideoSource):
    """
    Pexels stock video search (high quality, fast CDN downloads).
    Requires env: PEXELS_API_KEY
    """

    def __init__(
        self,
        api_key: str,
        throttle_delay_sec: float = 0.2,
        verbose: bool = False,
        timeout_sec: float = 12,
        max_height: int = 1080,
    ):
        super().__init__(throttle_delay_sec, verbose, timeout_sec=timeout_sec)
        self.api_key = str(api_key or "").strip()
        self.max_height = int(max_height or 1080)
        self.search_url = "https://api.pexels.com/videos/search"

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        q = str(query or "").strip()
        if not q:
            return []

        params = {"query": q, "per_page": min(max_results, 30), "page": 1}
        headers = {"Authorization": self.api_key, "User-Agent": "PodcastVideoBot/1.0 (Documentary compilation)"}

        try:
            self._throttle()
            resp = requests.get(self.search_url, params=params, headers=headers, timeout=self.timeout_sec)
            self._record_success(resp.status_code)
            resp.raise_for_status()
            data = resp.json() or {}
            vids = data.get("videos", []) or []

            out: List[Dict[str, Any]] = []
            for v in vids:
                vid = v.get("id")
                if vid is None:
                    continue
                duration = v.get("duration")
                thumb = v.get("image")
                files = v.get("video_files", []) or []

                # Pick MP4 file up to max_height (prefer higher within limit)
                pick = None
                best_h = -1
                for f in files:
                    try:
                        if str(f.get("file_type") or "").lower() not in ("video/mp4", "mp4"):
                            continue
                        h = int(f.get("height") or 0)
                        link = str(f.get("link") or "").strip()
                        if not link:
                            continue
                        if h <= 0:
                            continue
                        if h <= self.max_height and h > best_h:
                            best_h = h
                            pick = f
                    except Exception:
                        continue
                if not pick:
                    # Fallback: any link (still should be playable)
                    for f in files:
                        link = str(f.get("link") or "").strip()
                        if link:
                            pick = f
                            break
                if not pick:
                    continue

                link = str(pick.get("link") or "").strip()
                if not link:
                    continue

                out.append(
                    {
                        "source": "pexels",
                        "item_id": str(vid),
                        "title": f"Pexels video {vid}",
                        "description": f"Pexels stock video result for query '{q[:80]}'",
                        # IMPORTANT: set url to direct media URL for fast download (no extra API call in CB)
                        "url": link,
                        "license": "pexels",
                        "license_raw": "Pexels License",
                        "attribution": None,
                        "thumbnail_url": thumb,
                        "duration_sec": float(duration) if isinstance(duration, (int, float)) else None,
                        "downloads": None,
                    }
                )

            return out[:max_results]
        except Exception as e:
            status = None
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            self._record_error(status, e)
            if self.verbose:
                print(f"⚠️  Pexels search error: {e}")
            return []

    def get_download_url(self, item_id: str) -> Optional[str]:
        # We already emit direct media URLs in search(); downloader can use asset_url directly.
        return None


class PixabaySource(VideoSource):
    """
    Pixabay stock video search (fast, reliable CDN).
    Requires env: PIXABAY_API_KEY
    """

    def __init__(
        self,
        api_key: str,
        throttle_delay_sec: float = 0.2,
        verbose: bool = False,
        timeout_sec: float = 12,
        preferred_quality: str = "medium",  # one of: large, medium, small, tiny
    ):
        super().__init__(throttle_delay_sec, verbose, timeout_sec=timeout_sec)
        self.api_key = str(api_key or "").strip()
        self.preferred_quality = str(preferred_quality or "medium").strip().lower()
        self.search_url = "https://pixabay.com/api/videos/"

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        q = str(query or "").strip()
        if not q:
            return []

        params = {
            "key": self.api_key,
            "q": q,
            "per_page": min(max_results, 50),
            "safesearch": "true",
        }
        headers = {"User-Agent": "PodcastVideoBot/1.0 (Documentary compilation)"}

        try:
            self._throttle()
            resp = requests.get(self.search_url, params=params, headers=headers, timeout=self.timeout_sec)
            self._record_success(resp.status_code)
            resp.raise_for_status()
            data = resp.json() or {}
            hits = data.get("hits", []) or []

            out: List[Dict[str, Any]] = []
            for h in hits:
                vid = h.get("id")
                if vid is None:
                    continue
                duration = h.get("duration")
                thumb = h.get("picture_id")
                videos = h.get("videos") or {}

                # Pick preferred quality URL, with fallback order
                order = [self.preferred_quality, "medium", "small", "tiny", "large"]
                pick_url = None
                for key in order:
                    v = videos.get(key)
                    if isinstance(v, dict) and v.get("url"):
                        pick_url = str(v.get("url") or "").strip()
                        if pick_url:
                            break
                if not pick_url:
                    continue

                # Thumbnail URL (Pixabay pattern)
                thumb_url = None
                if thumb:
                    thumb_url = f"https://i.vimeocdn.com/video/{thumb}_295x166.jpg"  # best-effort

                out.append(
                    {
                        "source": "pixabay",
                        "item_id": str(vid),
                        "title": f"Pixabay video {vid}",
                        "description": f"Pixabay stock video result for query '{q[:80]}'",
                        "url": pick_url,
                        "license": "pixabay",
                        "license_raw": "Pixabay License",
                        "attribution": None,
                        "thumbnail_url": thumb_url,
                        "duration_sec": float(duration) if isinstance(duration, (int, float)) else None,
                        "downloads": int(h.get("views", 0) or 0),
                    }
                )

            return out[:max_results]
        except Exception as e:
            status = None
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            self._record_error(status, e)
            if self.verbose:
                print(f"⚠️  Pixabay search error: {e}")
            return []

    def get_download_url(self, item_id: str) -> Optional[str]:
        return None
    
    def get_download_url(self, item_id: str) -> Optional[str]:
        """
        Europeana nemá direct download - musíme použít edmIsShownBy URL.
        """
        # TODO: Implement když budeme integrovat do CB
        return None
    
    def _normalize_license(self, rights_url: str) -> str:
        """
        Normalizuje Europeana rights URL.
        """
        if not rights_url:
            return "unknown"
        
        r = rights_url.lower()
        
        if "publicdomain" in r or "public-domain" in r:
            return "public_domain"
        if "creativecommons.org/publicdomain/zero" in r:
            return "cc0"
        if "creativecommons.org/licenses/by-sa" in r:
            return "cc-by-sa"
        if "creativecommons.org/licenses/by" in r:
            return "cc-by"
        
        return "unknown"


def create_multi_source_searcher(
    archive_org: bool = True,
    wikimedia: bool = True,
    europeana: bool = False,
    europeana_api_key: Optional[str] = None,
    pexels: bool = False,
    pexels_api_key: Optional[str] = None,
    pixabay: bool = False,
    pixabay_api_key: Optional[str] = None,
    throttle_delay_sec: float = 0.2,
    verbose: bool = False,
    timeout_sec: float = 12,
    allow_unknown_archive_org_license_fallback: bool = False,
    stock_max_height: int = 1080,
    pixabay_preferred_quality: str = "medium",
) -> List[VideoSource]:
    """
    Factory pro vytvoření seznamu video source providerů.
    
    Args:
        archive_org: Enable Archive.org search
        wikimedia: Enable Wikimedia Commons search
        europeana: Enable Europeana search (requires API key)
        europeana_api_key: Europeana API key
        throttle_delay_sec: Rate limiting delay
        verbose: Enable verbose logging
    
    Returns:
        List of VideoSource instances (ordered by priority)
    """
    sources = []
    
    if archive_org:
        sources.append(
            ArchiveOrgSource(
                throttle_delay_sec,
                verbose,
                timeout_sec=timeout_sec,
                allow_unknown_license_fallback=allow_unknown_archive_org_license_fallback,
            )
        )
    
    if wikimedia:
        sources.append(WikimediaSource(throttle_delay_sec, verbose, timeout_sec=timeout_sec))
    
    if europeana and europeana_api_key:
        sources.append(EuropeanaSource(europeana_api_key, throttle_delay_sec, verbose, timeout_sec=timeout_sec))

    # Optional stock sources (only if explicitly enabled + API key provided)
    if pexels and pexels_api_key:
        sources.append(
            PexelsSource(
                api_key=str(pexels_api_key),
                throttle_delay_sec=throttle_delay_sec,
                verbose=verbose,
                timeout_sec=timeout_sec,
                max_height=int(stock_max_height or 1080),
            )
        )
    if pixabay and pixabay_api_key:
        sources.append(
            PixabaySource(
                api_key=str(pixabay_api_key),
                throttle_delay_sec=throttle_delay_sec,
                verbose=verbose,
                timeout_sec=timeout_sec,
                preferred_quality=str(pixabay_preferred_quality or "medium"),
            )
        )
    
    return sources

