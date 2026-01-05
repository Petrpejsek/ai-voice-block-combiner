#!/usr/bin/env python3
"""
Visual Assistant - LLM Vision-based asset reranking
Analyzuje thumbnaily kandidátů z archive_manifest.json pomocí OpenAI Vision API
a vybírá nejlepší shodu pro každou scénu.
"""

import json
import os
import re
from typing import Dict, List, Optional, Any
import requests


class VisualAssistant:
    """
    LLM Vision assistant pro výběr nejlepších vizuálních kandidátů.
    
    Používá Vision API (gpt-4o, gpt-4-turbo) k analýze thumbnailů
    a detekci problémů jako text v obraze, špatná relevance, nízká kvalita.
    
    Podporuje: OpenRouter (preferovaný) nebo OpenAI.
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        custom_prompt: Optional[str] = None,
        verbose: bool = False,
        provider: str = "openai"  # "openai" nebo "openrouter"
    ):
        """
        Args:
            api_key: API klíč (OpenAI nebo OpenRouter)
            model: Model s vision capabilities (gpt-4o, gpt-4-turbo)
            temperature: Temperature pro LLM (0.0-1.0, nižší = konzistentnější)
            custom_prompt: Custom system prompt (None = použije default)
            verbose: Logování detailů
            provider: "openai" nebo "openrouter"
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.custom_prompt = custom_prompt
        self.verbose = verbose
        self.provider = provider.lower().strip()
        
        if not self.api_key:
            raise ValueError("API key je povinný pro Visual Assistant")
    
    def deduplicate_and_rank_pool_candidates(
        self,
        candidates: List[Dict[str, Any]],
        episode_topic: str,
        max_analyze: int = 30
    ) -> List[Dict[str, Any]]:
        """
        HLAVNÍ METODA PRO AAR: Deduplikuje + rankuje pool kandidáty pomocí LLM Vision.
        
        FÁZE 1: Visual Deduplication
        - Groupuje podobné/duplicitní thumbnaily
        - Z každé group vybere nejlepší kvalitu
        
        FÁZE 2: Quality Ranking
        - Hodnotí každý unique kandidát
        - Score: relevance × quality × suitability
        
        Args:
            candidates: List kandidátů s thumbnail_url
            episode_topic: Téma epizody (pro relevanci)
            max_analyze: Max kandidátů k analýze (default 30)
        
        Returns:
            List[Dict]: Seřazené unique kandidáty s llm_quality_score a llm_analysis
        """
        if not candidates:
            return []
        
        # Limit to max_analyze
        candidates = candidates[:max_analyze]
        
        print(f"🎨 Visual Assistant: Analyzing {len(candidates)} pool candidates...")
        
        # FÁZE 1: Visual Deduplication
        print(f"   Phase 1: Visual Deduplication (grouping similar thumbnails)...")
        dedup_result = self._deduplicate_pool_candidates(candidates, episode_topic)
        
        # FÁZE 2: Quality Ranking (pro unique candidates)
        unique_candidates = dedup_result.get('unique_candidates', [])
        print(f"   Phase 2: Quality Ranking (scoring {len(unique_candidates)} unique assets)...")
        ranked_candidates = self._rank_pool_candidates(
            unique_candidates,
            episode_topic
        )
        
        print(f"   ✅ Done: {len(candidates)} → {len(ranked_candidates)} unique (removed {len(candidates) - len(ranked_candidates)} duplicates)")
        
        return ranked_candidates
    
    def analyze_pool_candidates(
        self,
        candidates: List[Dict[str, Any]],
        episode_topic: str,
        max_analyze: int = 30
    ) -> Dict[str, Any]:
        """
        LEGACY: Analyzuje POOL kandidáty před výběrem TOP N (vrací dict s metadaty).
        
        Použij raději deduplicate_and_rank_pool_candidates() pro přímou integraci do AAR.
        
        FÁZE 1: Visual Deduplication
        - Groupuje podobné/duplicitní thumbnaily
        - Z každé group vybere nejlepší kvalitu
        
        FÁZE 2: Quality Ranking
        - Hodnotí každý unique kandidát
        - Score: relevance × quality × suitability
        
        Args:
            candidates: List kandidátů s thumbnail_url
            episode_topic: Téma epizody (pro relevanci)
            max_analyze: Max kandidátů k analýze
        
        Returns:
            {
                "deduplication_groups": [...],
                "unique_candidates": [
                    {
                        "archive_item_id": str,
                        "llm_quality_score": 0.0-1.0,
                        "llm_analysis": {...},
                        "is_duplicate": bool,
                        "duplicate_of": str | None
                    },
                    ...
                ],
                "stats": {...}
            }
        """
        if not candidates:
            return {"unique_candidates": [], "stats": {"total_analyzed": 0}}
        
        # Limit to max_analyze
        candidates = candidates[:max_analyze]
        
        print(f"🎨 Visual Assistant: Analyzing {len(candidates)} pool candidates...")
        
        # FÁZE 1: Visual Deduplication
        print(f"   Phase 1: Visual Deduplication (grouping similar thumbnails)...")
        dedup_result = self._deduplicate_pool_candidates(candidates, episode_topic)
        
        # FÁZE 2: Quality Ranking (pro unique candidates)
        print(f"   Phase 2: Quality Ranking (scoring {len(dedup_result['unique_candidates'])} unique assets)...")
        ranked_candidates = self._rank_pool_candidates(
            dedup_result['unique_candidates'],
            episode_topic
        )
        
        return {
            "deduplication_groups": dedup_result.get('groups', []),
            "unique_candidates": ranked_candidates,
            "stats": {
                "total_input": len(candidates),
                "duplicate_groups": len(dedup_result.get('groups', [])),
                "unique_after_dedup": len(dedup_result['unique_candidates']),
                "final_ranked": len(ranked_candidates)
            }
        }
    
    def _deduplicate_pool_candidates(
        self,
        candidates: List[Dict[str, Any]],
        episode_topic: str
    ) -> Dict[str, Any]:
        """
        LLM Visual Deduplication - groupuje podobné thumbnaily.
        """
        # Build thumbnail list for LLM
        thumbnail_list = []
        for i, c in enumerate(candidates):
            thumb_url = c.get('thumbnail_url') or c.get('asset_url', '')
            if not thumb_url:
                continue
            thumbnail_list.append({
                "index": i,
                "id": c.get('archive_item_id', f'asset_{i}'),
                "title": c.get('title', 'Unknown')[:100],
                "url": thumb_url
            })
        
        if not thumbnail_list:
            return {"unique_candidates": candidates, "groups": []}
        
        # LLM Deduplication Prompt
        system_prompt = f"""You are a visual deduplication expert for documentary footage.

You will receive thumbnails from multiple video/image sources (Archive.org, Wikimedia, Europeana).

YOUR TASK: Identify DUPLICATES or VERY SIMILAR content.

RULES:
1. Group thumbnails that show THE SAME scene/shot/angle
2. Group thumbnails that are DIFFERENT QUALITY versions of same content
3. For each group, recommend BEST thumbnail (highest visual quality)
4. List truly UNIQUE thumbnails separately

Return ONLY valid JSON:
{{
  "groups": [
    {{
      "ids": ["id1", "id2"],
      "reason": "Same Notre-Dame front view, different resolution",
      "best_id": "id1",
      "best_reason": "Sharper, higher resolution"
    }}
  ],
  "unique_ids": ["id3", "id4", ...],
  "reasoning": "Brief explanation of deduplication strategy"
}}"""

        user_message = f"""Episode topic: {episode_topic}

I have {len(thumbnail_list)} thumbnails. Please group duplicates/similar content.

Thumbnails:
"""
        for t in thumbnail_list[:500]:  # API limit: 500 images
            user_message += f"\n- ID: {t['id']}, Title: {t['title']}"
        
        # Call LLM with thumbnails
        try:
            response = self._call_vision_api_multi(
                system_prompt=system_prompt,
                user_text=user_message,
                image_urls=[t['url'] for t in thumbnail_list[:500]]  # API limit: 500 images
            )
            
            result = self._parse_json_object(response)
            groups = result.get('groups', [])
            unique_ids = set(result.get('unique_ids', []))
            
            # Mark duplicates
            duplicate_map = {}  # id -> best_id
            for group in groups:
                best_id = group.get('best_id')
                for gid in group.get('ids', []):
                    if gid != best_id:
                        duplicate_map[gid] = best_id
            
            # Build unique candidates list
            unique_candidates = []
            for c in candidates:
                cid = c.get('archive_item_id', '')
                if cid in duplicate_map:
                    c['_is_duplicate'] = True
                    c['_duplicate_of'] = duplicate_map[cid]
                elif cid in unique_ids or cid not in [g for grp in groups for g in grp.get('ids', [])]:
                    c['_is_duplicate'] = False
                    unique_candidates.append(c)
            
            if self.verbose:
                print(f"   ✅ Dedup: {len(candidates)} → {len(unique_candidates)} unique ({len(groups)} duplicate groups)")
            
            return {
                "unique_candidates": unique_candidates,
                "groups": groups
            }
        
        except Exception as e:
            print(f"   ⚠️ Deduplication failed: {e}, using all candidates")
            return {"unique_candidates": candidates, "groups": []}
    
    def _rank_pool_candidates(
        self,
        candidates: List[Dict[str, Any]],
        episode_topic: str
    ) -> List[Dict[str, Any]]:
        """
        LLM Quality Ranking - hodnotí kandidáty pomocí BATCH Vision API.
        OPTIMIZED: Posílá až 500 thumbnails NAJEDNOU (API limit)!
        """
        ranked = []
        
        # Filter candidates with valid thumbnails
        candidates_with_thumbs = []
        for c in candidates:
            thumb_url = c.get('thumbnail_url') or c.get('asset_url', '')
            if thumb_url:
                candidates_with_thumbs.append(c)
            else:
                c['llm_quality_score'] = 0.5
                ranked.append(c)
        
        if not candidates_with_thumbs:
            return ranked
        
        # Process in ONE batch (API supports up to 500 images / 50MB)
        batch = candidates_with_thumbs[:500]  # Safety limit
        
        # Build batch prompt
        system_prompt = f"""You are a visual quality expert for documentary footage about: {episode_topic}

Analyze these thumbnails and rate each on multiple dimensions.

Return ONLY valid JSON array with one object per thumbnail:
[
  {{
    "index": 0,
    "visual_quality": 0.0-1.0,
    "topic_relevance": 0.0-1.0,
    "technical_quality": 0.0-1.0,
    "has_text_overlay": true/false,
    "suitability": 0.0-1.0,
    "reasoning": "1-2 sentence explanation"
  }},
  ...
]"""

        # Build thumbnail list with metadata
        thumbnails_info = []
        image_urls = []
        for i, c in enumerate(batch):
            thumb_url = c.get('thumbnail_url') or c.get('asset_url', '')
            image_urls.append(thumb_url)
            thumbnails_info.append({
                "index": i,
                "title": c.get('title', 'Unknown')[:100],
                "description": c.get('description', 'N/A')[:150],
                "source": c.get('_source', 'unknown')
            })
        
        user_message = f"""Rate these {len(batch)} thumbnails for documentary about: {episode_topic}

Thumbnails:
"""
        for info in thumbnails_info[:100]:  # Limit text list to 100 for readability
            user_message += f"\n{info['index']}. Title: {info['title']} | Source: {info['source']}"
        
        if len(batch) > 100:
            user_message += f"\n... and {len(batch) - 100} more thumbnails (see images)"
        
        try:
            response = self._call_vision_api_batch(
                system_prompt=system_prompt,
                user_text=user_message,
                image_urls=image_urls
            )
            
            results = self._parse_json_array(response)
            
            # Apply scores to candidates
            for i, c in enumerate(batch):
                # Find matching result by index
                result = None
                for r in results:
                    if r.get('index') == i:
                        result = r
                        break
                
                if result:
                    visual_q = result.get('visual_quality', 0.5)
                    topic_rel = result.get('topic_relevance', 0.5)
                    tech_q = result.get('technical_quality', 0.5)
                    has_text = result.get('has_text_overlay', False)
                    suitability = result.get('suitability', 0.5)
                    
                    # Weighted score (quality first!)
                    score = (
                        visual_q * 0.35 +
                        topic_rel * 0.30 +
                        tech_q * 0.20 +
                        suitability * 0.15
                    )
                    
                    # Penalty pro text overlays
                    if has_text:
                        score *= 0.3
                    
                    c['llm_quality_score'] = round(score, 3)
                    c['llm_analysis'] = result
                else:
                    c['llm_quality_score'] = 0.5
                
                ranked.append(c)
            
            if self.verbose:
                print(f"   ✅ Rated {len(batch)} thumbnails in ONE API call")
        
        except Exception as e:
            if self.verbose:
                print(f"   ⚠️ Batch ranking failed: {e}, using defaults")
            for c in batch:
                c['llm_quality_score'] = 0.5
                ranked.append(c)
        
        # Sort by quality score (descending)
        ranked.sort(key=lambda x: x.get('llm_quality_score', 0), reverse=True)
        
        return ranked
    
    def _call_vision_api_multi(
        self,
        system_prompt: str,
        user_text: str,
        image_urls: List[str]
    ) -> str:
        """
        Volá Vision API s MULTIPLE images (pro deduplication).
        """
        if self.provider == "openrouter":
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
        else:
            endpoint = "https://api.openai.com/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Build content with multiple images
        content = [{"type": "text", "text": user_text}]
        for url in image_urls[:500]:  # API supports up to 500 images (increased from 50)
            content.append({
                "type": "image_url",
                "image_url": {"url": url, "detail": "low"}  # Low detail for dedup (faster + cheaper)
            })
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "temperature": self.temperature,
            "max_tokens": 2000
        }
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=120, verify=False)
        response.raise_for_status()
        data = response.json()
        
        return data["choices"][0]["message"]["content"]
    
    def _call_vision_api_batch(
        self,
        system_prompt: str,
        user_text: str,
        image_urls: List[str]
    ) -> str:
        """
        Volá Vision API s BATCH images (až 500 najednou pro rating).
        Optimized: detail="low" (512x512) pro úsporu tokenů.
        API limit: 500 images OR 50MB payload (whichever comes first)
        """
        if self.provider == "openrouter":
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
        else:
            endpoint = "https://api.openai.com/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Build content with ALL images (up to 500)
        content = [{"type": "text", "text": user_text}]
        for url in image_urls[:500]:  # API hard limit: 500 images
            content.append({
                "type": "image_url",
                "image_url": {"url": url, "detail": "low"}  # Low = 512x512 (~85 tokens per image)
            })
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "temperature": self.temperature,
            "max_tokens": 16000,  # Much higher for batch responses (500 items × ~30 tokens)
            "response_format": {"type": "json_object"} if self.provider == "openai" else None
        }
        
        # Remove None values
        if payload["response_format"] is None:
            del payload["response_format"]
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=300, verify=False)  # 5 min timeout
        response.raise_for_status()
        data = response.json()
        
        return data["choices"][0]["message"]["content"]

    def analyze_candidate(
        self,
        thumbnail_url: str,
        beat_text: str,
        shot_types: List[str],
        candidate_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyzuje jeden vizuální kandidát pomocí Vision API.
        
        Args:
            thumbnail_url: URL náhledu (thumbnail)
            beat_text: Text narrace pro tento beat
            shot_types: Seznam shot types (např. ["troop_movement", "maps"])
            candidate_metadata: Metadata (title, description, source)
        
        Returns:
            {
                "relevance_score": 0.0-1.0,
                "has_text_overlay": bool,
                "quality_issues": [],
                "recommendation": "use" | "skip" | "fallback",
                "reasoning": str
            }
        """
        system_prompt = self.custom_prompt or self._default_system_prompt()
        
        user_message = self._build_user_message(
            beat_text, shot_types, candidate_metadata
        )
        
        try:
            response = self._call_vision_api(
                system_prompt=system_prompt,
                user_text=user_message,
                image_url=thumbnail_url
            )
            
            # Parse JSON response (robust: strip code-fences / extract first JSON object)
            result = self._parse_json_object(response)
            
            if self.verbose:
                print(f"✅ Visual analysis: {candidate_metadata.get('title', 'Unknown')}")
                print(f"   Relevance: {result.get('relevance_score', 0):.2f}")
                print(f"   Text overlay: {result.get('has_text_overlay', False)}")
                print(f"   Recommendation: {result.get('recommendation', 'skip')}")
            
            return result
        
        except Exception as e:
            if self.verbose:
                print(f"⚠️ Visual analysis failed: {e}")
            
            # Fallback: keep candidate but strongly down-rank it (do NOT let failures dominate selection)
            return {
                "relevance_score": 0.2,
                "has_text_overlay": False,
                "quality_issues": [f"Analysis failed: {str(e)}"],
                "recommendation": "fallback",
                "reasoning": "Nepodařilo se analyzovat thumbnail (API chyba). Kandidát ponechán jen jako nouzová možnost."
            }
    
    def rerank_candidates(
        self,
        candidates: List[Dict[str, Any]],
        beat_text: str,
        shot_types: List[str],
        max_analyze: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Analyzuje a rerank kandidáty pro jeden beat.
        
        Args:
            candidates: Seznam kandidátů (musí mít thumbnail_url)
            beat_text: Text narrace
            shot_types: Shot types
            max_analyze: Max počet kandidátů k analýze (top N)
        
        Returns:
            Reranked seznam kandidátů (s přidaným "_visual_analysis" fieldem)
        """
        analyzed = []
        
        for i, candidate in enumerate(candidates[:max_analyze]):
            thumbnail_url = candidate.get('thumbnail_url')
            
            if not thumbnail_url:
                # Bez thumbnilu nemůžeme analyzovat
                candidate['_visual_analysis'] = {
                    "relevance_score": 0.3,
                    "has_text_overlay": False,
                    "quality_issues": ["No thumbnail available"],
                    "recommendation": "fallback",  # STABILITY: Don't hard-reject, allow as last resort
                    "reasoning": "No visual preview to analyze - may still be usable"
                }
                analyzed.append(candidate)
                continue
            
            metadata = {
                "title": candidate.get('title', ''),
                "description": candidate.get('description', ''),
                "source": candidate.get('_source', 'unknown'),
                "archive_item_id": candidate.get('archive_item_id', '')
            }
            
            analysis = self.analyze_candidate(
                thumbnail_url=thumbnail_url,
                beat_text=beat_text,
                shot_types=shot_types,
                candidate_metadata=metadata
            )
            
            candidate['_visual_analysis'] = analysis
            analyzed.append(candidate)
        
        # Přidat neanalyzované kandidáty (pokud jich je víc než max_analyze)
        for candidate in candidates[max_analyze:]:
            candidate['_visual_analysis'] = {
                "relevance_score": 0.2,
                "has_text_overlay": False,
                "quality_issues": ["Not analyzed (too low in initial ranking)"],
                "recommendation": "fallback",  # STABILITY: Don't hard-reject, allow as last resort
                "reasoning": "Below analysis threshold - may still be usable"
            }
            analyzed.append(candidate)
        
        # Sort by relevance score (descending)
        analyzed.sort(key=lambda c: c['_visual_analysis']['relevance_score'], reverse=True)
        
        return analyzed
    
    def process_manifest(
        self,
        manifest_path: str,
        output_path: Optional[str] = None,
        max_analyze_per_beat: int = 5
    ) -> Dict[str, Any]:
        """
        Zpracuje celý archive_manifest.json a rerank všechny kandidáty.
        
        Args:
            manifest_path: Cesta k archive_manifest.json
            output_path: Kam uložit reranked manifest (None = přepsat original)
            max_analyze_per_beat: Max kandidátů k analýze per beat
        
        Returns:
            Upravený manifest dict (s reranked candidates)
        """
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # ------------------------------------------------------------------
        # Enrich context for Vision:
        # - Resolve block_id -> full narration text from script_state.json
        # - Ensure each candidate has thumbnail_url + basic metadata
        # This fixes "assistant runs but does nothing" when manifest candidates
        # only contain archive_item_id/score without preview URLs.
        # ------------------------------------------------------------------
        episode_dir = os.path.dirname(manifest_path)
        state_path = os.path.join(episode_dir, "script_state.json")
        state: Dict[str, Any] = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as sf:
                    state = json.load(sf) or {}
            except Exception:
                state = {}

        # Build block_id -> text lookup (prefer TTS-ready text if available)
        block_text: Dict[str, str] = {}
        try:
            tts_pkg = None
            if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("tts_ready_package"), dict):
                tts_pkg = state["metadata"]["tts_ready_package"]
            elif isinstance(state.get("tts_ready_package"), dict):
                tts_pkg = state.get("tts_ready_package")
            if isinstance(tts_pkg, dict):
                blocks = tts_pkg.get("narration_blocks")
                if isinstance(blocks, list):
                    for b in blocks:
                        if not isinstance(b, dict):
                            continue
                        bid = str(b.get("block_id") or "").strip()
                        txt = str(b.get("text_tts") or b.get("text") or "").strip()
                        if bid and txt:
                            block_text[bid] = txt
        except Exception:
            pass

        def _split_source(aid: str) -> tuple[str, str]:
            s = str(aid or "").strip()
            if ":" in s:
                p, r = s.split(":", 1)
                p = p.strip().lower()
                r = r.strip()
                if p in ("archive", "archiveorg", "archive_org", "archive.org"):
                    return "archive_org", r
                if p in ("wikimedia", "commons", "wikimedia_commons"):
                    return "wikimedia", r
                if p in ("europeana",):
                    return "europeana", r
                return p or "other", r
            return "archive_org", s

        wm_cache: Dict[str, str] = {}
        eu_cache: Dict[str, str] = {}

        def _wm_thumb(file_id: str) -> str:
            fid = str(file_id or "").strip()
            if not fid:
                return ""
            fid = fid.replace("File:", "").replace(" ", "_")
            if fid in wm_cache:
                return wm_cache[fid] or ""
            try:
                api_url = "https://commons.wikimedia.org/w/api.php"
                params = {
                    "action": "query",
                    "format": "json",
                    "titles": f"File:{fid}",
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "iiurlwidth": 360,
                }
                headers = {"User-Agent": "PodcastVideoBot/1.0 (Visual Assistant thumbnails; local)"}
                r = requests.get(api_url, params=params, headers=headers, timeout=15, verify=False)
                r.raise_for_status()
                data = r.json() or {}
                pages = (data.get("query") or {}).get("pages") or {}
                for _pid, page in pages.items():
                    if not isinstance(page, dict):
                        continue
                    ii = page.get("imageinfo")
                    if isinstance(ii, list) and ii and isinstance(ii[0], dict):
                        thumb = str(ii[0].get("thumburl") or ii[0].get("url") or "").strip()
                        wm_cache[fid] = thumb
                        return thumb
            except Exception:
                pass
            wm_cache[fid] = ""
            return ""

        def _eu_thumb(record_id: str) -> str:
            rid = str(record_id or "").strip().lstrip("/")
            if not rid:
                return ""
            if rid in eu_cache:
                return eu_cache[rid] or ""
            try:
                wskey = (os.getenv("EUROPEANA_API_KEY") or "").strip()
                if not wskey:
                    eu_cache[rid] = ""
                    return ""
                api_url = f"https://api.europeana.eu/record/v2/{rid}.json"
                params = {"wskey": wskey, "profile": "rich"}
                r = requests.get(api_url, params=params, timeout=20, verify=False)
                r.raise_for_status()
                data = r.json() or {}
                obj = data.get("object") if isinstance(data.get("object"), dict) else {}
                prev = obj.get("edmPreview")
                if isinstance(prev, list) and prev:
                    eu_cache[rid] = str(prev[0] or "").strip()
                    return eu_cache[rid]
                if isinstance(prev, str) and prev.strip():
                    eu_cache[rid] = prev.strip()
                    return eu_cache[rid]
            except Exception:
                pass
            eu_cache[rid] = ""
            return ""

        def _thumb_for(aid: str) -> tuple[str, str]:
            src, raw = _split_source(aid)
            if src == "archive_org":
                return src, f"https://archive.org/services/img/{raw}"
            if src == "wikimedia":
                return src, _wm_thumb(raw)
            if src == "europeana":
                return src, _eu_thumb(raw)
            return src, ""
        
        total_beats = 0
        total_analyzed = 0
        
        for scene in manifest.get('scenes', []):
            # Map scene assets by id for metadata join
            assets = scene.get("assets") if isinstance(scene, dict) and isinstance(scene.get("assets"), list) else []
            by_id: Dict[str, Dict[str, Any]] = {}
            for a in assets:
                if isinstance(a, dict) and a.get("archive_item_id"):
                    by_id[str(a.get("archive_item_id"))] = a

            for beat in scene.get('visual_beats', []):
                total_beats += 1
                
                bid = str((beat or {}).get("block_id") or "").strip()
                beat_text = (
                    block_text.get(bid)
                    or str((beat or {}).get("narration_text") or (beat or {}).get("text_preview") or "").strip()
                )
                # Older manifests may not have shot_types → use keywords as lightweight context
                shot_types = (beat or {}).get("shot_types")
                if not isinstance(shot_types, list):
                    shot_types = []
                if not shot_types:
                    kws = (beat or {}).get("keywords")
                    if isinstance(kws, list):
                        shot_types = [str(x).strip() for x in kws if str(x).strip()][:10]

                candidates = (beat or {}).get('asset_candidates', [])
                if not isinstance(candidates, list):
                    candidates = []
                
                if not candidates:
                    if self.verbose:
                        print(f"⏭️  Beat {beat.get('block_id', '?')}: no candidates")
                    continue

                # Ensure candidates have thumbnails + basic metadata required by Vision.
                for c in candidates:
                    if not isinstance(c, dict):
                        continue
                    aid = str(c.get("archive_item_id") or "").strip()
                    if not aid:
                        continue
                    src, thumb = _thumb_for(aid)
                    # Store inferred source in a stable place for prompts
                    if not str(c.get("_source") or "").strip():
                        c["_source"] = src
                    # Enrich thumbnail_url (needed for analysis)
                    if not str(c.get("thumbnail_url") or "").strip():
                        c["thumbnail_url"] = thumb
                    # Enrich title/description from scene assets when missing (optional but helps)
                    ainfo = by_id.get(aid) or {}
                    if isinstance(ainfo, dict):
                        if not str(c.get("title") or "").strip() and ainfo.get("title"):
                            c["title"] = ainfo.get("title")
                        if not str(c.get("description") or "").strip() and ainfo.get("description"):
                            c["description"] = ainfo.get("description")
                
                if self.verbose:
                    print(f"\n📊 Analyzing beat {beat.get('block_id', '?')} ({len(candidates)} candidates)")
                
                reranked = self.rerank_candidates(
                    candidates=candidates,
                    beat_text=beat_text,
                    shot_types=shot_types,
                    max_analyze=max_analyze_per_beat
                )
                
                beat['asset_candidates'] = reranked
                # Auto-pick: if no manual selection exists, set selected_asset_id to the best candidate.
                # This ensures CompilationBuilder uses the same choice as LLM reranking.
                try:
                    existing_sel = str((beat or {}).get("selected_asset_id") or "").strip()
                    if not existing_sel and reranked:
                        # Prefer candidates explicitly recommended for use; otherwise fall back to top reranked.
                        best = None
                        for c in reranked:
                            if not isinstance(c, dict):
                                continue
                            va = c.get("_visual_analysis") if isinstance(c.get("_visual_analysis"), dict) else {}
                            rec = str(va.get("recommendation") or "").strip().lower()
                            score = va.get("relevance_score", None)
                            try:
                                score_f = float(score)
                            except Exception:
                                score_f = None
                            # Only auto-pick when the model is confident enough.
                            if rec == "use" and (score_f is None or score_f >= 0.6):
                                best = c
                                break
                        # If there is no strong "use" candidate, do NOT force a selection.
                        # (CB will still use the reranked order, but we avoid pinning a bad choice.)
                        if best and best.get("archive_item_id"):
                            beat["selected_asset_id"] = str(best.get("archive_item_id"))
                except Exception:
                    # Non-fatal: keep reranked list even if auto-pick fails
                    pass
                total_analyzed += min(len(candidates), max_analyze_per_beat)
        
        # Metadata
        manifest['_visual_assistant_metadata'] = {
            "model": self.model,
            "temperature": self.temperature,
            "total_beats": total_beats,
            "total_candidates_analyzed": total_analyzed,
            "max_analyze_per_beat": max_analyze_per_beat
        }
        
        # Save
        output = output_path or manifest_path
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        if self.verbose:
            print(f"\n✅ Visual Assistant finished:")
            print(f"   Analyzed: {total_analyzed} candidates across {total_beats} beats")
            print(f"   Saved to: {output}")
        
        return manifest
    
    def _call_vision_api(
        self,
        system_prompt: str,
        user_text: str,
        image_url: str
    ) -> str:
        """
        Volá Vision API (OpenAI nebo OpenRouter podle self.provider).
        
        Returns:
            JSON string response
        """
        # Build headers based on provider
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Provider-specific configuration
        if self.provider == "openrouter":
            api_url = "https://openrouter.ai/api/v1/chat/completions"
            headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost")
            headers["X-Title"] = os.getenv("OPENROUTER_APP_TITLE", "podcasts-visual-assistant")
            # OpenRouter model format: "openai/gpt-4o" 
            model = self.model if "/" in self.model else f"openai/{self.model}"
        else:
            api_url = "https://api.openai.com/v1/chat/completions"
            model = self.model
        
        payload: Dict[str, Any] = {
            "model": model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_text
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "low"  # Cheaper, faster, sufficient for thumbnails
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500
        }
        
        # Request STRICT JSON when possible.
        # - OpenAI: supported
        # - OpenRouter: often supported for OpenAI-routed models; if it errors, we retry without it.
        payload["response_format"] = {"type": "json_object"}
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=60)

        # OpenRouter compatibility: retry once without response_format if server rejects it.
        if self.provider == "openrouter" and response.status_code == 400 and "response_format" in payload:
            try:
                payload.pop("response_format", None)
            except Exception:
                pass
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
        
        response.raise_for_status()
        data = response.json() or {}

        try:
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        except Exception:
            content = ""
        if content is None:
            content = ""
        return str(content).strip()
    
    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        """
        Robust JSON parsing for model outputs.
        Handles:
        - empty responses
        - markdown fences ```json ... ```
        - extra prose around JSON (extract first {...} block)
        """
        raw = str(text or "").strip()
        if not raw:
            raise ValueError("Empty model response")

        s = raw.strip()
        # Strip markdown fences
        s = re.sub(r"^```\s*json\s*", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"^```\s*", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"```\s*$", "", s, flags=re.IGNORECASE).strip()

        # Extract first JSON object if wrapped in other text
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end+1]

        try:
            return json.loads(s)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON: {s[:200]}")
    
    def _parse_json_array(self, text: str) -> List[Dict[str, Any]]:
        """
        Robust JSON array parsing for batch responses.
        Handles:
        - markdown fences ```json ... ```
        - extra prose around JSON (extract first [...] block)
        """
        raw = str(text or "").strip()
        if not raw:
            raise ValueError("Empty model response")

        s = raw.strip()
        # Strip markdown fences
        s = re.sub(r"^```\s*json\s*", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"^```\s*", "", s, flags=re.IGNORECASE).strip()
        s = re.sub(r"```\s*$", "", s, flags=re.IGNORECASE).strip()

        # Extract first JSON array if wrapped in other text
        start = s.find("[")
        end = s.rfind("]")
        if start != -1 and end != -1 and end > start:
            s = s[start:end+1]

        try:
            result = json.loads(s)
            if not isinstance(result, list):
                raise ValueError(f"Expected array, got {type(result)}")
            return result
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON array: {s[:200]}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]

        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("Model response is not a JSON object")

        # Normalize required keys (defensive)
        obj.setdefault("relevance_score", 0.0)
        obj.setdefault("has_text_overlay", False)
        obj.setdefault("quality_issues", [])
        obj.setdefault("recommendation", "skip")
        obj.setdefault("reasoning", "")
        return obj
    
    def _default_system_prompt(self) -> str:
        """Default system prompt pro Visual Assistant."""
        return """You are a strict Vision Thumbnail Evaluator for documentary editing.

TASK
- Evaluate ONE candidate thumbnail image for ONE narration beat and return a JSON object only.

NON-NEGOTIABLE OUTPUT
- Output MUST be a single valid JSON object.
- Do NOT output markdown, prose, or code fences.
- Do NOT output extra keys.
- Always include ALL required keys, even if uncertain.
- "reasoning" MUST be in Czech (cs). Keep it 1–2 short sentences.

REQUIRED JSON SCHEMA (EXACT KEYS)
{
  "relevance_score": 0.0,
  "has_text_overlay": false,
  "quality_issues": [],
  "recommendation": "use",
  "reasoning": ""
}

SCORING
- relevance_score (0.0–1.0): Relevance to beat context is #1 priority.

QUALITY / SAFETY
- Penalize strongly: subtitles/captions, UI overlays, watermarks/logos, wrong era/event, too modern look for historical beats.

recommendation
- "use": relevant + usable
- "skip": mismatch or heavy overlays
- "fallback": ONLY if image is not interpretable / analysis uncertain (otherwise prefer 'skip')"""
    
    def _build_user_message(
        self,
        beat_text: str,
        shot_types: List[str],
        candidate_metadata: Dict[str, Any]
    ) -> str:
        """Build user message pro Vision API."""
        return f"""Analyze this thumbnail for a documentary video.

SCENE CONTEXT:
Narration: "{beat_text}"
Desired shot types: {', '.join(shot_types)}

CANDIDATE METADATA:
Title: {candidate_metadata.get('title', 'Unknown')}
Description: {candidate_metadata.get('description', 'N/A')}
Source: {candidate_metadata.get('source', 'unknown')}

Does this thumbnail match the scene? Any quality issues? Should we use it?
Respond ONLY with JSON."""


