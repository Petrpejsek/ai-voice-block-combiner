"""
Topic Intelligence Signal Providers - USA/EN focus

Isolated from pipeline. Provides signals for topic recommendation:
- Google Trends (MVP: placeholder)
- Wikipedia Pageviews (Wikimedia REST API)
- YouTube Signals (competition analysis)

All providers return normalized scores (0-100) and status (ok/no_data/error).
"""

import os
import requests
import time
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import quote


class BaseSignalProvider(ABC):
    """
    Abstract base class for topic intelligence signal providers.
    Follows pattern from video_sources.py for consistency.
    """
    
    def __init__(self, throttle_delay_sec: float = 0.3, timeout_sec: float = 10, verbose: bool = False):
        self.throttle_delay_sec = throttle_delay_sec
        self.last_request_time = 0.0
        self.timeout_sec = timeout_sec
        self.verbose = verbose
        self.provider_name = self.__class__.__name__
        
        # Simple in-memory cache (can upgrade to Redis later)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_sec = int(os.getenv('TOPIC_INTEL_CACHE_TTL', '10800'))  # 3 hours default
        
        # Telemetry
        self.last_http_status: Optional[int] = None
        self.last_error: Optional[str] = None
        self.request_count = 0
        self.cache_hit_count = 0
    
    def _throttle(self) -> None:
        """Rate limiting between requests"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.throttle_delay_sec:
            time.sleep(self.throttle_delay_sec - elapsed)
        self.last_request_time = time.time()
    
    def _record_success(self, http_status: Optional[int] = None) -> None:
        self.last_http_status = http_status
        self.last_error = None
    
    def _record_error(self, http_status: Optional[int], err: Exception) -> None:
        self.last_http_status = http_status
        self.last_error = str(err)
    
    def _get_cache_key(self, query: str, window_days: int, locale: str) -> str:
        """Generate cache key"""
        return f"{self.provider_name}:{query.lower()}:{window_days}:{locale}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get from cache if not expired"""
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if time.time() - cached['timestamp'] < self._cache_ttl_sec:
                self.cache_hit_count += 1
                if self.verbose:
                    print(f"✅ {self.provider_name}: Cache HIT for {cache_key}")
                return cached['data']
            else:
                # Expired
                del self._cache[cache_key]
        return None
    
    def _save_to_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Save to cache with timestamp"""
        self._cache[cache_key] = {
            'timestamp': time.time(),
            'data': data
        }
    
    @abstractmethod
    def fetch(self, query: str, window_days: int, locale: str) -> Dict[str, Any]:
        """
        Fetch signal for a topic.
        
        Args:
            query: Topic query string
            window_days: Time window (7, 30, etc.)
            locale: Locale code (e.g., 'US')
        
        Returns:
            {
                'status': 'ok' | 'no_data' | 'error',
                'score': 0-100,
                'note': str,  # User-facing explanation
                'metadata': dict  # Provider-specific data
            }
        """
        pass


class GoogleTrendsProvider(BaseSignalProvider):
    """
    Google Trends signal provider.
    
    MVP: Returns placeholder status='no_data'.
    Architecture is ready for future integration (pytrends or official API).
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_configured = False  # MVP: not configured
    
    def fetch(self, query: str, window_days: int, locale: str) -> Dict[str, Any]:
        """
        MVP: Return placeholder.
        Future: Implement pytrends or official Trends API.
        """
        self.request_count += 1
        
        if self.verbose:
            print(f"⚠️  GoogleTrendsProvider: Not configured (placeholder)")
        
        return {
            'status': 'no_data',
            'score': 0,
            'note': 'Google Trends API not configured',
            'metadata': {
                'query': query,
                'window_days': window_days,
                'locale': locale,
                'configured': False
            }
        }


class WikipediaPageviewsProvider(BaseSignalProvider):
    """
    Wikipedia Pageviews signal provider using official Wikimedia REST API.
    
    Measures:
    - Absolute pageviews (popularity)
    - Growth delta (momentum)
    
    Score formula: min(100, (absolute_views / 10000) * 50 + growth_pct * 50)
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_base = os.getenv('WIKIPEDIA_API_BASE_URL', 'https://wikimedia.org/api/rest_v1/metrics/pageviews/')
    
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    def _overlap_score(self, query: str, title: str) -> float:
        """
        Heuristic: token overlap between query and candidate title.
        Higher = better match.
        """
        q = set(self._tokenize(query))
        t = set(self._tokenize(title))
        if not q or not t:
            return 0.0
        return len(q & t) / max(1, len(q))

    def _query_variants(self, query: str) -> List[str]:
        """
        Generate simpler variants for framed / clickbait titles so Wikipedia search works.
        Example: "The Final Days of Ted Bundy" -> ["Ted Bundy", ...]
        """
        q = (query or "").strip()
        if not q:
            return []

        variants: List[str] = []
        variants.append(q)

        # Remove common framing prefixes (expanded list)
        prefix_patterns = [
            r"^(the\s+)?(final|last)\s+(days|hours|48\s+hours|72\s+hours|moments?)\s+of\s+",
            r"^(the\s+)?trial\s+of\s+",
            r"^(the\s+)?disappearance\s+of\s+",
            r"^(the\s+)?mystery\s+of\s+",
            r"^(the\s+)?case\s+of\s+",
            r"^(the\s+)?death\s+of\s+",
            r"^(the\s+)?assassination\s+of\s+",
            r"^(the\s+)?execution\s+of\s+",
            r"^(the\s+)?fall\s+of\s+",
            r"^(the\s+)?rise\s+and\s+fall\s+of\s+",
            r"^(the\s+)?collapse\s+of\s+",
            r"^(the\s+)?scandal\s+of\s+",
            r"^(the\s+)?secrets?\s+of\s+",
            r"^(the\s+)?true\s+story\s+of\s+",
            r"^(the\s+)?untold\s+story\s+of\s+",
            r"^(the\s+)?hunt\s+for\s+",
            r"^(the\s+)?search\s+for\s+",
            r"^inside\s+(the\s+)?",
            r"^who\s+killed\s+",
            r"^what\s+happened\s+to\s+",
            r"^how\s+they\s+caught\s+",
        ]
        
        for pattern in prefix_patterns:
            cleaned = re.sub(pattern, "", q, flags=re.IGNORECASE).strip()
            if cleaned and cleaned.lower() != q.lower() and cleaned not in variants:
                variants.append(cleaned)

        # Remove trailing subtitle fragments after ":" or " - "
        cleaned2 = re.split(r"\s*[:\-–—]\s*", q, maxsplit=1)[0].strip()
        if cleaned2 and cleaned2.lower() != q.lower() and cleaned2 not in variants:
            variants.append(cleaned2)

        # If still long, try last 2-5 tokens (often person/place)
        toks = self._tokenize(q)
        if len(toks) >= 3:
            for n in (2, 3, 4, 5):
                if len(toks) >= n:
                    tail = " ".join(toks[-n:])
                    if tail and tail.lower() != q.lower():
                        variants.append(tail)

        # Deduplicate preserving order
        seen = set()
        out = []
        for v in variants:
            k = v.lower().strip()
            if k and k not in seen:
                seen.add(k)
                out.append(v.strip())
        return out[:6]  # Limit to 6 variants

    def fetch(self, query: str, window_days: int, locale: str) -> Dict[str, Any]:
        """
        Fetch Wikipedia pageviews for query.
        
        Process:
        1. Search for Wikipedia page title
        2. Get pageviews for last N days
        3. Calculate growth percentage
        4. Compute score
        """
        self.request_count += 1
        
        # Check cache
        cache_key = self._get_cache_key(query, window_days, locale)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            # Step 1: Find Wikipedia page title
            page_title = self._search_wikipedia_page(query)
            if not page_title:
                result = {
                    'status': 'no_data',
                    'score': 0,
                    'note': 'No Wikipedia page found',
                    'metadata': {'query': query}
                }
                self._save_to_cache(cache_key, result)
                return result
            
            # Step 2: Get pageviews
            pageviews_data = self._get_pageviews(page_title, window_days)
            if not pageviews_data:
                result = {
                    'status': 'no_data',
                    'score': 0,
                    'note': f'Page found: {page_title}, but no pageview data',
                    'metadata': {'query': query, 'page_title': page_title}
                }
                self._save_to_cache(cache_key, result)
                return result
            
            # Step 3: Calculate metrics
            total_views = pageviews_data['total_views']
            growth_pct = pageviews_data['growth_pct']
            
            # Step 4: Compute score
            # Formula: min(100, (absolute_views / 10000) * 50 + growth_pct * 50)
            absolute_score = min(50, (total_views / 10000) * 50)
            growth_score = min(50, max(-50, growth_pct) * 0.5 + 25)  # Normalize -100 to +100 → 0 to 50
            score = min(100, absolute_score + growth_score)
            
            # Generate note
            if growth_pct > 20:
                trend = "Strong growth"
            elif growth_pct > 5:
                trend = "Moderate growth"
            elif growth_pct > -5:
                trend = "Stable"
            else:
                trend = "Declining"
            
            note = f"{trend} ({growth_pct:+.1f}%) • {total_views:,} views/{window_days}d"
            
            result = {
                'status': 'ok',
                'score': int(score),
                'note': note,
                'metadata': {
                    'page_title': page_title,
                    'total_views': total_views,
                    'delta_pct': round(growth_pct, 2),
                    'window_days': window_days,
                    'url': f"https://en.wikipedia.org/wiki/{quote(page_title)}"
                }
            }
            
            self._record_success(200)
            self._save_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            self._record_error(None, e)
            if self.verbose:
                print(f"⚠️  WikipediaPageviewsProvider error: {e}")
            
            result = {
                'status': 'error',
                'score': 0,
                'note': f'Error fetching data: {str(e)[:50]}',
                'metadata': {'query': query, 'error': str(e)}
            }
            return result
    
    def _search_wikipedia_page(self, query: str) -> Optional[str]:
        """
        Search for Wikipedia page title.
        Uses multiple query variants + picks best match by token overlap.
        """
        url = "https://en.wikipedia.org/w/api.php"
        headers = {
            'User-Agent': 'TopicIntelligenceAssistant/1.0 (Documentary research; contact@example.com)'
        }

        for qv in self._query_variants(query):
            self._throttle()
            params = {
                'action': 'opensearch',
                'search': qv,
                'limit': 5,
                'namespace': 0,
                'format': 'json'
            }
            try:
                response = requests.get(url, params=params, headers=headers, timeout=self.timeout_sec)
                response.raise_for_status()
                data = response.json()
                titles = data[1] if (len(data) > 1 and isinstance(data[1], list)) else []
                if titles:
                    best = max(titles, key=lambda t: self._overlap_score(query, t))
                    if best:
                        if self.verbose:
                            print(f"   📚 Wiki found: '{best}' for '{qv}'")
                        return best
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Wikipedia opensearch error ({qv}): {e}")

        # Fallback: MediaWiki search API (often better for long titles)
        for qv in self._query_variants(query):
            self._throttle()
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': qv,
                'srlimit': 5,
                'format': 'json'
            }
            try:
                response = requests.get(url, params=params, headers=headers, timeout=self.timeout_sec)
                response.raise_for_status()
                data = response.json() or {}
                items = (data.get("query", {}) or {}).get("search", []) or []
                titles = [it.get("title") for it in items if isinstance(it, dict) and it.get("title")]
                if titles:
                    best = max(titles, key=lambda t: self._overlap_score(query, t))
                    if best:
                        if self.verbose:
                            print(f"   📚 Wiki found (search): '{best}' for '{qv}'")
                        return best
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Wikipedia search API error ({qv}): {e}")

        return None
    
    def _get_pageviews(self, page_title: str, window_days: int) -> Optional[Dict[str, Any]]:
        """
        Get pageviews for a Wikipedia page over the last N days.
        """
        self._throttle()
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=window_days)
        mid_date = end_date - timedelta(days=window_days // 2)
        
        # API format: YYYYMMDD
        start_str = start_date.strftime('%Y%m%d')
        mid_str = mid_date.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        
        # URL encode page title
        encoded_title = quote(page_title.replace(' ', '_'))
        
        # Pageviews API endpoint
        url = f"{self.api_base}per-article/en.wikipedia/all-access/all-agents/{encoded_title}/daily/{start_str}/{end_str}"
        headers = {
            'User-Agent': 'TopicIntelligenceAssistant/1.0 (Documentary research; contact@example.com)'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout_sec)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            if not items:
                return None
            
            # Calculate total views and growth
            total_views = sum(item.get('views', 0) for item in items)
            
            # Split into first half and second half for growth calculation
            mid_timestamp = mid_date.strftime('%Y%m%d00')
            first_half_views = sum(item.get('views', 0) for item in items if item.get('timestamp', '') < mid_timestamp)
            second_half_views = sum(item.get('views', 0) for item in items if item.get('timestamp', '') >= mid_timestamp)
            
            # Calculate growth percentage
            if first_half_views > 0:
                growth_pct = ((second_half_views - first_half_views) / first_half_views) * 100
            else:
                growth_pct = 0 if second_half_views == 0 else 100
            
            return {
                'total_views': total_views,
                'first_half_views': first_half_views,
                'second_half_views': second_half_views,
                'growth_pct': growth_pct
            }
            
        except Exception as e:
            if self.verbose:
                print(f"⚠️  Pageviews API error: {e}")
            return None


class YouTubeSignalsProvider(BaseSignalProvider):
    """
    YouTube signals provider for competition analysis.
    
    Uses YouTube Data API v3:
    - Search: Count recent videos (competition level)
    - Videos: Check channel sizes (mega-channel dominance)
    
    Score formula: Inverse competition (fewer recent uploads = higher score)
    """
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY', '')
        self.api_base = "https://www.googleapis.com/youtube/v3"

    def _read_dotenv_key(self, key_name: str) -> str:
        """
        Best-effort read from backend/.env (without exposing it anywhere).
        This helps when the key is saved server-side but not present in process env yet.
        """
        try:
            dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            if not os.path.exists(dotenv_path):
                return ""
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == key_name:
                        v = v.strip().strip('"').strip("'")
                        return v
            return ""
        except Exception:
            return ""

    def _refresh_api_key(self) -> None:
        """
        Refresh key dynamically so a newly saved key starts working without code changes.
        """
        if self.api_key:
            return
        self.api_key = os.getenv("YOUTUBE_API_KEY", "") or self._read_dotenv_key("YOUTUBE_API_KEY")
    
    def fetch(self, query: str, window_days: int, locale: str) -> Dict[str, Any]:
        """
        Fetch YouTube competition signals for query.
        
        Process:
        1. Search for recent videos (last N days)
        2. Count results
        3. Check if dominated by mega-channels
        4. Compute competition score
        """
        self.request_count += 1

        # Refresh key (in case it was added after provider init)
        self._refresh_api_key()

        # Check if API key configured
        if not self.api_key:
            return {
                'status': 'no_data',
                'score': 0,
                'note': 'YouTube API key not configured',
                'metadata': {'configured': False}
            }
        
        # Check cache
        cache_key = self._get_cache_key(query, window_days, locale)
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            # Step 1: Search for recent videos
            search_results = self._search_videos(query, window_days, locale)
            if not search_results:
                result = {
                    'status': 'no_data',
                    'score': 0,
                    'note': 'No recent videos found',
                    'metadata': {'query': query}
                }
                self._save_to_cache(cache_key, result)
                return result
            
            video_count = search_results['video_count']
            video_ids = search_results['video_ids']
            
            # Step 2: Check for mega-channel dominance
            dominated_by_large = False
            if video_ids:
                dominated_by_large = self._check_mega_channel_dominance(video_ids)
            
            # Step 3: Compute competition score
            # Formula: inverse competition (fewer uploads = better)
            # 0-5 videos = high score (90-100)
            # 6-20 videos = medium score (60-89)
            # 21-50 videos = low score (30-59)
            # 50+ videos = very low score (0-29)
            
            if video_count <= 5:
                base_score = 95
                competition_level = "Very low"
            elif video_count <= 20:
                base_score = 75 - (video_count - 5) * 1.5
                competition_level = "Low"
            elif video_count <= 50:
                base_score = 45 - (video_count - 20) * 0.5
                competition_level = "Moderate"
            else:
                base_score = max(10, 30 - (video_count - 50) * 0.2)
                competition_level = "High"
            
            # Penalty if dominated by mega-channels
            if dominated_by_large:
                base_score *= 0.7
                dominance_note = " • Dominated by large channels"
            else:
                dominance_note = ""
            
            score = int(min(100, max(0, base_score)))
            
            # Generate note
            note = f"{competition_level} competition • {video_count} recent videos/{window_days}d{dominance_note}"
            
            # Competition flags
            flags = []
            if video_count > 50:
                flags.append("TOO_MANY_RECENT_UPLOADS")
            if dominated_by_large:
                flags.append("MEGA_CHANNELS_DOMINATE")
            
            result = {
                'status': 'ok',
                'score': score,
                'note': note,
                'metadata': {
                    'recent_videos_count': video_count,
                    'dominated_by_large_channels': dominated_by_large,
                    'window_days': window_days,
                    'competition_level': competition_level,
                    'competition_flags': flags
                }
            }
            
            self._record_success(200)
            self._save_to_cache(cache_key, result)
            return result
            
        except Exception as e:
            self._record_error(None, e)
            if self.verbose:
                print(f"⚠️  YouTubeSignalsProvider error: {e}")
            
            result = {
                'status': 'error',
                'score': 0,
                'note': f'Error fetching data: {str(e)[:50]}',
                'metadata': {'query': query, 'error': str(e)}
            }
            return result
    
    def _search_videos(self, query: str, window_days: int, locale: str) -> Optional[Dict[str, Any]]:
        """
        Search for recent videos using YouTube Data API.
        """
        self._throttle()
        
        # Calculate date for publishedAfter
        after_date = datetime.utcnow() - timedelta(days=window_days)
        after_str = after_date.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        url = f"{self.api_base}/search"
        params = {
            'part': 'id',
            'q': query,
            'type': 'video',
            'maxResults': 50,
            'order': 'relevance',
            'publishedAfter': after_str,
            'regionCode': locale,
            'key': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout_sec)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            video_ids = [item['id']['videoId'] for item in items if 'videoId' in item.get('id', {})]
            
            return {
                'video_count': len(video_ids),
                'video_ids': video_ids[:10]  # Keep only first 10 for channel check
            }
            
        except Exception as e:
            if self.verbose:
                print(f"⚠️  YouTube search error: {e}")
            return None
    
    def _check_mega_channel_dominance(self, video_ids: List[str]) -> bool:
        """
        Check if videos are dominated by mega-channels (>1M subs).
        """
        if not video_ids:
            return False
        
        self._throttle()
        
        # Get video details to find channel IDs
        url = f"{self.api_base}/videos"
        params = {
            'part': 'snippet',
            'id': ','.join(video_ids[:10]),
            'key': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout_sec)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            channel_ids = [item['snippet']['channelId'] for item in items]
            
            if not channel_ids:
                return False
            
            # Check channel subscriber counts
            self._throttle()
            url = f"{self.api_base}/channels"
            params = {
                'part': 'statistics',
                'id': ','.join(channel_ids[:10]),
                'key': self.api_key
            }
            
            response = requests.get(url, params=params, timeout=self.timeout_sec)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            mega_channel_count = 0
            
            for item in items:
                stats = item.get('statistics', {})
                sub_count = int(stats.get('subscriberCount', 0))
                if sub_count > 1000000:  # 1M+ subs
                    mega_channel_count += 1
            
            # If more than 50% are mega-channels, consider it dominated
            return mega_channel_count > len(items) / 2
            
        except Exception as e:
            if self.verbose:
                print(f"⚠️  Channel check error: {e}")
            return False
    
    def get_most_popular_videos(self, locale: str = 'US', max_results: int = 20) -> List[str]:
        """
        Get most popular videos for seeding topics.
        Returns list of video titles.
        """
        self._refresh_api_key()
        if not self.api_key:
            return []
        
        self._throttle()
        
        url = f"{self.api_base}/videos"
        params = {
            'part': 'snippet',
            'chart': 'mostPopular',
            'regionCode': locale,
            'maxResults': max_results,
            'videoCategoryId': '22',  # People & Blogs (general interest)
            'key': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout_sec)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            titles = [item['snippet']['title'] for item in items]
            
            if self.verbose:
                print(f"✅ YouTube: Fetched {len(titles)} popular video titles")
            
            return titles
            
        except Exception as e:
            if self.verbose:
                print(f"⚠️  YouTube mostPopular error: {e}")
            return []