def run_visual_assistant(
    episode_id: str,
    projects_dir: str,
    api_key: str,
    model: str = "gpt-4o",
    temperature: float = 0.3,
    custom_prompt: Optional[str] = None,
    max_analyze_per_beat: int = 5,
    verbose: bool = True,
    provider: str = "openai"
) -> Dict[str, Any]:
    """
    Entry point: Spustí Visual Assistant pro daný episode.
    
    Args:
        episode_id: ID epizody
        projects_dir: Cesta k projects složce
        api_key: API key (OpenAI nebo OpenRouter)
        model: Model (gpt-4o)
        temperature: Temperature
        custom_prompt: Custom prompt (optional)
        max_analyze_per_beat: Max kandidátů k analýze per beat
        verbose: Logování
        provider: "openai" nebo "openrouter"
    
    Returns:
        Upravený manifest dict
    """
    from project_store import ProjectStore
    
    store = ProjectStore(projects_dir)
    episode_dir = store.episode_dir(episode_id)
    manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
    
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(
            f"Archive manifest not found. Run AAR (Preview) first: {manifest_path}"
        )
    
    assistant = VisualAssistant(
        api_key=api_key,
        model=model,
        temperature=temperature,
        custom_prompt=custom_prompt,
        verbose=verbose,
        provider=provider
    )
    
    return assistant.process_manifest(
        manifest_path=manifest_path,
        output_path=None,  # Přepíše original
        max_analyze_per_beat=max_analyze_per_beat
    )


if __name__ == '__main__':
    # Test
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python visual_assistant.py <episode_id>")
        sys.exit(1)
    
    episode_id = sys.argv[1]
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        sys.exit(1)
    
    result = run_visual_assistant(
        episode_id=episode_id,
        projects_dir='../projects',
        api_key=api_key,
        verbose=True
    )
    
    print(f"\n✅ Done! Analyzed {result['_visual_assistant_metadata']['total_candidates_analyzed']} candidates")


