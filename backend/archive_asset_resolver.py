"""
Archive Asset Resolver (AAR) - 7. krok v pipeline

Převádí search_queries z FDA na konkrétní archive.org itemy.
ŽÁDNÉ stahování videí (to dělá CompilationBuilder).
POUZE vyhledávání a naplnění assets[] konkrétními URL/ID.

MULTI-SOURCE SUPPORT:
- Archive.org (primary)
- Wikimedia Commons (secondary)
- Europeana (optional, requires API key)
"""

import json
import time
import requests
from typing import Dict, List, Any, Tuple, Optional, Callable
from datetime import datetime, timezone
import os
import hashlib
import re
import subprocess
import math
# ========================================================================
# AAR hard-fail exception with structured details (for script_state.error.details)
# ========================================================================
class AARHardFail(RuntimeError):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = str(code or "AAR_ERROR")
        self.details = details or {}
        super().__init__(f"{self.code}: {message}")


# Import multi-source video providers
try:
    from video_sources import create_multi_source_searcher, LICENSE_PRIORITY, YOUTUBE_SAFE_LICENSES
    MULTI_SOURCE_AVAILABLE = True
except ImportError as e:
    MULTI_SOURCE_AVAILABLE = False
    print("⚠️  Multi-source video providers not available (video_sources.py missing)")
    # #region agent log
    try:
        import time as _time, json as _json, os as _os, sys as _sys
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H1",
                "location": "backend/archive_asset_resolver.py:import_video_sources",
                "message": "ImportError while importing video_sources; multi-source disabled",
                "data": {
                    "error_type": type(e).__name__,
                    "error_str": str(e)[:300],
                    "cwd": _os.getcwd(),
                    "sys_path_0": str(_sys.path[0]) if isinstance(getattr(_sys, "path", None), list) and _sys.path else "",
                    "this_file": __file__,
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion

# B: Cache versioning - bump při změně search/scoring/gates/heuristik
# v11: tighten anchor stopwords (months/discourse) + improve anchor extraction order (prefer search_queries)
# v12: add doc/texts stage (map/document fallback) + richer diagnostics
# v13: per-scene diagnostics + global fallback query pack
# v14: LLM-based topic relevance validation (prevents off-topic contamination)
AAR_CACHE_VERSION = "v14_topic_relevance"

# ============================================================================
# LLM-BASED TOPIC RELEVANCE VALIDATOR
# ============================================================================
# Prevents off-topic contamination by validating candidates against episode topic.
# Example: "maxwell-chikumbutso-new-energy-zimbabwe" rejected for "Nikola Tesla" episode.
#
# Env:
#   AAR_ENABLE_LLM_TOPIC_VALIDATION=1  (default: 1 - ENABLED)
#   AAR_LLM_TOPIC_VALIDATION_MODEL=gpt-4o-mini  (default: gpt-4o-mini for speed/cost)
#

def validate_candidates_topic_relevance(
    candidates: List[Dict[str, Any]],
    episode_topic: str,
    scene_context: Optional[Dict[str, Any]] = None,
    max_candidates: int = 20,
    verbose: bool = False,
    use_vision: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    LLM-based validation of candidate relevance to episode topic.
    
    Uses LLM (with optional Vision) to filter out off-topic candidates BEFORE
    they are added to manifest. This prevents issues like Zimbabwe news
    appearing in a Nikola Tesla documentary.
    
    SUPPORTS: OpenRouter (preferred) or OpenAI as fallback.
    
    Args:
        candidates: List of asset candidates from search
        episode_topic: Main episode topic (e.g., "Nikola Tesla")
        scene_context: Optional dict with scene info:
            - narration_summary: Brief scene description
            - search_queries: Queries used to find candidates
            - keywords: Scene keywords
            - emotion: Scene emotion
        max_candidates: Max candidates to validate in one batch
        verbose: Enable debug logging
        use_vision: If True, include thumbnail URLs for visual analysis (requires vision model)
    
    Returns:
        (relevant_candidates, rejected_candidates, validation_report)
    """
    if not episode_topic or not candidates:
        return candidates, [], {"skipped": True, "reason": "no_topic_or_empty_candidates"}
    
    # Check if validation is enabled (default: YES)
    enabled = str(os.getenv("AAR_ENABLE_LLM_TOPIC_VALIDATION", "1")).strip().lower() in ("1", "true", "yes")
    if not enabled:
        if verbose:
            print(f"⚠️  AAR: LLM topic validation disabled (AAR_ENABLE_LLM_TOPIC_VALIDATION=0)")
        return candidates, [], {"skipped": True, "reason": "disabled_by_env"}
    
    # Determine provider: prefer OpenRouter, fallback to OpenAI
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if openrouter_key:
        provider = "openrouter"
        api_key = openrouter_key
        # For Vision, use gpt-4o; for text-only use gpt-4o-mini
        default_model = "openai/gpt-4o" if use_vision else "openai/gpt-4o-mini"
        model = os.getenv("AAR_LLM_TOPIC_VALIDATION_MODEL", default_model)
        api_url = "https://openrouter.ai/api/v1/chat/completions"
    elif openai_key:
        provider = "openai"
        api_key = openai_key
        default_model = "gpt-4o" if use_vision else "gpt-4o-mini"
        model = os.getenv("AAR_LLM_TOPIC_VALIDATION_MODEL", default_model)
        api_url = "https://api.openai.com/v1/chat/completions"
    else:
        if verbose:
            print(f"⚠️  AAR: LLM topic validation skipped - no OPENROUTER_API_KEY or OPENAI_API_KEY")
        return candidates, [], {"skipped": True, "reason": "no_api_key"}
    
    # Prepare batch for validation (limit to max_candidates)
    batch = candidates[:max_candidates]
    
    # Extract scene context
    scene_narration = ""
    scene_queries = []
    scene_keywords = []
    if scene_context and isinstance(scene_context, dict):
        scene_narration = str(scene_context.get("narration_summary", ""))[:300]
        sq = scene_context.get("search_queries", [])
        if isinstance(sq, list):
            scene_queries = [str(q.get("query") if isinstance(q, dict) else q)[:60] for q in sq[:5]]
        kw = scene_context.get("keywords", [])
        if isinstance(kw, list):
            scene_keywords = [str(k)[:30] for k in kw[:8]]
    
    # Build validation prompt with FULL CONTEXT
    items_text = ""
    thumbnail_urls = []
    for i, cand in enumerate(batch):
        title = str(cand.get("title", ""))[:120]
        desc = str(cand.get("description", ""))[:250]
        item_id = str(cand.get("archive_item_id", ""))[:80]
        query_used = str(cand.get("query_used", ""))[:60]
        source = str(cand.get("_source", cand.get("provider", "archive_org")))
        
        items_text += f"\n{i+1}. ID: {item_id}"
        items_text += f"\n   Title: {title}"
        items_text += f"\n   Description: {desc[:200]}..."
        items_text += f"\n   Source: {source}"
        if query_used:
            items_text += f"\n   Found via query: \"{query_used}\""
        
        # Collect thumbnail URLs for vision
        thumb_url = cand.get("thumbnail_url")
        if not thumb_url and "archive_item_id" in cand:
            # Generate archive.org thumbnail URL
            aid = str(cand.get("archive_item_id", "")).replace("archive_org:", "")
            if aid and not aid.startswith(("wikimedia:", "europeana:", "local_safety_pack:")):
                thumb_url = f"https://archive.org/services/img/{aid}"
        thumbnail_urls.append(thumb_url)
        items_text += "\n"
    
    # Build rich system prompt with scene context
    system_prompt = f"""You are an expert video archivist validating footage for a documentary.

═══════════════════════════════════════════════════════════════════════════════
EPISODE TOPIC: "{episode_topic}"
═══════════════════════════════════════════════════════════════════════════════"""
    
    if scene_narration:
        system_prompt += f"""

CURRENT SCENE NARRATION:
"{scene_narration}"
"""
    
    if scene_queries:
        system_prompt += f"""
SEARCH QUERIES USED TO FIND THESE CANDIDATES:
{', '.join(scene_queries)}
"""
    
    if scene_keywords:
        system_prompt += f"""
SCENE KEYWORDS:
{', '.join(scene_keywords)}
"""
    
    system_prompt += """
═══════════════════════════════════════════════════════════════════════════════

YOUR TASK:
Evaluate each candidate video/image and determine if it is RELEVANT to this documentary.

STRICT RULES:
1. RELEVANT = The content directly relates to the episode topic or scene narration
2. IRRELEVANT = The content is about a completely different subject, person, event, or era
3. Be VERY STRICT about false matches:
   - "free energy" from Zimbabwe ≠ Nikola Tesla documentary
   - Random news footage ≠ Historical documentary
   - Children's shows, conspiracy videos, unrelated topics = REJECT
4. Generic archival footage (maps, documents, period photos) IS relevant if it matches the era/topic
5. If title/description mentions a DIFFERENT person as the main subject = IRRELEVANT

RESPOND WITH JSON ARRAY ONLY:
[
  {"index": 1, "relevant": true, "confidence": 0.95, "reason": "Documentary about subject"},
  {"index": 2, "relevant": false, "confidence": 0.99, "reason": "Different person entirely"}
]

Each object must have: index (1-N), relevant (bool), confidence (0.0-1.0), reason (brief explanation)"""

    user_message = f"""Analyze these {len(batch)} archive candidates for the documentary about "{episode_topic}":

{items_text}

Evaluate EACH candidate (index 1 to {len(batch)}) and return JSON array with your decisions."""

    try:
        import requests as req
        
        # Build headers based on provider
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost")
            headers["X-Title"] = os.getenv("OPENROUTER_APP_TITLE", "podcasts-aar")
        
        # Build message content - optionally with thumbnails for Vision
        valid_thumbnails = [url for url in thumbnail_urls if url and isinstance(url, str) and url.startswith("http")]
        
        # Use Vision if enabled and we have thumbnails
        actually_use_vision = use_vision and len(valid_thumbnails) >= 2
        
        if actually_use_vision:
            # Vision API format: array of content items
            user_content = [
                {"type": "text", "text": user_message},
            ]
            # Add thumbnail images (limit to first 5 to avoid token limits)
            for i, thumb_url in enumerate(valid_thumbnails[:5]):
                if thumb_url:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": thumb_url, "detail": "low"}  # low detail = faster/cheaper
                    })
            
            messages = [
                {"role": "system", "content": system_prompt + "\n\nI'm also showing you thumbnail images of the candidates. Use visual inspection to verify relevance."},
                {"role": "user", "content": user_content}
            ]
            if verbose:
                print(f"🔍 AAR Topic Validation: Using {provider} ({model}) with VISION ({len(valid_thumbnails)} thumbnails)")
        else:
            # Text-only mode
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            if verbose:
                print(f"🔍 AAR Topic Validation: Using {provider} ({model}) text-only")
        
        resp = req.post(
            api_url,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 2000
            },
            timeout=60  # Longer timeout for vision
        )
        resp.raise_for_status()
        
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # --------------------------------------------------------------------
        # Robust parsing of JSON array output (models sometimes add prose/fences)
        # --------------------------------------------------------------------
        def _parse_decisions_json(raw: str) -> List[Dict[str, Any]]:
            s = str(raw or "").strip()
            if not s:
                raise ValueError("empty_response")
            # Strip markdown fences
            s = re.sub(r"^```(?:json)?\\s*", "", s, flags=re.IGNORECASE).strip()
            s = re.sub(r"\\s*```\\s*$", "", s, flags=re.IGNORECASE).strip()
            # Extract first JSON array if surrounded by other text
            if "[" in s and "]" in s:
                s2 = s[s.find("[") : s.rfind("]") + 1]
            else:
                s2 = s
            obj = json.loads(s2)
            # Sometimes the model returns an object wrapper
            if isinstance(obj, dict):
                for k in ("decisions", "items", "results", "data"):
                    if isinstance(obj.get(k), list):
                        obj = obj.get(k)
                        break
            if not isinstance(obj, list):
                raise ValueError("not_a_json_array")
            return [x for x in obj if isinstance(x, dict)]

        def _heuristic_anchor_tokens(topic: str, ctx: Optional[Dict[str, Any]]) -> List[str]:
            """
            Conservative fallback if LLM parsing fails:
            require at least one strong anchor token in title/description.
            This prevents catastrophic off-topic picks (e.g., movies/comedies) when the LLM response is unusable.
            """
            stop = {
                # generic glue words
                "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "from",
                # generic doc words
                "documentary", "episode", "part", "story", "history", "historical",
                "video", "footage", "film", "archive", "archival",
                # overly generic time words
                "day", "days", "last", "final", "life", "death", "hours", "hour",
                # pronouns
                "her", "his", "their", "she", "he", "they", "it", "this", "that",
            }

            toks: List[str] = []
            base = f"{topic or ''}"
            if ctx and isinstance(ctx, dict):
                base += " " + str(ctx.get("narration_summary") or "")
                # keywords/search_queries can be noisy; include lightly
                kws = ctx.get("keywords") or []
                if isinstance(kws, list):
                    base += " " + " ".join(str(x) for x in kws[:10] if str(x or "").strip())
            for t in re.findall(r"[a-z0-9]{3,}", base.lower()):
                if t in stop:
                    continue
                if t not in toks:
                    toks.append(t)
            # Prefer longer tokens (more specific)
            toks = sorted(toks, key=lambda x: (-len(x), x))
            return toks[:12]

        decisions = None
        try:
            decisions = _parse_decisions_json(content)
        except Exception as parse_err:
            # LLM response unusable → heuristic fallback (FAIL-CLOSED against off-topic contamination)
            anchors = _heuristic_anchor_tokens(episode_topic, scene_context)
            relevant = []
            rejected = []
            for cand in candidates[:max_candidates]:
                if not isinstance(cand, dict):
                    continue
                hay = " ".join(
                    [
                        str(cand.get("title") or ""),
                        str(cand.get("description") or ""),
                        str(cand.get("subject") or ""),
                        str(cand.get("collection") or ""),
                        str(cand.get("archive_item_id") or ""),
                    ]
                ).lower()
                hit = any(a in hay for a in anchors) if anchors else False
                cand["_topic_validation"] = {
                    "relevant": bool(hit),
                    "reason": "heuristic_anchor_match" if hit else "heuristic_no_anchor_match",
                    "anchors_used": anchors[:8],
                }
                (relevant if hit else rejected).append(cand)

            # Remaining candidates beyond batch: apply same heuristic to keep behavior consistent
            for cand in candidates[max_candidates:]:
                if not isinstance(cand, dict):
                    continue
                hay = " ".join(
                    [
                        str(cand.get("title") or ""),
                        str(cand.get("description") or ""),
                        str(cand.get("subject") or ""),
                        str(cand.get("collection") or ""),
                        str(cand.get("archive_item_id") or ""),
                    ]
                ).lower()
                hit = any(a in hay for a in anchors) if anchors else False
                cand["_topic_validation"] = {
                    "relevant": bool(hit),
                    "reason": "heuristic_anchor_match" if hit else "heuristic_no_anchor_match",
                    "anchors_used": anchors[:8],
                }
                (relevant if hit else rejected).append(cand)

            report = {
                "skipped": True,
                "reason": f"llm_parse_failed_fallback_heuristic: {parse_err}",
                "provider": provider,
                "model": model,
                "topic": episode_topic,
                "scene_context_provided": bool(scene_context and scene_narration),
                "vision_used": actually_use_vision,
                "thumbnails_analyzed": len(valid_thumbnails) if actually_use_vision else 0,
                "validated_count": min(len(candidates), max_candidates),
                "relevant_count": len(relevant),
                "rejected_count": len(rejected),
                "rejected_items": [{"id": r.get("archive_item_id"), "reason": r.get("_topic_validation", {}).get("reason")} for r in rejected[:5]],
            }
            if verbose:
                print(f"⚠️  AAR Topic Validation: LLM parse failed ({parse_err}) → heuristic fallback. relevant={len(relevant)} rejected={len(rejected)}")
            return relevant, rejected, report

        # Apply decisions (STRICT: missing decision defaults to IRRELEVANT)
        relevant = []
        rejected = []
        decision_map: Dict[int, Dict[str, Any]] = {}
        for d in (decisions or []):
            try:
                idx_raw = d.get("index")
                idx_int = int(idx_raw)
            except Exception:
                continue
            decision_map[idx_int] = d

        for i, cand in enumerate(batch):
            idx = i + 1
            decision = decision_map.get(idx)
            if not isinstance(decision, dict):
                # Missing decision for this index => reject (safe default)
                cand["_topic_validation"] = {"relevant": False, "reason": "missing_decision_for_index"}
                rejected.append(cand)
                continue

            is_relevant = bool(decision.get("relevant", False))
            reason = decision.get("reason", "Accepted by LLM" if is_relevant else "Rejected by LLM")
            cand["_topic_validation"] = {"relevant": bool(is_relevant), "reason": str(reason)[:240]}

            if is_relevant:
                relevant.append(cand)
            else:
                rejected.append(cand)
                if verbose:
                    print(f"  ❌ Topic mismatch: {cand.get('title', '')[:60]} - {reason}")
        
        # Add remaining candidates (beyond max_candidates) WITHOUT validation:
        # Conservative choice: require at least some anchor overlap; otherwise reject.
        # This prevents off-topic "popular" items from slipping in beyond the validated batch.
        anchors_fallback = _heuristic_anchor_tokens(episode_topic, scene_context)
        for cand in candidates[max_candidates:]:
            if not isinstance(cand, dict):
                continue
            hay = " ".join(
                [
                    str(cand.get("title") or ""),
                    str(cand.get("description") or ""),
                    str(cand.get("subject") or ""),
                    str(cand.get("collection") or ""),
                    str(cand.get("archive_item_id") or ""),
                ]
            ).lower()
            hit = any(a in hay for a in anchors_fallback) if anchors_fallback else False
            cand["_topic_validation"] = {
                "relevant": bool(hit),
                "reason": "heuristic_anchor_match (beyond batch)" if hit else "heuristic_no_anchor_match (beyond batch)",
            }
            (relevant if hit else rejected).append(cand)
        
        report = {
            "skipped": False,
            "provider": provider,
            "model": model,
            "topic": episode_topic,
            "scene_context_provided": bool(scene_context and scene_narration),
            "vision_used": actually_use_vision,
            "thumbnails_analyzed": len(valid_thumbnails) if actually_use_vision else 0,
            "validated_count": len(batch),
            "relevant_count": len([c for c in batch if c.get("_topic_validation", {}).get("relevant")]),
            "rejected_count": len(rejected),
            "rejected_items": [{"id": r.get("archive_item_id"), "reason": r.get("_topic_validation", {}).get("reason")} for r in rejected[:5]]
        }
        
        if verbose:
            print(f"🔍 AAR Topic Validation: {report['relevant_count']}/{report['validated_count']} relevant to '{episode_topic}'")
            if rejected:
                print(f"   Rejected {len(rejected)} off-topic candidates")
        
        return relevant, rejected, report
        
    except json.JSONDecodeError as e:
        # Should be rare due to robust parsing above, but keep a safe fallback.
        if verbose:
            print(f"⚠️  AAR: LLM topic validation failed (JSON parse): {e}")
        anchors = [t for t in re.findall(r"[a-z0-9]{3,}", str(episode_topic or "").lower()) if t]
        relevant = []
        rejected = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            hay = " ".join([str(cand.get("title") or ""), str(cand.get("description") or ""), str(cand.get("archive_item_id") or "")]).lower()
            hit = any(a in hay for a in anchors) if anchors else False
            cand["_topic_validation"] = {"relevant": bool(hit), "reason": "json_parse_error_fallback"}
            (relevant if hit else rejected).append(cand)
        return relevant, rejected, {"skipped": True, "reason": f"json_parse_error: {e}"}
    except Exception as e:
        if verbose:
            print(f"⚠️  AAR: LLM topic validation failed: {e}")
        anchors = [t for t in re.findall(r"[a-z0-9]{3,}", str(episode_topic or "").lower()) if t]
        relevant = []
        rejected = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            hay = " ".join([str(cand.get("title") or ""), str(cand.get("description") or ""), str(cand.get("archive_item_id") or "")]).lower()
            hit = any(a in hay for a in anchors) if anchors else False
            cand["_topic_validation"] = {"relevant": bool(hit), "reason": f"exception_fallback: {str(e)[:120]}"}
            (relevant if hit else rejected).append(cand)
        return relevant, rejected, {"skipped": True, "reason": f"error: {e}"}

# ============================================================================
# GLOBAL FALLBACK QUERIES
# ============================================================================
# IMPORTANT (Episode Anchor Lock):
# Global, topic-agnostic fallback queries are a major source of off-topic contamination
# (e.g., "Moscow 1812" visuals showing up in unrelated episodes).
#
# This project policy is **NO GLOBAL FALLBACK** by default.
# If you *really* need fallback behavior, implement an EPISODE-ANCHORED fallback list
# derived from the scene/episode anchors and enable it explicitly.
#
# Env:
#   AAR_ENABLE_GLOBAL_FALLBACK_QUERIES=1  (default: 0)
#
# For safety, the default list is empty.
GLOBAL_FALLBACK_QUERIES: List[str] = []

# SYNONYM SETS for robust visual noun matching (Section 4)
VISUAL_SYNONYM_GROUPS = {
    "documents": ["document", "documents", "paper", "papers", "paperwork", "record", "records", 
                  "file", "files", "archive", "archival", "memorandum", "letter", "letters"],
    "maps": ["map", "maps", "chart", "charts", "diagram", "diagrams", "atlas"],
    "office": ["office", "desk", "interior", "room", "bureau", "administration"],
    "aftermath": ["ruin", "ruins", "rubble", "destruction", "aftermath", "recovery", "rebuilding"],
}

# FORBIDDEN PATTERNS (context-aware - depends on shot_types)
# Section 5 - Rule 3
# shot_types are from FDA ALLOWED_SHOT_TYPES enum:
# - historical_battle_footage, troop_movement, leaders_speeches, civilian_life,
#   destruction_aftermath, industry_war_effort, maps_context, archival_documents,
#   atmosphere_transition
FORBIDDEN_FOR_NON_COMBAT = [
    "famous battle", "greatest battle", "epic battle", "best battle",
    "compilation", "montage", "highlights", "greatest moments",
    "frontline combat", "battlefield", "combat footage",
    "famous speech", "iconic speech", "churchill speech"
]

# Shot types that allow combat/battle footage (from FDA enum)
COMBAT_ALLOWED_SHOT_TYPES = {
    "historical_battle_footage",
    "troop_movement",
    "destruction_aftermath"
}

# Search tuning (A/B/C/E)
# Media cascade:
#   1) video (movies/movingimage)
#   2) images (image)  -> can be Ken Burns / stills
ARCHIVE_VIDEO_MEDIATYPE_FILTER = "movies OR movingimage"
ARCHIVE_IMAGE_MEDIATYPE_FILTER = "image"
# Third fallback: documents/maps often live under archive.org "texts" with image derivatives (jpg/png pages)
ARCHIVE_TEXT_MEDIATYPE_FILTER = "texts"
# Backward compatible default (video-first)
ARCHIVE_MEDIATYPE_FILTER = ARCHIVE_VIDEO_MEDIATYPE_FILTER
SEARCH_ROWS_STRICT = 50
SEARCH_ROWS_RELAXED = 100
MIN_RESULTS_TO_STOP_BROADENING = 10   # N: numFound proxy target
MIN_APPROVED_TO_STOP_BROADENING = 3   # K: after_gates target

# E) Negative terms to reduce talks/studios directly in search (not a hard gate)
NEGATIVE_SEARCH_TERMS = [
    "lecture",
    "conference",
    "panel",
    "plenary",
    "keynote",
    "seminar",
    "congress",
    "interview",
    "talkshow",
    "newsroom",
]

# ═══════════════════════════════════════════════════════════════════════════
# ASSET RANKING SYSTEM (requirement #1)
# ═══════════════════════════════════════════════════════════════════════════

# ANCHOR DICTIONARY (requirement #4) - povolené historické anchory
ALLOWED_HISTORICAL_ANCHORS = {
    # Osoby (Napoleon era)
    "napoleon", "bonaparte", "alexander", "tsar", "rostopchin", "kutuzov", "barclay",
    "murat", "ney", "davout", "bagration",
    
    # Místa
    "moscow", "kremlin", "russia", "russian", "france", "french", "smolensk", 
    "borodino", "petersburg", "saint petersburg", "vilnius", "berlin", "paris",
    
    # Fyzické artefakty (CONCRETE visual nouns)
    "map", "maps", "letter", "letters", "manuscript", "manuscripts", "engraving",
    "engravings", "painting", "paintings", "portrait", "portraits", "lithograph",
    "lithographs", "etching", "etchings", "document", "documents", "correspondence",
    "palace", "building", "buildings", "cathedral", "church", "fortress",
    
    # Vizuální formáty (archival context)
    "nineteenth century", "19th century", "eighteenth century", "18th century",
    "archival", "historical", "newsreel", "photograph", "photographs",
    
    # Roky (Napoleon era + WWII fallback)
    "1812", "1813", "1814", "1815", "1805", "1806", "1807", "1808", "1809",
    "1939", "1940", "1941", "1942", "1943", "1944", "1945",
}

# QUALITY FLOOR (requirement #5)
ASSET_RANKING_QUALITY_FLOOR = 0.45  # If best candidate < 0.45, use maps/documents fallback

# HARD FILTERS (requirement #2) - expanded to catch modern stock/AI/compilations
ASSET_HARD_REJECT_PATTERNS = [
    # Compilations / montages
    r"\bcompilation\b", r"\bmontage\b", r"\bhighlights?\b", r"\bbest\s+of\b",
    r"\btop\s+\d+\b", r"\bgreatest\s+moments\b",
    
    # Modern stock / AI
    r"\bstock\s+footage\b", r"\bai\s+generated\b", r"\bai\s+colorized\b",
    r"\bcolorized\s+by\b", r"\bupscaled\b", r"\b4k\s+remaster\b",
    
    # Random / generic
    r"\brandom\b", r"\bmix\b", r"\bmixing\b", r"\bvarious\b",
    
    # Modern context (unless clearly historical)
    r"\bmodern\s+war\b", r"\bcurrent\s+events\b", r"\b202[0-9]\b", r"\b201[5-9]\b",
]

# Duration sanity limits (requirement #1, signal 4)
MIN_VIABLE_DURATION_SEC = 5     # < 5 sec = too short (likely intro/logo)
MAX_VIABLE_DURATION_SEC = 3600  # > 1 hour = too long (likely documentary/compilation)

# Preferred collections (requirement #1, signal 3)
TRUSTED_COLLECTIONS = {
    "prelinger", "british_pathe", "national_archives", "imperial_war_museum",
    "library_of_congress", "ushmm", "national_film_board", "bundesarchiv",
    "europeana", "wikimedia",
}

# 1) HARD REJECT - always ban (animated/kids/obvious junk/modern talks)
HARD_REJECT_PATTERNS = [
    # Animated / Kids content (HARD - always reject)
    r"\banimated\b", r"\bcartoon\b", r"\banime\b",
    r"\btoy\b", r"\bkids\b", r"\bchildren\b", r"\bmonstrux\b", r"\bgiantess\b",
    r"\bback\s+to\s+the\s+future.*animated\b",  # specific bad example
    r"\bsize\s+comparison\b",  # youtube junk
    # Modern talks / conferences (HARD - always reject)
    r"\bplenary\b", r"\bcongress\b", r"\bworld\s+congress\b", r"\bkeynote\b",
    r"\bpanel\s+discussion\b", r"\blecture\b", r"\bseminar\b", r"\bconference\b",
    r"\bnewsroom\b", r"\btalk\s+show\b", r"\bpundit\b",
    # Specific known junk
    r"\bgatto\b", r"\bgulag\s+usa\b", r"\bjiu-?jitsu\b"
]

# CONDITIONAL REJECT - season/episode/series (OK if historical, else reject)
CONDITIONAL_PATTERNS = [
    r"\bs\d{1,2}[e\-]\d{1,2}\b",  # S01E01, s02-e03
    r"\bseason\s+\d+\b", r"\bepisode\s+\d+\b",
    r"\bseries\b", r"\btv\b"
]

# SOFT PENALIZE - not automatically bad, just often off-topic
SOFT_PENALIZE_PATTERNS = [
    r"\beducation\b", r"\blesson\b", r"\bclassroom\b",
    r"\btraining\s+film\b", r"\bschool\b", r"\bteacher\b"
]

# 2) WWII/historical must-hit - expanded to catch more relevant content
HISTORY_WHITELIST_TOKENS = {
    # WWII specific (broader)
    "wwii", "ww2", "world war", "world war ii", "world war 2", "second world war",
    "wartime", "war time", "1940s",
    # Military/Naval (expanded)
    "naval", "army", "military", "warfare", "battle", "raid", "invasion", "assault",
    "battleship", "destroyer", "submarine", "aircraft", "fleet", "navy", "marines",
    "commando", "troops", "soldier", "sailor",
    # Key nations/groups
    "allied", "allies", "axis", "german", "germany", "british", "britain", 
    "american", "america", "nazi", "soviet", "japan", "japanese", "french", "france",
    # Operations/Events (expanded)
    "operation", "campaign", "offensive", "defense", "defence", "siege", 
    "sabotage", "intelligence", "deception", "espionage", "occupied", "occupation",
    # Infrastructure/Objects
    "dock", "port", "harbor", "fortress", "bunker", "fortification",
    # Documentary markers
    "documentary", "archive", "footage", "historical", "history", "war film",
    "archival", "newsreel", "propaganda",
    # Specific locations (expanded)
    "normandy", "atlantic", "pacific", "europe", "africa", "asia",
    "st nazaire", "france", "germany", "england", "mediterranean",
    # Specific operations/people (add more as needed)
    "tirpitz", "bismarck", "campbeltown", "mincemeat", "overlord", "barbarossa",
    # Time period (expanded)
    "1939", "1940", "1941", "1942", "1943", "1944", "1945",
    "39", "40", "41", "42", "43", "44", "45"  # short years in titles
}


def _now_iso() -> str:
    """Vrací ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ═══════════════════════════════════════════════════════════════════════════
# ASSET RANKING FUNCTIONS (requirement #1, #2, #5)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_scene_anchors(scene: Dict[str, Any]) -> List[str]:
    """
    Extract anchor terms from scene (requirement #4 - Anchor Dictionary).
    Returns ONLY allowed historical anchors from keywords + narration_summary.
    """
    anchors = []
    
    # Keywords
    for kw in (scene.get("keywords") or []):
        kw_lower = str(kw or "").lower().strip()
        if kw_lower in ALLOWED_HISTORICAL_ANCHORS:
            anchors.append(kw_lower)
    
    # Proper nouns from narration_summary
    summary = str(scene.get("narration_summary") or "")
    for token in re.findall(r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b', summary):
        token_lower = token.lower()
        if token_lower in ALLOWED_HISTORICAL_ANCHORS:
            anchors.append(token_lower)
    
    # Years (1812, etc.)
    for year in re.findall(r'\b1[0-9]{3}\b', summary):
        if year in ALLOWED_HISTORICAL_ANCHORS:
            anchors.append(year)
    
    # Deduplicate
    return list(dict.fromkeys(anchors))


def _apply_hard_filters(asset: Dict[str, Any], verbose: bool = False) -> Tuple[bool, str]:
    """
    Hard filters for assets (requirement #2).
    Returns (is_valid, reject_reason).
    
    Filters:
    - Must have playable video file (not just images/text)
    - No compilations/montages/random
    - No modern stock/AI
    - Duration sanity (5 sec - 1 hour)
    """
    item_id = asset.get("archive_item_id", "")
    title = str(asset.get("title", "")).lower()
    desc = str(asset.get("description", "")).lower()
    combined = f"{title} {desc}"
    
    # 1) Check for playable video
    media_type = str(asset.get("media_type", "")).lower()
    if media_type not in ("video", "movies", "movingimage"):
        return False, "not_playable_video"
    
    # 2) Check for compilations/montages/modern stock
    for pattern in ASSET_HARD_REJECT_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            if verbose:
                matched = re.search(pattern, combined, re.IGNORECASE)
                print(f"🚫 HARD_FILTER: '{title[:60]}' rejected by pattern '{pattern}' (matched: {matched.group(0) if matched else 'N/A'})")
            return False, f"pattern:{pattern}"
    
    # 3) Duration sanity
    duration = asset.get("duration_sec", 0)
    if duration > 0:
        if duration < MIN_VIABLE_DURATION_SEC:
            if verbose:
                print(f"🚫 HARD_FILTER: '{title[:60]}' too short ({duration}s < {MIN_VIABLE_DURATION_SEC}s)")
            return False, "too_short"
        if duration > MAX_VIABLE_DURATION_SEC:
            if verbose:
                print(f"🚫 HARD_FILTER: '{title[:60]}' too long ({duration}s > {MAX_VIABLE_DURATION_SEC}s)")
            return False, "too_long"
    
    return True, ""


def _rank_asset(asset: Dict[str, Any], scene_anchors: List[str], shot_types: List[str] = None, verbose: bool = False) -> Tuple[float, Dict[str, Any]]:
    """
    NEW RELEVANCE SCORING (10 pravidel - deterministické, 0.0-1.0)
    
    Cíl: Vybrat NEJLEPŠÍ výsledek, ne failovat.
    
    ✅ PLUS BODY:
    1. +0.25 pokud TITLE obsahuje anchor
    2. +0.15 pokud DESCRIPTION obsahuje anchor
    3. +0.15 pokud obsahuje archivní formát (engraving/map/manuscript/letter/archival/photograph)
    4. +0.10 pokud délka videa je v rozumném rozsahu (10s-3min)
    5. +0.10 pokud typ odpovídá shot_type (map/document/city view)
    
    ❌ MÍNUS BODY:
    6. −0.30 pokud TITLE/DESC obsahuje: montage/compilation/highlights/edit/HD/full documentary
    7. −0.15 pokud je video extrémně krátké (<5s) nebo dlouhé (>20min)
    8. −0.20 pokud TITLE je generický ("historical footage", "old video")
    
    Returns:
        (score_0_to_1, debug_dict)
    """
    title = str(asset.get("title", "")).lower()
    desc = str(asset.get("description", "")).lower()
    combined = f"{title} {desc}"
    
    score = 0.0
    debug = {"rules": []}
    
    # ═══════════════════════════════════════════════════════════════
    # ✅ PLUS BODY
    # ═══════════════════════════════════════════════════════════════
    
    # 1. +0.25 pokud TITLE obsahuje anchor
    title_anchor_matches = sum(1 for anchor in scene_anchors if anchor in title)
    if title_anchor_matches > 0:
        score += 0.25
        debug["rules"].append(f"+0.25 title_anchors({title_anchor_matches})")
    
    # 2. +0.15 pokud DESCRIPTION obsahuje anchor
    desc_anchor_matches = sum(1 for anchor in scene_anchors if anchor in desc)
    if desc_anchor_matches > 0:
        score += 0.15
        debug["rules"].append(f"+0.15 desc_anchors({desc_anchor_matches})")
    
    # 3. +0.15 pokud obsahuje archivní formát
    archival_formats = ["engraving", "map", "manuscript", "letter", "archival", "photograph", 
                        "lithograph", "etching", "drawing", "document", "newsreel"]
    has_archival_format = any(fmt in combined for fmt in archival_formats)
    if has_archival_format:
        score += 0.15
        debug["rules"].append("+0.15 archival_format")
    
    # 4. +0.10 pokud délka videa je v rozumném rozsahu (10s-3min)
    duration = asset.get("duration_sec", 0)
    if 10 <= duration <= 180:  # 10s - 3min
        score += 0.10
        debug["rules"].append(f"+0.10 good_duration({duration}s)")
    
    # 5. +0.10 pokud typ odpovídá shot_type
    shot_types = shot_types or []
    type_match_bonus = 0.0
    
    if "maps_context" in shot_types and any(w in combined for w in ["map", "chart", "diagram"]):
        type_match_bonus = 0.10
        debug["rules"].append("+0.10 shot_type_match(maps)")
    elif "archival_documents" in shot_types and any(w in combined for w in ["document", "letter", "manuscript", "paper"]):
        type_match_bonus = 0.10
        debug["rules"].append("+0.10 shot_type_match(documents)")
    elif "civilian_life" in shot_types and any(w in combined for w in ["city", "street", "civilian", "daily life"]):
        type_match_bonus = 0.10
        debug["rules"].append("+0.10 shot_type_match(civilian)")
    elif "destruction_aftermath" in shot_types and any(w in combined for w in ["ruin", "destruction", "damage", "aftermath"]):
        type_match_bonus = 0.10
        debug["rules"].append("+0.10 shot_type_match(destruction)")
    
    score += type_match_bonus
    
    # ═══════════════════════════════════════════════════════════════
    # ❌ MÍNUS BODY
    # ═══════════════════════════════════════════════════════════════
    
    # 6. −0.30 pokud obsahuje compilation/montage/highlights/edit/HD/full documentary
    bad_patterns = [
        "montage", "compilation", "highlights", "highlight reel", "best of",
        "edit", "edited", "full documentary", "documentary film",
        "hd", "4k", "remaster", "colorized", "upscaled"
    ]
    has_bad_pattern = any(pattern in combined for pattern in bad_patterns)
    if has_bad_pattern:
        score -= 0.30
        debug["rules"].append("-0.30 bad_pattern(compilation/edit)")
    
    # 7. −0.15 pokud je video extrémně krátké (<5s) nebo dlouhé (>20min)
    if duration > 0:
        if duration < 5 or duration > 1200:  # <5s nebo >20min
            score -= 0.15
            debug["rules"].append(f"-0.15 extreme_duration({duration}s)")
    
    # 8. −0.20 pokud TITLE je generický
    generic_titles = [
        "historical footage", "old video", "archive footage", "vintage video",
        "old film", "historical film", "history", "documentary"
    ]
    # Pokud title je POUZE generický term (bez specifických anchors)
    if any(title == gen or title.startswith(gen + " ") for gen in generic_titles):
        if title_anchor_matches == 0:  # Žádné konkrétní anchory
            score -= 0.20
            debug["rules"].append("-0.20 generic_title")
    
    # ═══════════════════════════════════════════════════════════════
    # FINAL SCORE
    # ═══════════════════════════════════════════════════════════════
    
    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    
    debug["final_score"] = round(score, 3)
    debug["anchor_matches_title"] = title_anchor_matches
    debug["anchor_matches_desc"] = desc_anchor_matches
    debug["duration_sec"] = duration
    
    return score, debug


def _select_top_assets(
    candidates: List[Dict[str, Any]],
    scene: Dict[str, Any],
    max_assets: int,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Select top assets from candidates using NEW relevance scoring.
    
    ZMĚNA CHOVÁNÍ:
    - NIKDY nefailuje (vždy vrátí TOP 1, i když score < 0.45)
    - Fallback jen pokud žádné kandidáty
    
    Returns:
        List of top-ranked assets with scoring metadata attached.
    """
    scene_anchors = _extract_scene_anchors(scene)
    shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
    
    if verbose:
        print(f"🎯 Ranking {len(candidates)} candidates with {len(scene_anchors)} anchors: {scene_anchors[:5]}")
        print(f"   Shot types: {shot_types}")
    
    # Apply hard filters first
    filtered = []
    for asset in candidates:
        is_valid, reject_reason = _apply_hard_filters(asset, verbose=verbose)
        if is_valid:
            filtered.append(asset)
        elif verbose:
            print(f"  ❌ Filtered: {asset.get('title', '')[:60]} (reason: {reject_reason})")
    
    if not filtered:
        if verbose:
            print(f"  ⚠️  No candidates passed hard filters")
        return []
    
    # Rank remaining candidates with NEW scoring
    scored = []
    for asset in filtered:
        rank_score, debug = _rank_asset(asset, scene_anchors, shot_types=shot_types, verbose=verbose)
        asset["_rank_score"] = rank_score
        asset["_rank_debug"] = debug
        scored.append((rank_score, asset))
    
    # Sort by score descending
    scored.sort(reverse=True, key=lambda x: x[0])
    
    if verbose and scored:
        print(f"  🏆 Top 3 scores: {[round(s, 3) for s, _ in scored[:3]]}")
        for rank_score, asset in scored[:3]:
            print(f"     {rank_score:.3f} - {asset.get('title', '')[:60]}")
    
    # NEW BEHAVIOR: VŽDY vrať TOP 1 (i když score < 0.45)
    # Fallback se použije pouze pokud žádné kandidáty
    best_score = scored[0][0] if scored else 0.0
    selected_asset = scored[0][1] if scored else None
    
    # ═══════════════════════════════════════════════════════════════
    # TELEMETRIE (minimální - per scénu)
    # ═══════════════════════════════════════════════════════════════
    scene_id = scene.get("scene_id", "unknown")
    telemetry = {
        "scene_id": scene_id,
        "candidates_count": len(candidates),
        "filtered_count": len(filtered),
        "selected_asset_id": selected_asset.get("archive_item_id") if selected_asset else None,
        "selected_score": round(best_score, 3),
        "top3_scores": [round(s, 3) for s, _ in scored[:3]],
        "top3_titles": [a.get("title", "")[:60] for _, a in scored[:3]],
    }
    
    # Log telemetrie (grep-friendly JSON)
    import json
    print(f"AAR_TELEMETRY: {json.dumps(telemetry, ensure_ascii=False)}")
    
    if best_score < ASSET_RANKING_QUALITY_FLOOR:
        if verbose:
            print(f"  ⚠️  Best score {best_score:.3f} < quality floor {ASSET_RANKING_QUALITY_FLOOR:.3f}")
            print(f"  ✅  BUT: Using TOP 1 anyway (NO FAIL!)")
    
    # ALWAYS return top N (even if score is low)
    # Fallback only if NO candidates at all
    return [asset for _, asset in scored[:max_assets]]



class ArchiveAssetResolver:
    """
    Resolver pro archive.org assets.
    - Throttling (1-2 requests/s)
    - Cache výsledků vyhledávání
    - Fail-safe s atmosphere_transition fallback
    """
    
    def __init__(
        self,
        cache_dir: str,
        throttle_delay_sec: float = 0.2,
        verbose: bool = False,
        enable_multi_source: bool = True,
        preview_mode: bool = False,
    ):
        """
        Args:
            cache_dir: Složka pro cache JSON souborů
            throttle_delay_sec: Delay mezi API calls (default 0.5s = 2 req/s)
            enable_multi_source: Enable multi-source search (Archive.org + Wikimedia + Europeana)
        """
        self.cache_dir = cache_dir
        self.throttle_delay_sec = throttle_delay_sec
        self.last_request_time = 0.0
        self.verbose = bool(verbose)
        enable_multi_source_input = bool(enable_multi_source)
        self.enable_multi_source = enable_multi_source_input and MULTI_SOURCE_AVAILABLE
        self.preview_mode = bool(preview_mode)
        # Optional context (scene_id/episode_id) for structured logs.
        self._log_context: Dict[str, Any] = {}
        # Persist last N query attempt logs per scene for diagnostics (UI / script_state.error.details)
        self._query_attempts_by_scene: Dict[str, List[Dict[str, Any]]] = {}

        # Query audit counters (A)
        self.cache_hit_count = 0
        self.network_error_count = 0
        
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Preview mode: be aggressive about speed. Never wait minutes just to say "0 results".
        try:
            default_timeout = 4.0 if self.preview_mode else 12.0
            self.request_timeout_sec = float(os.getenv("AAR_PREVIEW_REQUEST_TIMEOUT_S" if self.preview_mode else "AAR_REQUEST_TIMEOUT_S", str(default_timeout)))
        except Exception:
            self.request_timeout_sec = 4.0 if self.preview_mode else 12.0
        try:
            # NOTE: In this codebase MAX_RETRIES == number of attempts (loop is range(MAX_RETRIES)).
            # Must be >= 1, otherwise we do 0 network calls and always get 0 results.
            self.max_retries = int(os.getenv("AAR_PREVIEW_MAX_RETRIES" if self.preview_mode else "AAR_MAX_RETRIES", "1" if self.preview_mode else "2"))
        except Exception:
            self.max_retries = 1 if self.preview_mode else 2
        try:
            self.enable_relaxed_pass = str(os.getenv("AAR_PREVIEW_ENABLE_RELAXED_PASS" if self.preview_mode else "AAR_ENABLE_RELAXED_PASS", "0" if self.preview_mode else "1")).strip().lower() in ("1", "true", "yes")
        except Exception:
            self.enable_relaxed_pass = (not self.preview_mode)

        # Initialize multi-source video providers
        self.video_sources = []
        if self.enable_multi_source:
            # Get Europeana API key from environment if available
            europeana_key = os.getenv("EUROPEANA_API_KEY")
            # Optional stock sources (only if API keys exist)
            pexels_key = os.getenv("PEXELS_API_KEY")
            pixabay_key = os.getenv("PIXABAY_API_KEY")

            # Multi-source strategy: do NOT call all sources every time (farm efficiency).
            # Modes:
            # - "all": query every provider for every query (slowest, maximum recall)
            # - "cascade": query providers in priority order and stop early once we have enough
            #
            # IMPORTANT:
            # - In interactive preview mode, default to "cascade" for speed.
            # - In non-preview mode (pipeline), keep "all" as default for recall.
            try:
                if self.preview_mode:
                    self.multi_source_mode = str(os.getenv("AAR_PREVIEW_MULTI_SOURCE_MODE", os.getenv("AAR_MULTI_SOURCE_MODE", "cascade"))).strip().lower()
                else:
                    self.multi_source_mode = str(os.getenv("AAR_MULTI_SOURCE_MODE", "all")).strip().lower()
            except Exception:
                self.multi_source_mode = "cascade" if self.preview_mode else "all"
            try:
                # Default: if Europeana is configured, allow up to 3 providers (Archive + Wikimedia + Europeana)
                # so we are not stuck with a "2 provider" ceiling that never reaches Europeana in cascade mode.
                default_max_providers = "3" if str(europeana_key or "").strip() else "2"
                if self.preview_mode:
                    # Preview: keep it tight unless explicitly overridden.
                    self.multi_source_max_providers_per_query = int(
                        os.getenv("AAR_PREVIEW_MULTI_SOURCE_MAX_PROVIDERS_PER_QUERY", os.getenv("AAR_MULTI_SOURCE_MAX_PROVIDERS_PER_QUERY", "2"))
                    )
                else:
                    self.multi_source_max_providers_per_query = int(os.getenv("AAR_MULTI_SOURCE_MAX_PROVIDERS_PER_QUERY", default_max_providers))
            except Exception:
                self.multi_source_max_providers_per_query = 2
            try:
                if self.preview_mode:
                    self.multi_source_min_results_per_query = int(
                        os.getenv("AAR_PREVIEW_MULTI_SOURCE_MIN_RESULTS_PER_QUERY", os.getenv("AAR_MULTI_SOURCE_MIN_RESULTS_PER_QUERY", "2"))
                    )
                else:
                    self.multi_source_min_results_per_query = int(os.getenv("AAR_MULTI_SOURCE_MIN_RESULTS_PER_QUERY", "4"))
            except Exception:
                self.multi_source_min_results_per_query = 4
            try:
                self.source_cooldown_sec = int(os.getenv("AAR_SOURCE_COOLDOWN_S", "300"))
            except Exception:
                self.source_cooldown_sec = 300
            # Circuit breaker storage: source_name -> cooldown_until_ts
            self._source_cooldowns: Dict[str, float] = {}

            # NO FALLBACK POLICY (per user): do NOT relax license constraints implicitly.
            # Unknown license fallback must be explicitly enabled by environment variable.
            try:
                allow_unknown_license = str(
                    os.getenv("AAR_PREVIEW_ALLOW_UNKNOWN_LICENSE_FALLBACK" if self.preview_mode else "AAR_ALLOW_UNKNOWN_LICENSE_FALLBACK",
                              "0")
                ).strip().lower() in ("1", "true", "yes")
            except Exception:
                allow_unknown_license = False

            # Stock sources are opt-in:
            # - Enabled only when API keys exist (so accidental usage is unlikely).
            enable_stock = bool((pexels_key or "").strip() or (pixabay_key or "").strip())
            try:
                enable_stock = str(os.getenv("AAR_ENABLE_STOCK_SOURCES", "1" if enable_stock else "0")).strip().lower() in ("1", "true", "yes")
            except Exception:
                pass

            # Stock tuning
            try:
                stock_max_height = int(os.getenv("AAR_STOCK_MAX_HEIGHT", "720"))
            except Exception:
                stock_max_height = 720
            pixabay_quality = str(os.getenv("AAR_PIXABAY_QUALITY", "medium")).strip().lower()

            self.video_sources = create_multi_source_searcher(
                archive_org=True,
                wikimedia=True,
                europeana=bool(europeana_key),
                europeana_api_key=europeana_key,
                pexels=bool(enable_stock and (pexels_key or "").strip()),
                pexels_api_key=(pexels_key or "").strip() if enable_stock else None,
                pixabay=bool(enable_stock and (pixabay_key or "").strip()),
                pixabay_api_key=(pixabay_key or "").strip() if enable_stock else None,
                throttle_delay_sec=throttle_delay_sec,
                verbose=verbose,
                timeout_sec=self.request_timeout_sec,
                allow_unknown_archive_org_license_fallback=allow_unknown_license,
                stock_max_height=stock_max_height,
                pixabay_preferred_quality=pixabay_quality,
            )
            if verbose:
                source_names = [s.source_name for s in self.video_sources]
                print(f"✅ AAR: Multi-source enabled with {len(self.video_sources)} providers: {source_names}")
        else:
            if verbose:
                print("ℹ️  AAR: Multi-source disabled, using legacy archive.org only")

        # #region agent log
        try:
            import time as _time, json as _json, os as _os
            has_europeana_key = bool(str(_os.getenv("EUROPEANA_API_KEY") or "").strip())
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H2",
                    "location": "backend/archive_asset_resolver.py:ArchiveAssetResolver.__init__",
                    "message": "Resolver init (multi-source flags + providers)",
                    "data": {
                        "cwd": _os.getcwd(),
                        "preview_mode": bool(self.preview_mode),
                        "enable_multi_source_input": enable_multi_source_input,
                        "MULTI_SOURCE_AVAILABLE": bool(MULTI_SOURCE_AVAILABLE),
                        "enable_multi_source_final": bool(self.enable_multi_source),
                        "video_sources_count": len(self.video_sources) if isinstance(self.video_sources, list) else None,
                        "video_sources_names": [s.source_name for s in self.video_sources] if isinstance(self.video_sources, list) else None,
                        "multi_source_mode": str(getattr(self, "multi_source_mode", "") or ""),
                        "multi_source_max_providers_per_query": int(getattr(self, "multi_source_max_providers_per_query", 0) or 0),
                        "multi_source_min_results_per_query": int(getattr(self, "multi_source_min_results_per_query", 0) or 0),
                        "has_europeana_key": has_europeana_key,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion

    def _log_query_attempt(self, payload: Dict[str, Any]) -> None:
        """
        A) MUST-HAVE structured log line per query attempt (PASS A/B).
        Always printed (grep-friendly) to support fail-fast debugging.
        """
        try:
            merged = {}
            if isinstance(self._log_context, dict) and self._log_context:
                merged.update(self._log_context)
            merged.update(payload or {})
            print("ASSET_QUERY_ATTEMPT " + json.dumps(merged, ensure_ascii=False))
            # Keep a bounded in-memory audit trail for post-mortem diagnostics
            try:
                sid = merged.get("scene_id")
                if sid:
                    sid = str(sid)
                    buf = self._query_attempts_by_scene.setdefault(sid, [])
                    buf.append(merged)
                    # keep only last 200 entries per scene to avoid memory blow-up
                    if len(buf) > 200:
                        del buf[: max(0, len(buf) - 200)]
            except Exception:
                pass
        except Exception:
            # Fallback if json serialization fails for any reason
            print(f"ASSET_QUERY_ATTEMPT {payload}")

    def _append_negative_terms(self, query_text: str) -> str:
        q = str(query_text or "").strip()
        if not q:
            return q
        # Avoid duplicates
        existing = q.lower()
        extras = []
        for term in NEGATIVE_SEARCH_TERMS:
            tok = f"-{term}"
            if tok not in existing:
                extras.append(tok)
        if extras:
            q = f"{q} {' '.join(extras)}"
        return q
    
    def _throttle(self) -> None:
        """Zajišťuje delay mezi requesty"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.throttle_delay_sec:
            time.sleep(self.throttle_delay_sec - elapsed)
        self.last_request_time = time.time()
    
    def _cache_key(self, query: str, pass_name: str) -> str:
        """B: Generuje cache key z query + pass + version"""
        q = f"{pass_name}|{query}"
        query_hash = hashlib.md5(q.encode("utf-8")).hexdigest()[:16]
        return f"archive_search_{AAR_CACHE_VERSION}_{pass_name}_{query_hash}.json"
    
    def _get_cached_results(self, query: str, pass_name: str) -> Optional[Dict[str, Any]]:
        """
        A: Cache = raw search results (standardized items) + response metadata.
        Topic gates se aplikují až po načtení (při výpočtu after_gates).
        """
        cache_file = os.path.join(self.cache_dir, self._cache_key(query, pass_name))
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.cache_hit_count += 1
                    return {
                        "query_text": data.get("query") or query,
                        "pass": data.get("pass") or pass_name,
                        "final_search_url": data.get("final_search_url"),
                        "http_status": data.get("http_status"),
                        "num_found": data.get("num_found"),
                        "rows_requested": data.get("rows_requested"),
                        "docs_returned": data.get("docs_returned"),
                        "results": data.get("results", []) or [],
                        "cached_at": data.get("cached_at"),
                    }
            except Exception as e:
                print(f"⚠️  AAR: Cache read error for {query[:50]}: {e}")
        return None
    
    def _save_to_cache(self, query: str, pass_name: str, payload: Dict[str, Any]) -> None:
        """Uloží raw search results + metadata do cache"""
        cache_file = os.path.join(self.cache_dir, self._cache_key(query, pass_name))
        try:
            cache_data = {
                "query": query,
                "pass": pass_name,
                "cached_at": _now_iso(),
                "final_search_url": payload.get("final_search_url"),
                "http_status": payload.get("http_status"),
                "num_found": payload.get("num_found"),
                "rows_requested": payload.get("rows_requested"),
                "docs_returned": payload.get("docs_returned"),
                "results": payload.get("results", []) or [],
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  AAR: Cache write error for {query[:50]}: {e}")
    
    def _apply_topic_gates(self, docs: List[Dict[str, Any]], query_context: str = "") -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        1-4) Refined topic gates with 3 levels: HARD / CONDITIONAL / SOFT
        
        Returns:
            (filtered_docs, stats_dict)
            stats_dict = {
                "hard_reject": count,
                "conditional_reject": count,
                "must_hit_fail": count,
                "soft_penalize": count,
                "approved": count
            }
        """
        approved = []
        stats = {
            "hard_reject": 0,
            "conditional_reject": 0,
            "must_hit_fail": 0,
            "soft_penalize": 0,
            "approved": 0
        }
        
        for doc in docs:
            identifier = doc.get("archive_item_id") or doc.get("identifier") or ""
            if not identifier:
                continue
            
            title = str(doc.get("title", "")).lower()
            desc = str(doc.get("description", "")).lower()
            coll = str(doc.get("collection", "")).lower()
            combined = f"{title} {desc} {coll}"
            
            # 1) HARD REJECT - animated/kids/talks
            reject_reason = None
            for pattern in HARD_REJECT_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    matched = re.search(pattern, combined, re.IGNORECASE)
                    reject_reason = f"HARD:{matched.group(0) if matched else pattern}"
                    break
            
            if reject_reason:
                stats["hard_reject"] += 1
                if self.verbose:
                    print(f"🚫 AAR: HARD REJECT: {doc.get('title', '')[:60]} (reason={reject_reason})")
                continue
            
            # 2) Check historical must-hit (video is stricter; stills/texts allow physical artefacts)
            has_history_hit = any(token in combined for token in HISTORY_WHITELIST_TOKENS)
            if not has_history_hit:
                # For images/texts we accept physical artefact anchors even when "WWII tokens" are absent.
                # This supports non-WWII episodes and map/document/engraving fallback without letting in random junk.
                mt = str(doc.get("mediatype") or "").strip().lower()
                if mt in {"image", "texts"}:
                    physical_tokens = (
                        "map",
                        "maps",
                        "atlas",
                        "chart",
                        "diagram",
                        "photograph",
                        "photographs",
                        "photo",
                        "portrait",
                        "engraving",
                        "engravings",
                        "lithograph",
                        "etching",
                        "document",
                        "documents",
                        "letter",
                        "letters",
                        "manuscript",
                        "manuscripts",
                        "archive",
                        "archival",
                    )
                    if any(tok in combined for tok in physical_tokens) or re.search(r"\b(18|19|20)\d{2}\b", combined):
                        has_history_hit = True

            
            # 1) CONDITIONAL REJECT - season/episode/series
            # These are OK if they have historical hits, otherwise reject
            conditional_match = None
            for pattern in CONDITIONAL_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    matched = re.search(pattern, combined, re.IGNORECASE)
                    conditional_match = matched.group(0) if matched else pattern
                    break
            
            if conditional_match:
                if has_history_hit:
                    # OK - it's a documentary series about WWII (e.g., Nazi Megastructures Season 7)
                    if self.verbose:
                        print(
                            f"✅ AAR: CONDITIONAL OK (has history): {doc.get('title', '')[:60]} "
                            f"(matched={conditional_match})"
                        )
                    doc["_quality_penalty"] = 0.8  # Small penalty but allowed
                else:
                    # Reject - it's a TV series but not historical
                    stats["conditional_reject"] += 1
                    if self.verbose:
                        print(
                            f"🚫 AAR: CONDITIONAL REJECT (no history): {doc.get('title', '')[:60]} "
                            f"(matched={conditional_match})"
                        )
                    continue
            
            # 2) MUST-HIT check for non-conditional items
            if not has_history_hit:
                stats["must_hit_fail"] += 1
                if self.verbose:
                    print(f"⚠️  AAR: MUST-HIT FAIL: {doc.get('title', '')[:60]} (no WWII/historical tokens)")
                # Still reject if no history hits and not already conditionally approved
                continue
            
            # 1) SOFT PENALIZE - education/classroom etc
            soft_match = None
            for pattern in SOFT_PENALIZE_PATTERNS:
                if re.search(pattern, combined, re.IGNORECASE):
                    matched = re.search(pattern, combined, re.IGNORECASE)
                    soft_match = matched.group(0) if matched else pattern
                    break
            
            if soft_match:
                stats["soft_penalize"] += 1
                if self.verbose:
                    print(f"⚡ AAR: SOFT PENALIZE: {doc.get('title', '')[:60]} (matched={soft_match})")
                doc["_quality_penalty"] = 0.7  # Heavier penalty
            
            # Passed all gates!
            stats["approved"] += 1
            approved.append(doc)
        
        # 4) Cache evidence logging (verbose only; query attempt logger always has gate_stats)
        if self.verbose:
            print(f"📊 AAR: Topic gates stats for '{query_context[:40]}': {stats}")
        
        return approved, stats
    
    def search_multi_source(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        NEW: Multi-source video search (Archive.org + Wikimedia + Europeana).
        
        Merges results from all enabled sources, deduplicates by title similarity,
        and returns standardized items sorted by:
        1. License priority (PD/CC0 > CC-BY)
        2. Source priority (Archive.org > Wikimedia > Europeana)
        3. Popularity (downloads for Archive.org)
        
        Returns:
            List of standardized items (same format as search_archive_org for compatibility)
        """
        # #region agent log
        try:
            import time as _time, json as _json
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session", "runId": "aar-v1", "hypothesisId": "API-3",
                    "location": "backend/archive_asset_resolver.py:search_multi_source",
                    "message": "search_multi_source called",
                    "data": {
                        "query": query[:120],
                        "enable_multi_source": self.enable_multi_source,
                        "video_sources_count": len(self.video_sources) if isinstance(self.video_sources, list) else None,
                        "video_sources_names": [s.source_name for s in self.video_sources] if isinstance(self.video_sources, list) else None,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        if not self.enable_multi_source or not self.video_sources:
            # Fallback to legacy single-source
            return self.search_archive_org(query, max_results, mediatype_filter=ARCHIVE_VIDEO_MEDIATYPE_FILTER, media_label="video")
        
        def _in_cooldown(name: str) -> bool:
            try:
                until = float(self._source_cooldowns.get(name, 0.0) or 0.0)
                return time.time() < until
            except Exception:
                return False

        def _mark_cooldown(name: str, reason: str = "") -> None:
            try:
                self._source_cooldowns[name] = time.time() + float(self.source_cooldown_sec or 300)
                if self.verbose:
                    print(f"⏸️  AAR: Cooling down {name} for {int(self.source_cooldown_sec)}s ({reason})")
            except Exception:
                pass

        all_results: List[Dict[str, Any]] = []

        mode = str(getattr(self, "multi_source_mode", "cascade") or "cascade").strip().lower()
        max_providers = int(getattr(self, "multi_source_max_providers_per_query", 2) or 2)
        min_results = int(getattr(self, "multi_source_min_results_per_query", 4) or 4)

        # Fast path: "all" mode keeps legacy behavior
        if mode == "all":
            for source in self.video_sources:
                # #region agent log
                try:
                    import time as _time
                    with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({
                            "sessionId": "debug-session", "runId": "aar-all-mode", "hypothesisId": "ALL",
                            "location": "backend/archive_asset_resolver.py:search_multi_source:all_mode_loop",
                            "message": "Trying source in all mode",
                            "data": {
                                "query": query[:80],
                                "source_name": source.source_name,
                                "in_cooldown": _in_cooldown(source.source_name),
                            },
                            "timestamp": int(_time.time() * 1000),
                        }) + "\n")
                except Exception:
                    pass
                # #endregion
                
                try:
                    if _in_cooldown(source.source_name):
                        continue
                    source_results = source.search(query, max_results=max_results)
                    if self.verbose:
                        print(f"📡 AAR: {source.source_name} returned {len(source_results)} results for '{query[:40]}'")
                    
                    # #region agent log
                    try:
                        import time as _time
                        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                            _f.write(_json.dumps({
                                "sessionId": "debug-session", "runId": "aar-all-mode", "hypothesisId": "ALL",
                                "location": "backend/archive_asset_resolver.py:search_multi_source:all_mode_result",
                                "message": "Source returned results",
                                "data": {
                                    "query": query[:80],
                                    "source_name": source.source_name,
                                    "results_count": len(source_results),
                                },
                                "timestamp": int(_time.time() * 1000),
                            }) + "\n")
                    except Exception:
                        pass
                    # #endregion
                    
                    all_results.extend(source_results)
                    # Circuit breaker on HTTP outages (429/5xx)
                    st = getattr(source, "last_http_status", None)
                    if isinstance(st, int) and (st == 429 or 500 <= st <= 599):
                        _mark_cooldown(source.source_name, reason=f"http:{st}")
                except Exception as e:
                    # #region agent log
                    try:
                        import time as _time, traceback
                        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                            _f.write(_json.dumps({
                                "sessionId": "debug-session", "runId": "aar-all-mode", "hypothesisId": "ALL",
                                "location": "backend/archive_asset_resolver.py:search_multi_source:all_mode_exception",
                                "message": "Source search failed",
                                "data": {
                                    "query": query[:80],
                                    "source_name": source.source_name,
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                    "traceback": traceback.format_exc()[:300],
                                },
                                "timestamp": int(_time.time() * 1000),
                            }) + "\n")
                    except Exception:
                        pass
                    # #endregion
                    
                    if self.verbose:
                        print(f"⚠️  AAR: {source.source_name} search failed: {e}")
            if not all_results:
                return []
            unique_results = self._deduplicate_by_title(all_results)
            scored = []
            for item in unique_results:
                score = self._score_multi_source_item(item)
                scored.append((score, item))
            scored.sort(reverse=True, key=lambda x: x[0])
            legacy_format = []
            for score, item in scored[:max_results]:
                legacy_format.append(self._convert_to_aar_format(item))
            return legacy_format

        # Default: "cascade" (priority + early exit)
        providers_tried = 0
        for source in self.video_sources:
            if providers_tried >= max_providers:
                break
            if _in_cooldown(source.source_name):
                continue
            try:
                source_results = source.search(query, max_results=max_results)
                # #region agent log
                try:
                    import time as _time, json as _json
                    with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "H4",
                            "location": "backend/archive_asset_resolver.py:search_multi_source(cascade)",
                            "message": "Provider attempt (cascade)",
                            "data": {
                                "provider": str(getattr(source, "source_name", "") or ""),
                                "providers_tried_before": int(providers_tried),
                                "results_count": int(len(source_results) if isinstance(source_results, list) else 0),
                                "all_results_len_after": int(len(all_results) + (len(source_results) if isinstance(source_results, list) else 0)),
                                "min_results": int(min_results),
                                "max_results": int(max_results),
                                "max_providers": int(max_providers),
                            },
                            "timestamp": int(_time.time() * 1000),
                        }) + "\n")
                except Exception:
                    pass
                # #endregion
                if self.verbose:
                    print(f"📡 AAR(cascade): {source.source_name} returned {len(source_results)} results for '{query[:40]}'")
                all_results.extend(source_results)
                providers_tried += 1
                st = getattr(source, "last_http_status", None)
                if isinstance(st, int) and (st == 429 or 500 <= st <= 599):
                    _mark_cooldown(source.source_name, reason=f"http:{st}")
                # Early exit once we have enough candidates
                if len(all_results) >= max(min_results, max_results):
                    break
                if len(all_results) >= min_results:
                    break
            except Exception as e:
                providers_tried += 1
                _mark_cooldown(source.source_name, reason=f"exception:{type(e).__name__}")
                if self.verbose:
                    print(f"⚠️  AAR(cascade): {source.source_name} search failed: {e}")
        # #region agent log
        try:
            import time as _time, json as _json
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H4",
                    "location": "backend/archive_asset_resolver.py:search_multi_source(cascade)",
                    "message": "Cascade summary",
                    "data": {
                        "providers_tried": int(providers_tried),
                        "all_results_len": int(len(all_results)),
                        "min_results": int(min_results),
                        "max_results": int(max_results),
                        "max_providers": int(max_providers),
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion

        # If cascade found nothing, expand to remaining providers (rare, but avoids 0-results episodes)
        if not all_results:
            for source in self.video_sources:
                if _in_cooldown(source.source_name):
                    continue
                try:
                    source_results = source.search(query, max_results=max_results)
                    if self.verbose:
                        print(f"📡 AAR(expand): {source.source_name} returned {len(source_results)} results for '{query[:40]}'")
                    all_results.extend(source_results)
                    st = getattr(source, "last_http_status", None)
                    if isinstance(st, int) and (st == 429 or 500 <= st <= 599):
                        _mark_cooldown(source.source_name, reason=f"http:{st}")
                    if all_results:
                        break
                except Exception as e:
                    _mark_cooldown(source.source_name, reason=f"exception:{type(e).__name__}")
                    continue
        
        if not all_results:
            return []
        
        # Deduplicate by title similarity (same video from multiple sources)
        unique_results = self._deduplicate_by_title(all_results)
        
        # Score and sort
        scored = []
        for item in unique_results:
            score = self._score_multi_source_item(item)
            scored.append((score, item))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        
        # Convert to AAR legacy format for compatibility
        legacy_format = []
        for score, item in scored[:max_results]:
            legacy_format.append(self._convert_to_aar_format(item))
        
        return legacy_format

    # ------------------------------------------------------------------------
    # Wikimedia Commons IMAGE search (to avoid single-point-of-failure on Archive)
    # ------------------------------------------------------------------------
    def _normalize_wikimedia_license(self, license_short: str) -> str:
        """
        Normalize Wikimedia license string to our internal buckets.
        Must stay aligned with video_sources.YOUTUBE_SAFE_LICENSES semantics.
        """
        s = str(license_short or "").strip()
        if not s:
            return "unknown"
        l = s.lower()
        if "public domain" in l or l == "pd" or l.startswith("pd-"):
            return "public_domain"
        if "cc0" in l or "cc-zero" in l:
            return "cc0"
        if "cc-by-sa" in l or "cc by-sa" in l:
            return "cc-by-sa"
        if "cc-by" in l or "cc by" in l:
            return "cc-by"
        return "unknown"

    def search_wikimedia_images(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search Wikimedia Commons for still images (maps, photos, paintings, scans).
        Returns AAR legacy format items with archive_item_id prefixed as 'wikimedia:'.
        """
        q = str(query or "").strip()
        if not q:
            return []

        api_url = "https://commons.wikimedia.org/w/api.php"
        # NOTE:
        # We keep CirrusSearch query broad (filemime:image) and then HARD-FILTER by actual
        # mime/ext from imageinfo. This avoids the "0 results" failure mode when Cirrus
        # does not honor full mime OR-groups reliably.
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filemime:image {q}",
            "gsrlimit": min(max_results, 50),
            "gsrnamespace": 6,  # File: namespace
            "prop": "imageinfo|info",
            "iiprop": "url|size|mime|mediatype|extmetadata",
            "iiurlwidth": 640,
        }
        headers = {
            # Wikimedia requires a descriptive UA or it can rate-limit/deny.
            "User-Agent": "PodcastVideoBot/1.0 (Documentary visual research; contact: local)",
        }

        try:
            self._throttle()
            resp = requests.get(api_url, params=params, headers=headers, timeout=float(self.request_timeout_sec or 12.0), verify=False)
            resp.raise_for_status()
            data = resp.json() or {}
            pages = (data.get("query") or {}).get("pages") or {}

            out: List[Dict[str, Any]] = []
            for _pid, page in pages.items():
                if not isinstance(page, dict):
                    continue
                title = str(page.get("title") or "").strip()
                if not title.startswith("File:"):
                    continue
                imageinfo = page.get("imageinfo")
                if not isinstance(imageinfo, list) or not imageinfo:
                    continue
                info = imageinfo[0] if isinstance(imageinfo[0], dict) else None
                if not info:
                    continue

                # License gate (NO implicit relaxation)
                extmeta = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
                license_raw = ""
                if isinstance(extmeta, dict):
                    license_raw = (extmeta.get("LicenseShortName") or {}).get("value") or (extmeta.get("License") or {}).get("value") or ""
                license_norm = self._normalize_wikimedia_license(license_raw)
                if "YOUTUBE_SAFE_LICENSES" in globals():
                    if license_norm not in YOUTUBE_SAFE_LICENSES:
                        continue
                else:
                    # Conservative: only allow explicit PD/CC variants we recognize
                    if license_norm not in ("public_domain", "cc0", "cc-by", "cc-by-sa"):
                        continue

                # Extract URLs
                file_url = str(info.get("url") or "").strip()
                thumb_url = str(info.get("thumburl") or "").strip()
                if not file_url:
                    continue

                # ═══════════════════════════════════════════════════════════════════════════
                # HARD FILTER: Only allow real still-image formats we can render (jpg/png/webp/gif)
                # and reject DjVu/PDF/TIFF/SVG/etc.
                # ═══════════════════════════════════════════════════════════════════════════
                mime_type = str(info.get("mime") or "").lower()
                file_ext = file_url.lower().split(".")[-1] if "." in file_url else ""

                ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
                ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

                BANNED_EXTENSIONS = {"djvu", "pdf", "tiff", "tif", "svg", "xcf", "psd", "ai", "eps", "bmp"}
                BANNED_MIMES = {"image/vnd.djvu", "application/pdf", "image/tiff", "image/svg+xml", "image/x-xcf"}

                if file_ext in BANNED_EXTENSIONS:
                    if self.verbose:
                        print(f"⚠️  AAR: Rejecting Wikimedia file (banned ext: {file_ext}): {title[:80]}")
                    continue
                if mime_type in BANNED_MIMES:
                    if self.verbose:
                        print(f"⚠️  AAR: Rejecting Wikimedia file (banned mime: {mime_type}): {title[:80]}")
                    continue

                # Allowlist (must pass)
                if mime_type:
                    if mime_type not in ALLOWED_MIMES:
                        if self.verbose:
                            print(f"⚠️  AAR: Rejecting Wikimedia file (unsupported mime: {mime_type}): {title[:80]}")
                        continue
                else:
                    if file_ext and file_ext not in ALLOWED_EXTENSIONS:
                        if self.verbose:
                            print(f"⚠️  AAR: Rejecting Wikimedia file (unsupported ext: {file_ext}): {title[:80]}")
                        continue

                file_id = title.replace("File:", "").replace(" ", "_")
                desc = ""
                if isinstance(extmeta, dict):
                    desc = str((extmeta.get("ImageDescription") or {}).get("value") or "")[:1200]

                out.append(
                    {
                        "archive_item_id": f"wikimedia:{file_id}",
                        "title": title[:240],
                        "description": desc,
                        "collection": "wikimedia",
                        "subject": "",
                        "mediatype": "image",
                        "asset_url": file_url,  # direct media URL
                        "downloads": 0,
                        "thumbnail_url": thumb_url or file_url,
                        "_license": license_norm,
                        "_license_raw": str(license_raw)[:200],
                        "_source": "wikimedia",
                    }
                )

            return out[:max_results]
        except Exception as e:
            if self.verbose:
                print(f"⚠️  AAR: Wikimedia image search failed: {e}")
            return []

    def search_images_multi_source(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Multi-source IMAGE search.
        Today: Archive.org (images) + Wikimedia Commons (images).
        """
        results: List[Dict[str, Any]] = []

        # Archive.org images (legacy)
        try:
            r = self.search_archive_org(
                query,
                max_results=max_results,
                mediatype_filter=ARCHIVE_IMAGE_MEDIATYPE_FILTER,
                media_label="image",
            )
            for it in r:
                if isinstance(it, dict):
                    it.setdefault("mediatype", "image")
                    it.setdefault("_source", "archive_org")
                    if not it.get("thumbnail_url"):
                        aid = str(it.get("archive_item_id") or "").replace("archive_org:", "")
                        if aid:
                            it["thumbnail_url"] = f"https://archive.org/services/img/{aid}"
            results.extend(r)
        except Exception:
            pass

        # Wikimedia images (fast + reliable)
        try:
            results.extend(self.search_wikimedia_images(query, max_results=max_results))
        except Exception:
            pass

        # Dedupe by archive_item_id
        seen: set = set()
        uniq: List[Dict[str, Any]] = []
        for it in results:
            if not isinstance(it, dict):
                continue
            aid = str(it.get("archive_item_id") or "").strip()
            if not aid or aid in seen:
                continue
            seen.add(aid)
            uniq.append(it)
        return uniq[:max_results]
    
    def _deduplicate_by_title(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplikuje výsledky podle title similarity (stejné video z více zdrojů).
        Preferuje zdroj s vyšší prioritou (Archive.org > Wikimedia > Europeana).
        """
        SOURCE_PRIORITY = {"archive_org": 3, "wikimedia": 2, "europeana": 1}
        
        unique = []
        seen_titles_normalized = set()
        
        # Sort by source priority first
        results_sorted = sorted(results, key=lambda x: SOURCE_PRIORITY.get(x.get("source", ""), 0), reverse=True)
        
        for item in results_sorted:
            title = item.get("title", "")
            title_normalized = re.sub(r'[^a-z0-9]', '', title.lower())[:60]
            
            if title_normalized and title_normalized not in seen_titles_normalized:
                seen_titles_normalized.add(title_normalized)
                unique.append(item)
        
        return unique
    
    def _score_multi_source_item(self, item: Dict[str, Any]) -> float:
        """
        Score multi-source item for sorting.
        """
        score = 0.0
        
        # 1. License priority (PD/CC0 > CC-BY)
        license_norm = item.get("license", "unknown")
        score += LICENSE_PRIORITY.get(license_norm, 0) * 2.0
        
        # 2. Source priority
        source = item.get("source", "")
        if source == "archive_org":
            score += 5.0
        elif source == "wikimedia":
            score += 3.0
        elif source == "europeana":
            score += 2.0
        
        # 3. Popularity (only Archive.org has downloads)
        downloads = item.get("downloads", 0) or 0
        if downloads > 0:
            score += math.log(downloads) * 0.1
        
        return score
    
    def _convert_to_aar_format(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Konvertuje multi-source item na AAR legacy format pro kompatibilitu.
        """
        return {
            "archive_item_id": f"{item['source']}:{item['item_id']}",  # Prefix with source
            "title": item["title"],
            "description": item["description"],
            "collection": item.get("source", ""),  # Use source as collection
            "subject": "",
            "mediatype": "video",
            "asset_url": item["url"],
            "downloads": item.get("downloads", 0) or 0,
            # IMPORTANT: keep thumbnail_url so Visual Assistant + topic validation can use Vision
            "thumbnail_url": item.get("thumbnail_url"),
            "_license": item.get("license", "unknown"),
            "_license_raw": item.get("license_raw", ""),
            "_attribution": item.get("attribution"),
            "_source": item.get("source", "unknown"),
        }
    
    def search_archive_org(
        self,
        query: str,
        max_results: int = 10,
        mediatype_filter: str = ARCHIVE_MEDIATYPE_FILTER,
        media_label: str = "video",
    ) -> List[Dict[str, Any]]:
        """
        A+B+E: Vyhledá archive.org pomocí 2-pass search (strict → relaxed),
        s negativními termy a audit logem per query pokus.
        
        - PASS A (A_strict): mediatype filter, rows 25–50, bez collection.
        - PASS B (B_relaxed): jen query + mediatype, rows 50–100, bez dalších filtrů.
        
        Topic gates se aplikují vždy (i na cached data).
        
        Args:
            query: Search query string
            max_results: Maximální počet výsledků (po gates) které vrátíme volajícímu
            mediatype_filter: Archive.org mediatype filter (video vs image)
            media_label: Cache/audit label (e.g. "video"|"image")
        
        Returns:
            List of archive.org items s metadata (už po topic gates!)
        """
        query_text = str(query or "").strip()
        if not query_text:
            return []

        base_url = "https://archive.org/advancedsearch.php"
        # Must be >= 1 (see __init__ note)
        MAX_RETRIES = max(1, int(self.max_retries or 1))
        REQUEST_TIMEOUT = float(self.request_timeout_sec or 12.0)  # seconds

        # E) add negative terms into free-text query (not a hard gate)
        query_text_final = self._append_negative_terms(query_text)

        media_label = str(media_label or "video").strip().lower()
        passes = [(f"A_strict_{media_label}", max(25, min(SEARCH_ROWS_STRICT, 100)))]
        if self.enable_relaxed_pass:
            passes.append((f"B_relaxed_{media_label}", max(50, min(SEARCH_ROWS_RELAXED, 150))))

        for pass_name, rows_default in passes:
            rows_requested = int(max(rows_default, max_results))

            # Build advancedsearch q (no collection filter)
            mt = str(mediatype_filter or ARCHIVE_MEDIATYPE_FILTER).strip()
            q_expr = f"({query_text_final}) AND mediatype:({mt})"
            params = {
                "q": q_expr,
                "fl[]": [
                    "identifier",
                    "title",
                    "description",
                    "collection",
                    "subject",
                    "mediatype",
                    "downloads",
                    "date",
                    "creator",
                ],
                "rows": rows_requested,
                "output": "json",
                "sort[]": "downloads desc",
            }

            # Prepared URL for audit logs (A)
            try:
                final_search_url = requests.Request("GET", base_url, params=params).prepare().url
            except Exception:
                final_search_url = None

            cache_hit = False
            http_status = None
            num_found = None
            docs_returned = 0
            raw_items: List[Dict[str, Any]] = []
            error_text = None

            cached_payload = self._get_cached_results(query_text_final, pass_name)
            if cached_payload is not None:
                cache_hit = True
                http_status = cached_payload.get("http_status")
                num_found = cached_payload.get("num_found")
                docs_returned = cached_payload.get("docs_returned") or 0
                raw_items = cached_payload.get("results") or []
                # Use cached URL if present
                final_search_url = cached_payload.get("final_search_url") or final_search_url
            else:
                for attempt in range(MAX_RETRIES):
                    try:
                        self._throttle()
                        resp = requests.get(base_url, params=params, timeout=REQUEST_TIMEOUT, verify=False)
                        http_status = int(resp.status_code)
                        if http_status != 200:
                            self.network_error_count += 1
                        resp.raise_for_status()

                        data = resp.json() or {}
                        num_found = int(data.get("response", {}).get("numFound", 0) or 0)
                        docs = data.get("response", {}).get("docs", []) or []
                        docs_returned = len(docs)

                        def _norm_field(v: Any, limit: int) -> str:
                            if isinstance(v, list):
                                s = " ".join([str(x) for x in v if x is not None])
                            else:
                                s = str(v or "")
                            s = re.sub(r"\s+", " ", s).strip()
                            return s[:limit]

                        raw_items = []
                        dropped_mediatype = 0
                        for doc in docs:
                            identifier = doc.get("identifier", "")
                            if not identifier:
                                continue
                            
                            # Mediatype filter (per media_label context)
                            mediatype_raw = doc.get("mediatype", "")
                            mediatype = _norm_field(mediatype_raw, 60).lower()
                            
                            # Context-specific allowlist
                            allowed_types = []
                            if media_label == "image":
                                allowed_types = ["image"]
                            elif media_label == "video":
                                allowed_types = ["movies", "movingimage"]
                            else:
                                # DOC/MAP context (texts mediatype) - allow for now
                                allowed_types = ["texts", "text"]
                            
                            # Fail-closed: drop if mediatype unknown or not allowed
                            if not mediatype:
                                dropped_mediatype += 1
                                if self.verbose:
                                    print(f"  🚫 AAR: Dropped {identifier} (DROP_UNKNOWN_MEDIATYPE, context={media_label})")
                                continue
                            if mediatype not in allowed_types:
                                dropped_mediatype += 1
                                if self.verbose:
                                    print(f"  🚫 AAR: Dropped {identifier} (DROP_MEDIATYPE_NOT_ALLOWED: {mediatype}, context={media_label})")
                                continue
                            
                            raw_items.append(
                                {
                                    "archive_item_id": identifier,
                                    "title": _norm_field(doc.get("title", "Untitled"), 240),
                                    "description": _norm_field(doc.get("description", ""), 1200),
                                    "collection": _norm_field(doc.get("collection", ""), 400),
                                    "subject": _norm_field(doc.get("subject", ""), 400),
                                    "mediatype": mediatype,
                                    "asset_url": f"https://archive.org/details/{identifier}",
                                    "downloads": int(doc.get("downloads", 0) or 0),
                                }
                            )

                        # Save raw items + metadata to cache (A/B)
                        self._save_to_cache(
                            query_text_final,
                            pass_name,
                            {
                                "final_search_url": final_search_url,
                                "http_status": http_status,
                                "num_found": num_found,
                                "rows_requested": rows_requested,
                                "docs_returned": docs_returned,
                                "results": raw_items,
                            },
                        )
                        
                        # Telemetry: mediatype filter
                        if dropped_mediatype > 0 and self.verbose:
                            total_before = docs_returned
                            total_after = len(raw_items)
                            print(f"📊 AAR Mediatype Filter ({media_label}): before={total_before}, after={total_after}, dropped={dropped_mediatype}")
                        
                        break
                    except requests.exceptions.Timeout as e:
                        error_text = f"timeout:{e}"
                        self.network_error_count += 1
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(1)
                            continue
                    except requests.exceptions.RequestException as e:
                        error_text = f"request:{e}"
                        self.network_error_count += 1
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(1)
                            continue
                    except Exception as e:
                        error_text = f"unexpected:{e}"
                        break

            # Apply gates (always, even for cache hit)
            # Include subject in combined text for better must-hit coverage.
            for it in raw_items:
                if it.get("subject") and not it.get("collection"):
                    # leave collection; subject is already in dict and used by gates below
                    pass
            # Gates currently look at title/description/collection; include subject by appending to description
            gated_input: List[Dict[str, Any]] = []
            for it in raw_items:
                it2 = dict(it)
                subj = str(it2.get("subject") or "")
                if subj:
                    it2["description"] = (str(it2.get("description") or "") + " " + subj).strip()
                gated_input.append(it2)

            filtered, gate_stats = self._apply_topic_gates(
                gated_input, query_context=f"{pass_name}:{query_text[:40]}"
            )
            after_gates = len(filtered)

            # Structured audit line per attempt (A)
            self._log_query_attempt(
                {
                    "query_text": query_text_final,
                    "pass": pass_name,
                    "final_search_url": final_search_url,
                    "http_status": http_status,
                    "num_found": num_found,
                    "rows_requested": rows_requested,
                    "docs_returned": docs_returned,
                    "after_gates": after_gates,
                    "gate_stats": gate_stats,
                    "cache_hit": cache_hit,
                    "error": error_text,
                    "cache_hit_count": self.cache_hit_count,
                }
            )

            if after_gates > 0:
                # Tag for downstream audit/scoring
                for it in filtered:
                    it["_search_pass"] = pass_name
                    it["_search_query_text"] = query_text_final
                    it["_search_num_found"] = num_found
                return filtered[:max_results]

            # Only run relaxed pass if strict returned 0 (or all got filtered out)
            if pass_name == "A_strict":
                continue

        return []
    
    def _fetch_asset_metadata(self, archive_item_id: str) -> Dict[str, Any]:
        """
        Fetch size + duration from archive.org metadata API.
        Returns: {"size_bytes": int, "duration_sec": float}
        """
        metadata_url = f"https://archive.org/metadata/{archive_item_id}"
        try:
            self._throttle()  # Respect rate limiting
            response = requests.get(metadata_url, timeout=10, verify=False)
            response.raise_for_status()
            metadata = response.json()
            
            files = metadata.get("files", [])
            for f in files:
                fmt = f.get("format", "")
                if fmt in ["MPEG4", "h.264"] or f.get("name", "").lower().endswith(".mp4"):
                    size_bytes = int(f.get("size", "0"))
                    duration_sec = float(f.get("length", "0") or "0")
                    return {"size_bytes": size_bytes, "duration_sec": duration_sec}
            return {"size_bytes": 0, "duration_sec": 0}
        except Exception as e:
            print(f"⚠️  AAR: Metadata fetch failed for {archive_item_id}: {e}")
            return {"size_bytes": 0, "duration_sec": 0}
    
    def _generate_entity_queries(self, scene: Dict[str, Any]) -> List[str]:
        """
        A2 FIX: Generate 3-6 entity-first search queries from scene narration.
        Priority:
        1. Entity-first queries (proper nouns, operations, places)
        2. Context queries (time period + topic)
        3. Generic fallback (avoid if possible)
        
        Returns: List of search queries
        """
        queries = []
        
        # Extract entities from narration_summary or keywords
        summary = str(scene.get("narration_summary") or "")
        keywords = scene.get("keywords") or []
        
        # Entity detection patterns
        entities = []
        
        # Multi-word proper nouns (St Nazaire, HMS Campbeltown, Operation Chariot)
        for m in re.findall(r"\b[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3}\b", summary):
            val = m.strip()
            if len(val) >= 4 and (" " in val or val.startswith(("HMS", "USS", "Operation"))):
                entities.append(val)
        
        # From keywords: prioritize multi-word phrases
        for kw in keywords[:15]:
            kw_str = str(kw or "").strip()
            if len(kw_str) >= 4 and (" " in kw_str or kw_str.lower().startswith(("hms", "uss", "operation"))):
                if kw_str not in entities:
                    entities.append(kw_str)
        
        # Generate entity-first queries (2-3 queries)
        entity_queries = []
        for i, entity in enumerate(entities[:3]):
            # Combine entity with context for richer query
            if i == 0:
                entity_queries.append(entity)  # Pure entity query
            else:
                # Add context: operation/location + WWII/historical context
                if "operation" in entity.lower():
                    entity_queries.append(f"{entity} WWII raid")
                elif any(naval in entity.lower() for naval in ["hms", "uss", "ship", "destroyer", "battleship"]):
                    entity_queries.append(f"{entity} naval warfare")
                else:
                    entity_queries.append(f"{entity} World War II")
        
        queries.extend(entity_queries)
        
        # Context queries (2-3 queries): time period + topic
        context_queries = []
        
        # Detect time period
        year_matches = re.findall(r"\b(19\d{2}|194\d|195\d)\b", summary)
        if year_matches:
            time_context = year_matches[0]
        else:
            # IMPORTANT: do NOT default to WWII (breaks non-WWII episodes like Moscow 1812).
            # Also avoid "historical/history" because later filters ban them.
            time_context = "archival"
        
        # Detect topic from keywords
        topics = []
        for kw in keywords[:10]:
            kw_lower = str(kw or "").lower()
            if kw_lower in ["raid", "invasion", "assault", "attack", "operation"]:
                topics.append("military operation")
            elif kw_lower in ["naval", "ship", "destroyer", "battleship", "submarine"]:
                topics.append("naval")
            elif kw_lower in ["deception", "intelligence", "spy", "secret"]:
                topics.append("intelligence")
        
        # Generate context queries
        if topics:
            # Avoid banned token "footage" (we prefer archive-friendly "newsreel")
            context_queries.append(f"{time_context} {topics[0]} newsreel")
        if len(entities) > 0:
            context_queries.append(f"{time_context} {entities[0].split()[0]}")
        
        queries.extend(context_queries)
        
        # Generic fallback (ONLY if we have < 3 queries)
        if len(queries) < 3:
            # Use most specific keywords
            specific_kws = [kw for kw in keywords[:5] if len(str(kw or "")) >= 5]
            if specific_kws:
                queries.append(f"{' '.join(str(k) for k in specific_kws[:3])} documentary")
        
        # A2 ACCEPTANCE: Ban overly generic queries
        banned_patterns = [
            "world war ii strategies",
            "world war strategies",
            "ww2 strategies",
            "historical events",
            "war tactics",
            "military history"
        ]
        
        queries = [q for q in queries if q.lower() not in banned_patterns]
        
        # Limit to 6 queries max
        return queries[:6]

    def _scene_topic_category(self, scene: Dict[str, Any]) -> str:
        """Heuristic topic classification for query broadening tiers."""
        narration = str(scene.get("narration_summary", "")).lower()
        kws = " ".join([str(k or "").lower() for k in (scene.get("keywords") or [])])
        text = f"{narration} {kws}".strip()

        intel_markers = [
            "intelligence",
            "deception",
            "spy",
            "secret",
            "mincemeat",
            "documents",
            "forged",
            "falsified",
            "counterintelligence",
        ]
        naval_markers = [
            "naval",
            "ship",
            "ships",
            "destroyer",
            "battleship",
            "submarine",
            "fleet",
            "navy",
            "dock",
            "dry dock",
            "port",
            "harbor",
            "raid",
            "commando",
        ]
        maps_markers = ["map", "maps", "troop movement", "campaign", "invasion", "front line"]
        industry_markers = ["factory", "production", "industry", "shipyard", "munition", "wartime production"]

        if any(m in text for m in intel_markers):
            return "intel"
        if any(m in text for m in naval_markers):
            return "naval"
        if any(m in text for m in maps_markers):
            return "maps"
        if any(m in text for m in industry_markers):
            return "industry"
        return "generic"

    def _generate_query_tiers(self, scene: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        C) Query broadening ladder L1 → L2 → L3 → L4 → L5 (never-fail policy).
        
        Query Ladder (tight -> medium -> safe fallback):
        - L1 (FULL): Scene search_queries (as-is)
        - L2 (DROP_ADJECTIVES): deterministically remove adjectives/soft descriptors
        - L3 (DROP_YEAR): deterministically remove explicit years
        - L4 (ENTITY+OBJECT): entity + concrete object type
        - L5 (CURATED_FALLBACK): themed, anchored safety queries (still not generic)
        
        CRITICAL: Never use super-generic queries like "World War II" alone or "documentary footage".
        All tiers MUST contain concrete anchors (names/places/years) from the scene.
        """
        category = self._scene_topic_category(scene)

        def _dedupe(xs: List[str]) -> List[str]:
            out = []
            seen = set()
            for x in xs:
                s = str(x or "").strip()
                if not s:
                    continue
                k = s.lower()
                if k in seen:
                    continue
                seen.add(k)
                out.append(s)
            return out

        def _extract_scene_anchors(scene_obj: Dict[str, Any]) -> List[str]:
            """
            Deterministically extract strong anchors (names/places/years) from the scene.
            These anchors are used to keep fallback queries inside the documentary topic.
            """
            # PRIMARY: use FDA search queries (they SHOULD contain the right names/places/years).
            q_list = scene_obj.get("search_queries") if isinstance(scene_obj.get("search_queries"), list) else []
            raw_queries = " ".join([q.strip() for q in q_list if isinstance(q, str) and q.strip()])

            # SECONDARY: scene summary + keywords (can contain sentence-initial fillers like "However")
            summ = scene_obj.get("narration_summary") if isinstance(scene_obj.get("narration_summary"), str) else ""
            kw_list = scene_obj.get("keywords") if isinstance(scene_obj.get("keywords"), list) else []
            raw_secondary = " ".join([str(summ or "").strip()] + [str(k or "").strip() for k in kw_list]).strip()

            raw = raw_queries or raw_secondary
            if not str(raw).strip():
                return []

            # Years
            years = re.findall(r"\b(?:15|16|17|18|19|20)\d{2}\b", raw)

            # Proper-noun phrases (keeps order-ish)
            props = re.findall(r"\b[A-Z][A-Za-z'’\\.-]*(?:\s+[A-Z][A-Za-z'’\\.-]*){0,3}\b", raw)

            # Normalize + filter generics
            generic = {
                "world war", "world war ii", "wwii", "ww2", "war", "wartime",
                "army", "troops", "soldiers", "military", "battle", "campaign",
                "russia", "russian", "france", "french", "britain", "british", "germany", "german",
                "documents", "document", "maps", "map", "letter", "letters", "correspondence",
                "aftermath", "destruction", "ruins", "city", "fire", "fires",
                # discourse / sentence-initial fillers (NOT anchors)
                "however", "therefore", "moreover", "contrary", "historical", "consensus", "primarily", "largely",
                # months (too generic)
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
            }

            anchors: List[str] = []
            for y in years:
                if y not in anchors:
                    anchors.append(y)
            for p in props:
                norm = self._normalize_text(p)
                if not norm or norm in generic or len(norm) < 4:
                    continue
                if norm not in anchors:
                    anchors.append(norm)

            # Also allow key lowercase anchors if present (e.g., "napoleon", "moscow" in lowercased queries)
            for w in re.findall(r"\b[a-z][a-z'\-]{3,}\b", raw.lower()):
                if w in generic:
                    continue
                if w in ("napoleon", "moscow", "kremlin", "rostopchin", "alexander", "grande", "armee"):
                    if w not in anchors:
                        anchors.append(w)

            # If we got <2 anchors from queries, try secondary text once more.
            if len(anchors) < 2 and raw_secondary and raw_secondary != raw:
                more = raw_secondary
                years2 = re.findall(r"\b(?:15|16|17|18|19|20)\d{2}\b", more)
                props2 = re.findall(r"\b[A-Z][A-Za-z'’\\.-]*(?:\s+[A-Z][A-Za-z'’\\.-]*){0,3}\b", more)
                for y in years2:
                    if y not in anchors:
                        anchors.append(y)
                for p in props2:
                    norm = self._normalize_text(p)
                    if not norm or norm in generic or len(norm) < 4:
                        continue
                    if norm not in anchors:
                        anchors.append(norm)

            return anchors[:6]

        # L1: prefer FDA-provided scene.search_queries (already sanitized upstream).
        # If missing, fallback to internal entity query generator.
        l1 = []
        sq = scene.get("search_queries", None)
        if isinstance(sq, list) and sq:
            l1 = [str(q or "").strip() for q in sq if str(q or "").strip()]
        else:
            l1 = self._generate_entity_queries(scene) or []

        anchors = _extract_scene_anchors(scene)
        a1 = anchors[0] if len(anchors) >= 1 else ""
        a2 = anchors[1] if len(anchors) >= 2 else ""
        year = next((a for a in anchors if re.fullmatch(r"(?:15|16|17|18|19|20)\\d{2}", a)), "")
        is_pre_1900 = bool(year) and int(year) < 1900

        def _drop_adjectives(q: str) -> str:
            # Deterministic, conservative filter: remove obvious adjectives/soft descriptors.
            # Keep proper nouns + years + concrete objects.
            bad = {
                "famous", "iconic", "epic", "dramatic", "massive", "major", "significant",
                "strategic", "tactical", "important", "historic", "historical", "legendary",
                "rare", "unique", "amazing", "best", "greatest", "ultimate",
            }
            toks = [t for t in str(q or "").strip().split() if t]
            kept = []
            for t in toks:
                tl = t.lower()
                # keep years and Capitalized anchors
                if re.fullmatch(r"(?:15|16|17|18|19|20)\d{2}", t):
                    kept.append(t)
                    continue
                if t[:1].isupper():
                    kept.append(t)
                    continue
                if tl in bad:
                    continue
                kept.append(t)
            return " ".join(kept).strip()

        def _drop_years(q: str) -> str:
            toks = [t for t in str(q or "").strip().split() if t]
            toks = [t for t in toks if not re.fullmatch(r"(?:15|16|17|18|19|20)\d{2}", t)]
            return " ".join(toks).strip()

        # L2/L3 derived from L1 (deterministic ladder).
        l2_base = [_drop_adjectives(q) for q in l1 if str(q or "").strip()]

        # Primary entity anchor used for multiple tiers
        ent = a1 or a2 or ""

        # IMPORTANT: Video-friendly anchored variants.
        # FDA-style queries often target scans/documents (great for images) but can yield 0 video hits.
        # Add a few anchored "broad but not generic" queries so the VIDEO stage has a chance:
        # - keep strong entity anchors (names/places/years)
        # - avoid fully generic queries (must contain an anchor)
        video_variants: List[str] = []
        if ent:
            video_variants.append(ent)
            # anchored, still documentary-friendly
            video_variants.append(f"{ent} newsreel")
            video_variants.append(f"{ent} documentary")
            if year:
                video_variants.append(f"{ent} {year}")
            if a2 and a2 != ent:
                video_variants.append(f"{ent} {a2}")

        # Combine: variants first, then regular L2. Dedupe keeps order.
        l2 = _dedupe(video_variants + l2_base)
        l3 = _dedupe([_drop_years(q) for q in l2 if str(q or "").strip()])

        # L4: entity + object type (deterministic pack)
        obj_pack = ["archival map", "historical engraving", "portrait photograph", "handwritten letter", "archival documents"]
        l4: List[str] = []
        if ent:
            for obj in obj_pack:
                if year:
                    l4.append(f"{ent} {year} {obj}")
                l4.append(f"{ent} {obj}")

        # L5: curated themed fallback (still anchored; never "documentary footage")
        l5: List[str] = []
        if category == "maps":
            if ent:
                l5 += [f"archival map {ent}", f"route map {ent}", f"city map {ent}"]
        elif category == "intel":
            if ent:
                l5 += [f"handwritten letter {ent}", f"government correspondence {ent}", f"official documents {ent}"]
        elif category == "naval":
            if ent:
                l5 += [f"ship photograph {ent}", f"naval dock photograph {ent}", f"harbor photograph {ent}"]
        elif category == "industry":
            if ent:
                l5 += [f"factory photograph {ent}", f"shipyard photograph {ent}", f"industrial photograph {ent}"]
        else:
            if ent:
                l5 += [f"historical engraving {ent}", f"portrait photograph {ent}", f"archival documents {ent}"]

        # Keep compact + deterministic.
        return {
            "L1": _dedupe(l1)[:6],
            "L2": _dedupe(l2)[:6],
            "L3": _dedupe(l3)[:6],
            "L4": _dedupe(l4)[:6],
            "L5": _dedupe(l5)[:6],
        }
    
    def _normalize_text(self, text: str) -> str:
        """
        Section 3: Text normalization for robust matching.
        - lowercase
        - remove punctuation
        - normalize whitespace
        - simple plural normalization (documents → document)
        """
        if not text:
            return ""
        
        # Lowercase
        text = text.lower()
        
        # Remove punctuation (keep spaces, letters, numbers)
        text = re.sub(r"[^\w\s-]", " ", text)
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        # Simple plural normalization for common terms
        text = re.sub(r"\b(documents?|papers?|records?|files?|maps?|charts?)\b", 
                     lambda m: m.group(1).rstrip('s'), text)
        
        return text
    
    def _expand_with_synonyms(self, terms: List[str]) -> List[str]:
        """
        Section 4: Expand terms with synonym groups for robust matching.
        """
        expanded = set()
        for term in terms:
            term_norm = self._normalize_text(term)
            expanded.add(term_norm)
            
            # Check if term belongs to a synonym group
            for group_name, synonyms in VISUAL_SYNONYM_GROUPS.items():
                if term_norm in [self._normalize_text(s) for s in synonyms]:
                    # Add all synonyms from this group
                    expanded.update([self._normalize_text(s) for s in synonyms])
        
        return list(expanded)
    
    def _relevance_gate(
        self,
        asset: Dict[str, Any],
        beat_context: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        RELEVANCE GATE - Section 5: Phase 1 hard filter (PASS/FAIL).
        
        Asset MUST pass at least 2 of 3 rules to proceed to scoring.
        NO FALLBACKS - if fails, it's HARD REJECTED.
        
        Returns:
            (pass: bool, reason: str, details: dict)
        """
        # Normalize all texts (Section 3)
        title = self._normalize_text(str(asset.get("title") or ""))
        desc = self._normalize_text(str(asset.get("description") or ""))
        subjects = [self._normalize_text(str(s or "")) for s in (asset.get("subject") or [])]
        haystack = f"{title} {desc} {' '.join(subjects)}".strip()
        
        narration = self._normalize_text(str(beat_context.get("narration_summary") or beat_context.get("text_preview") or ""))
        keywords = [self._normalize_text(str(k or "")) for k in (beat_context.get("keywords") or [])]
        shot_types = beat_context.get("shot_types") or []
        query_used = self._normalize_text(str(asset.get("query_used") or ""))
        
        # RULE 1: ANCHOR MATCH (Section 5)
        anchor_pass, anchor_details = self._check_anchor_match_v2(haystack, narration, keywords, query_used)
        
        # RULE 2: VISUAL NOUN MATCH (Section 5)
        visual_pass, visual_details = self._check_visual_noun_match_v2(haystack, narration, keywords, shot_types)
        
        # RULE 3: NO FORBIDDEN PATTERNS (Section 5 - context-aware)
        forbidden_pass, forbidden_details = self._check_forbidden_patterns_v2(haystack, shot_types)
        
        rules_passed = sum([anchor_pass, visual_pass, forbidden_pass])
        
        # Section 6: Gate output structure
        details = {
            "rule_1_anchor": "PASS" if anchor_pass else f"FAIL",
            "rule_2_visual": "PASS" if visual_pass else f"FAIL",
            "rule_3_forbidden": "PASS" if forbidden_pass else f"FAIL",
            "rules_passed": f"{rules_passed}/3",
            "anchor_details": anchor_details,
            "visual_details": visual_details,
            "forbidden_details": forbidden_details
        }

        # CRITICAL POLICY: Anchor match is mandatory.
        # Beat text often contains generic actions ("sabotage", "retreat") that can match modern wars.
        # Without an anchor requirement, visually-plausible but topically wrong assets can pass (Ukraine/Syria/etc).
        if not anchor_pass:
            details["gate_policy"] = "anchor_required"
            return False, f"FAIL (anchor_required, {rules_passed}/3 rules)", details

        if rules_passed >= 2:
            return True, f"PASS ({rules_passed}/3 rules)", details
        reason = f"FAIL ({rules_passed}/3 rules)"
        return False, reason, details
    
    def _check_anchor_match_v2(
        self, 
        haystack: str, 
        narration: str, 
        keywords: List[str],
        query_used: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        RULE 1 (Section 5): Asset must contain specific anchor (NOT just era).
        
        ANCHOR = primarily keywords/summary concrete terms.
        Proper nouns are BONUS/extra signal when they exist, not required.
        
        Returns:
            (pass: bool, details: dict with matched/missing anchors)
        """
        # PRIMARY: Extract anchors from keywords (scene + beat context).
        # NOTE: Beat-level text often omits place/year; scene-level anchors MUST be present in keywords.
        anchors: List[str] = []
        for kw in (keywords or []):
            kw_norm = self._normalize_text(kw)
            if not kw_norm or len(kw_norm) < 3:
                continue
            if kw_norm not in anchors:
                anchors.append(kw_norm)

        # Heuristic: distinguish strong anchors (names/places/years) from weak generic words.
        # CRITICAL: Rule-1 "anchor match" MUST NOT be satisfied by generic production words
        # ("print", "original", "copy", "archive") or by generic conflict nouns ("battle", "occupation").
        # Those belong to Rule-2 (visual nouns) or are simply too broad.
        generic_era = {
            "world war", "world war ii", "wwii", "ww2", "war", "wartime", "world", "ii", "the",
            # demonyms / countries (too broad to anchor a beat by themselves)
            "russia", "russian", "france", "french", "britain", "british", "germany", "german",
            "america", "american", "soviet", "ukraine", "ukrainian",
            # generic conflict nouns (too generic to anchor a beat)
            "army", "troops", "soldier", "soldiers", "military", "battle", "campaign",
            "occupation", "occupied", "sabotage", "fire", "fires", "ruins", "city", "town",
            "retreat", "march", "winter", "supplies", "discipline", "looting",
            # generic visual nouns (not anchors)
            "map", "maps", "document", "documents", "letter", "letters", "correspondence",
            "aftermath", "destruction", "buildings", "wood", "wooden",
            # production / archive boilerplate (NOT anchors; these caused false positives)
            "archive", "archival", "original", "print", "copy", "scan", "page",
            "photo", "photos", "photograph", "photographs", "image", "images", "picture", "pictures",
            "video", "film", "newsreel", "documentary",
            # discourse / fillers (NOT anchors)
            "however", "therefore", "moreover", "contrary", "historical", "consensus", "primarily", "largely",
            # months (too generic; can match random broadcast dates)
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        }

        year_re = re.compile(r"\b(?:15|16|17|18|19|20)\d{2}\b")

        strong: List[str] = []
        weak: List[str] = []
        for a in anchors:
            if a in generic_era:
                weak.append(a)
                continue
            if year_re.fullmatch(a):
                strong.append(a)
                continue
            if len(a) >= 4:
                strong.append(a)
            else:
                weak.append(a)

        # If we have strong anchors, require matches on strong anchors (not weak generic terms).
        # RELAXED POLICY: Require only 1 match (not 2) to avoid over-rejection.
        # Reason: Archive.org often has limited metadata; requiring 2+ anchors rejects 90% of relevant videos.
        if strong:
            matched = [a for a in strong[:25] if a in haystack]
            matched_years = [a for a in matched if year_re.fullmatch(a)]
            # NEW: Always require only 1 match (down from 2), OR any year match
            required = 1
            passed = bool(matched_years) or (len(matched) >= required)
            return passed, {
                "mode": "strong_anchors",
                "required_matches": required,
                "matched_anchor_terms": matched[:5],
                "matched_years": matched_years[:3],
                "strong_anchor_count": len(strong),
                "weak_anchor_count": len(weak),
            }

        # Fallback: no strong anchors detected → FAIL (weak anchors alone are insufficient).
        # Reason: Weak anchors like "army"/"battle"/"occupation" can match ANY war content (WWII, Ukraine, Syria, etc.).
        # We require at least 1 strong anchor (place/person/year) to prevent off-topic contamination.
        matched_anchors = [a for a in weak[:25] if a in haystack]
        return False, {
            "mode": "weak_anchors_only_insufficient",
            "matched_weak_anchors": matched_anchors[:5],
            "missing_strong_anchors": strong[:5] if strong else ["NO_STRONG_ANCHORS_DETECTED"],
            "strong_anchor_count": len(strong),
            "weak_anchor_count": len(weak),
            "policy": "weak_anchors_insufficient_for_pass"
        }
    
    def _check_visual_noun_match_v2(
        self,
        haystack: str,
        narration: str,
        keywords: List[str],
        shot_types: List[str]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        RULE 2 (Section 5): Asset must contain concrete visual objects/environments.
        Uses synonym groups (Section 4) for robust matching.
        """
        # Detect which visual categories are relevant from narration + keywords + shot_types
        combined = f"{narration} {' '.join(keywords)} {' '.join(shot_types)}"
        
        relevant_categories = []
        for group_name, synonyms in VISUAL_SYNONYM_GROUPS.items():
            if any(self._normalize_text(s) in combined for s in synonyms):
                relevant_categories.append(group_name)
        
        if not relevant_categories:
            # No specific visual nouns detected → neutral (don't fail on this)
            return True, {
                "matched_visual_terms": [],
                "missing_visual_terms": [],
                "reason": "no_visual_requirements_detected"
            }
        
        # Check if asset contains visuals from relevant categories
        matched_visuals = []
        missing_visuals = []
        
        for cat in relevant_categories:
            synonyms = VISUAL_SYNONYM_GROUPS[cat]
            category_matched = False
            
            for synonym in synonyms:
                if self._normalize_text(synonym) in haystack:
                    matched_visuals.append(f"{cat}:{synonym}")
                    category_matched = True
                    break
            
            if not category_matched:
                missing_visuals.append(cat)
        
        if matched_visuals:
            return True, {
                "matched_visual_terms": matched_visuals,
                "missing_visual_terms": missing_visuals
            }
        
        return False, {
            "matched_visual_terms": [],
            "missing_visual_terms": relevant_categories
        }
    
    def _check_forbidden_patterns_v2(
        self,
        haystack: str,
        shot_types: List[str]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        RULE 3 (Section 5): Context-aware forbidden patterns.
        
        Forbidden depends on shot_types (from FDA ALLOWED_SHOT_TYPES enum):
        - historical_battle_footage/troop_movement/destruction_aftermath → ALLOW combat
        - archival_documents/maps_context/atmosphere_transition → FORBID combat/montage
        """
        # Normalize shot_types (they come from FDA enum, should already be valid)
        shot_types_norm = [self._normalize_text(st) for st in shot_types]
        
        # Check if beat explicitly needs combat/battle footage (using FDA enum)
        explicit_combat_needed = any(
            st in shot_types_norm for st in COMBAT_ALLOWED_SHOT_TYPES
        )
        
        if explicit_combat_needed:
            # Combat is allowed for this beat
            return True, {
                "forbidden_hit_terms": [],
                "reason": "combat_allowed_by_shot_types",
                "shot_types_checked": shot_types_norm[:3]
            }
        
        # Check for forbidden patterns (Section 5)
        forbidden_hits = []
        for pattern in FORBIDDEN_FOR_NON_COMBAT:
            pattern_norm = self._normalize_text(pattern)
            if pattern_norm in haystack:
                forbidden_hits.append(pattern)
        
        if forbidden_hits:
            return False, {
                "forbidden_hit_terms": forbidden_hits,
                "reason": "forbidden_pattern_detected",
                "shot_types_checked": shot_types_norm[:3]
            }
        
        return True, {
            "forbidden_hit_terms": [],
            "reason": "no_forbidden_patterns",
            "shot_types_checked": shot_types_norm[:3]
        }
    
    def _score_asset_quality(self, asset: Dict[str, Any], scene: Dict[str, Any]) -> float:
        """
        Smart scoring: relevance + size penalty + duration bonus + reuse potential.
        Higher score = better asset.
        """
        import math
        
        # Base score from keyword relevance (title + description)
        # NOTE: Favor specific entities over generic war/history terms to reduce off-topic footage.
        keywords = scene.get("keywords", [])
        title = str(asset.get("title") or "").lower()
        desc = str(asset.get("description") or "").lower()

        generic_markers = {
            "war",
            "world",
            "world war",
            "world war ii",
            "ww2",
            "wwii",
            "strategy",
            "strategies",
            "tactics",
            "warfare",
            "history",
            "historical",
            "conflict",
            "events",
            "battle",
            "footage",
        }

        # Penalize obvious "content advisory"/propaganda items (often unsuitable)
        content_markers = [
            "content advisory",
            "explicit racism",
            "racism",
            "extreme violence",
            "propaganda",
        ]
        content_penalty = -12.0 if any(m in desc for m in content_markers) else 0.0

        # Weighted relevance: multiword & longer keywords count more; generic markers count zero.
        # CRITICAL FIX: Track if we have ANY specific entity matches (not just generic WWII terms)
        relevance = 0.0
        specific_entity_matches = 0
        generic_only_matches = 0
        
        for kw in keywords or []:
            kw_s = str(kw or "").strip().lower()
            if not kw_s:
                continue
            # collapse spaced acronyms: "H M S" -> "HMS"
            kw_s = re.sub(r"\b(?:[a-z]\s){2,6}[a-z]\b", lambda m: m.group(0).replace(" ", ""), kw_s)
            
            # Skip generic markers entirely (they add no relevance)
            if kw_s in generic_markers:
                generic_only_matches += 1
                continue
            
            w = 1.0
            if " " in kw_s:
                w += 0.75
            if len(kw_s) >= 10:
                w += 0.25
            if kw_s in title:
                relevance += 1.0 * w
                specific_entity_matches += 1
            elif kw_s in desc:
                relevance += 0.6 * w
                specific_entity_matches += 1
        
        # CRITICAL: Penalize assets with ONLY generic matches (no specific entities)
        # This prevents "World War II" generic footage from ranking high
        if specific_entity_matches == 0 and generic_only_matches > 0:
            relevance -= 15.0  # Heavy penalty for "WWII" only, no specific entity
        
        # Content penalty: avoid obvious "screen capture / subtitles / modern UI" sources.
        # (Archive.org can contain YouTube rips or captioned footage; we want clean archival visuals.)
        bad_markers = [
            "youtube",
            "screen record",
            "screenrecord",
            "screencast",
            "gameplay",
            "walkthrough",
            "reaction",
            "subscribe",
            "like and subscribe",
            "字幕",  # subtitles (JP/CN markers)
            "subtitles",
            "with subtitles",
            "captioned",
            "captions",
            "closed captions",
            "cc",
        ]
        penalty = 0.0
        hay = f"{title} {desc}".strip()
        for m in bad_markers:
            if m in hay:
                penalty -= 4.0
                break
        # Light penalty for "trailer"/"promo" which often contains big on-screen text
        if "trailer" in hay or "promo" in hay or "teaser" in hay:
            penalty -= 1.5

        # Size penalty (prefer < 100 MB)
        size_mb = asset.get("size_bytes", 0) / (1024 * 1024)
        if size_mb == 0:
            size_penalty = 0
        elif size_mb < 50:
            size_penalty = 2.0
        elif size_mb < 100:
            size_penalty = 1.0
        elif size_mb < 200:
            size_penalty = -0.5
        else:
            size_penalty = -2.0  # Heavy penalty for > 200 MB
        
        # Duration bonus (prefer 5-20 min videos)
        duration_min = asset.get("duration_sec", 0) / 60.0
        if duration_min == 0:
            duration_bonus = 0
        elif 5 <= duration_min <= 20:
            duration_bonus = 1.5
        elif 2 <= duration_min < 5 or 20 < duration_min <= 40:
            duration_bonus = 0.5
        else:
            duration_bonus = -1.0  # Too short or too long
        
        # Reuse potential (longer video = more subclipy possible)
        reuse_potential = math.log(max(1, duration_min)) * 0.3
        
        # Popularity (DOWNSCALED - only tiebreaker, NOT main driver)
        # OLD: math.log(max(1, downloads)) * 0.2  (too strong)
        # NEW: math.log(max(1, downloads)) * 0.05  (weak tiebreaker only)
        popularity = math.log(max(1, asset.get("downloads", 0))) * 0.05
        
        # Apply quality penalty from topic gates (soft penalize)
        gate_penalty = 0.0
        if asset.get("_quality_penalty"):
            gate_penalty = -10.0 * (1.0 - float(asset.get("_quality_penalty", 1.0)))
        
        # C) Tier boost: prefer L1 > L2 > L3 when merging broadened results
        tier = str(asset.get("query_tier") or "").upper()
        tier_boost = 0.0
        if tier == "L1":
            tier_boost = 2.0
        elif tier == "L2":
            tier_boost = 1.0

        score = (
            (relevance * 10.0)
            + size_penalty
            + duration_bonus
            + reuse_potential
            + popularity
            + penalty
            + content_penalty
            + gate_penalty
            + tier_boost
        )
        return score
    
    def resolve_scene_assets(
        self,
        scene: Dict[str, Any],
        min_assets_per_scene: int = 3,
        max_assets_per_scene: int = 8,
        used_video_item_ids: Optional[set] = None,
        max_unique_video_sources_per_episode: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Naplní assets[] pro jednu scénu na základě search_queries.
        
        Args:
            scene: Scene dict z shot_plan
            min_assets_per_scene: Minimální počet assetů (fallback pokud search nenajde dost)
            max_assets_per_scene: Maximální počet assetů
        
        Returns:
            List of resolved assets
        """
        # Per-scene safety limits (fail-fast, prevent RUNNING forever)
        # Preview MUST be fast (seconds), full compile can be more patient.
        try:
            if self.preview_mode:
                scene_timeout_s = float(os.getenv("AAR_PREVIEW_SCENE_TIMEOUT_S", "15"))
            else:
                scene_timeout_s = float(os.getenv("AAR_SCENE_TIMEOUT_S", "120"))
        except Exception:
            scene_timeout_s = 20.0 if self.preview_mode else 120.0
        try:
            if self.preview_mode:
                max_query_attempts = int(os.getenv("AAR_PREVIEW_MAX_QUERY_ATTEMPTS", "3"))
            else:
                max_query_attempts = int(os.getenv("AAR_MAX_QUERY_ATTEMPTS", "10"))
        except Exception:
            max_query_attempts = 4 if self.preview_mode else 10

        scene_start_ts = time.time()
        scene_id = scene.get("scene_id")
        # Attach context for structured logs (used by search_archive_org)
        self._log_context = {"scene_id": scene_id} if scene_id else {}

        # C) Query broadening ladder (L1 → L2 → L3 → L4 → L5)
        tiered_queries = self._generate_query_tiers(scene)
        if not (tiered_queries.get("L1") or tiered_queries.get("L2") or tiered_queries.get("L3") or tiered_queries.get("L4") or tiered_queries.get("L5")):
            # NO FALLBACK / NO PLACEHOLDERS: continue with empty assets; never fail the pipeline
            print(f"⚠️  AAR: Scene {scene.get('scene_id')} has no queries; returning empty assets (NO FALLBACK)")
            return []

        # Prefer specific queries (contain scene entities) over generic war terms
        def _norm_term(t: Any) -> str:
            s = str(t or "").strip().lower()
            if not s:
                return ""
            s = re.sub(r"\b(?:[a-z]\s){2,6}[a-z]\b", lambda m: m.group(0).replace(" ", ""), s)
            s = re.sub(r"[^a-z0-9\s\-]", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        generic_terms = {
            "world",
            "war",
            "world war",
            "world war ii",
            "ww2",
            "wwii",
            "strategy",
            "strategies",
            "tactics",
            "warfare",
            "history",
            "historical",
            "conflict",
            "events",
            "battle",
            "footage",
        }

        strong_terms: List[str] = []
        for kw in (scene.get("keywords") or []):
            k = _norm_term(kw)
            if not k or k in generic_terms or len(k) < 4:
                continue
            if k not in strong_terms:
                strong_terms.append(k)

        summary = str(scene.get("narration_summary") or "")
        for ent in re.findall(r"\b(?:[A-Z][a-z]{2,}|[A-Z]{2,})(?:[.\-]?\s+(?:[A-Z][a-z]{2,}|[A-Z]{2,})){0,3}\b", summary):
            k = _norm_term(ent)
            if not k or k in generic_terms or len(k) < 4:
                continue
            if k not in strong_terms:
                strong_terms.append(k)

        def _query_score(q: str) -> float:
            ql = q.lower()
            s = 0.0
            if len(ql.split()) >= 2:
                s += 1.0
            if any(ch.isdigit() for ch in ql):
                s += 1.0
            if strong_terms and any(t in ql for t in strong_terms[:8]):
                s += 3.0
            # CRITICAL: Heavy penalty for generic-only queries (no specific entities)
            # DISABLED: These terms are legitimate for historical documentary content
            # if any(m in ql for m in ("strategy", "strategies", "tactics", "warfare", "history", "historical", "footage")):
            #     s -= 2.0
            # REJECT purely generic queries like "world war ii" or "wwii"
            query_words = set(ql.replace("-", " ").split())
            if query_words.issubset({"world", "war", "ii", "ww2", "wwii", "2"}):
                s -= 10.0  # Reject "World War II" alone
            if len(ql) < 12:
                s -= 0.5
            return s

        # Multi-pass resolve:
        # Pass 1: L1 queries in given order
        # Pass 2: L2 broadened object queries (still anchored)
        # Pass 3: L3 safe broaden (still anchored + physical artefacts)
        MAX_QUERIES_PER_SCENE = 8

        def _dedupe_keep_order(queries: List[str]) -> List[str]:
            seen = set()
            out = []
            for q in queries or []:
                s = str(q or "").strip()
                if not s:
                    continue
                k = s.lower()
                if k in seen:
                    continue
                seen.add(k)
                out.append(s)
            return out

        l1_pass = _dedupe_keep_order(tiered_queries.get("L1") or [])
        l2_pass = _dedupe_keep_order(tiered_queries.get("L2") or [])
        l3_pass = _dedupe_keep_order(tiered_queries.get("L3") or [])
        l4_pass = _dedupe_keep_order(tiered_queries.get("L4") or [])
        l5_pass = _dedupe_keep_order(tiered_queries.get("L5") or [])

        # Preview mode is aggressively time/attempt bounded (AAR_PREVIEW_MAX_QUERY_ATTEMPTS default=3).
        # If we start with strict L1 (often scan/doc oriented), we can burn the whole budget and never
        # try the anchored video-friendly variants (L2 starts with "<Entity>", "<Entity> newsreel", ...).
        # So for preview ONLY, we pull a small "L2 fast lane" to the front.
        if self.preview_mode:
            fast = []
            l1_lower = {q.lower() for q in l1_pass}
            for q in l2_pass:
                if q.lower() in l1_lower:
                    continue
                fast.append(q)
                if len(fast) >= 3:
                    break
            pass_plan = [
                ("pass0_L2_fast", fast),
                ("pass1_L1", l1_pass),
                ("pass2_L2", l2_pass),
                ("pass3_L3", l3_pass),
                ("pass4_L4", l4_pass),
                ("pass5_L5", l5_pass),
            ]
        else:
            pass_plan = [
                ("pass1_L1", l1_pass),
                ("pass2_L2", l2_pass),
                ("pass3_L3", l3_pass),
                ("pass4_L4", l4_pass),
                ("pass5_L5", l5_pass),
            ]

        # Apply generic query rejection only (keep order inside each pass)
        filtered_plan = []
        for pass_name, qs in pass_plan:
            kept = []
            for q in qs:
                score = _query_score(q)
                if score < -8.0:
                    if self.verbose:
                        print(f"  ⚠️  Rejecting generic query: '{q}' (score={score:.1f})")
                    continue
                kept.append(q)
            filtered_plan.append((pass_name, kept))

        # Cap total queries for runtime
        final_queries = []
        for _pn, qs in filtered_plan:
            for q in qs:
                final_queries.append(q)
                if len(final_queries) >= MAX_QUERIES_PER_SCENE:
                    break
            if len(final_queries) >= MAX_QUERIES_PER_SCENE:
                break
        
        if not final_queries:
            print(f"⚠️  AAR: All queries rejected as generic for scene {scene.get('scene_id')} - returning empty (NO FALLBACK)")
            return []  # NO FALLBACK - user request
        
        MAX_RESULTS_PER_QUERY = 25
        MAX_ASSETS_PER_QUERY = 6  # limit metadata fetch

        all_results: List[Dict[str, Any]] = []
        seen_item_ids: set = set()

        # ============================================================================
        # PER-SCENE DIAGNOSTICS COLLECTOR (for UI debugging)
        # ============================================================================
        query_diagnostics: List[Dict[str, Any]] = []
        reject_reasons_counter: Dict[str, int] = {}

        # ------------------------------------------------------------
        # MEDIA CASCADE (NO BLACK FALLBACKS):
        #   Stage 1: VIDEO assets (mp4/webm)
        #   Stage 2: IMAGE assets (jpg/png) via archive.org image search
        #   Stage 3: DOC/TEXT assets (maps/documents) via archive.org texts search (jpg/png page derivatives)
        # ------------------------------------------------------------
        # Attempt guards:
        # Historically we used ONE global attempt counter shared across stages (video→image→doc).
        # That caused a bad failure mode: if video yields 0 results (common for "map scan / document scan" queries),
        # we burned the entire attempt budget and never reached image/doc stages.
        # Fix: treat max_query_attempts as a PER-STAGE budget, still bounded by a global cap.
        attempt_idx = 0  # global (all stages)
        per_stage_attempts: Dict[str, int] = {"video": 0, "image": 0, "doc": 0}
        # Global cap: keep runtime bounded even if each stage gets its own budget.
        max_total_attempts = max(1, int(max_query_attempts or 1) * 3)

        def _run_query_list(stage: str, queries: List[str]) -> None:
            nonlocal attempt_idx, all_results, seen_item_ids, query_diagnostics, reject_reasons_counter, per_stage_attempts
            for query in queries:
                # Per-stage attempt budget
                if per_stage_attempts.get(stage, 0) >= max_query_attempts:
                    self._log_query_attempt(
                        {
                            "event": "stage_max_attempts",
                            "elapsed_s": round(float(time.time() - scene_start_ts), 3),
                            "stage": stage,
                            "stage_attempts_used": per_stage_attempts.get(stage, 0),
                            "stage_max_attempts": max_query_attempts,
                        }
                    )
                    break

                # Global attempt budget
                if attempt_idx >= max_total_attempts:
                    self._log_query_attempt(
                        {
                            "event": "scene_max_attempts",
                            "elapsed_s": round(float(time.time() - scene_start_ts), 3),
                            "max_total_attempts": max_total_attempts,
                            "stage": stage,
                        }
                    )
                    break

                attempt_idx += 1
                per_stage_attempts[stage] = per_stage_attempts.get(stage, 0) + 1

                # Per-scene time / attempts guard
                elapsed = time.time() - scene_start_ts
                if elapsed > scene_timeout_s:
                    self._log_query_attempt(
                        {
                            "event": "scene_timeout",
                            "elapsed_s": round(float(elapsed), 3),
                            "scene_timeout_s": scene_timeout_s,
                            "attempts_used": attempt_idx - 1,
                            "stage": stage,
                        }
                    )
                    break
                # NOTE: stage/global attempt caps handled above (do not double-count here)

                # Emit structured attempt log (scene-level)
                query_tier_guess = "L3"
                if query in (tiered_queries.get("L1") or []):
                    query_tier_guess = "L1"
                elif query in (tiered_queries.get("L2") or []):
                    query_tier_guess = "L2"
                self._log_query_attempt(
                    {
                        "event": "scene_query_start",
                        "attempt_index": attempt_idx,
                        "query_text": query,
                        "query_tier": query_tier_guess,
                        "max_results": MAX_RESULTS_PER_QUERY,
                        "stage": stage,
                    }
                )

                try:
                    if stage == "video":
                        results = self.search_multi_source(query, max_results=MAX_RESULTS_PER_QUERY)
                    elif stage == "image":
                        results = self.search_archive_org(
                            query,
                            max_results=MAX_RESULTS_PER_QUERY,
                            mediatype_filter=ARCHIVE_IMAGE_MEDIATYPE_FILTER,
                            media_label="image",
                        )
                    else:
                        # doc/texts stage (maps/documents)
                        results = self.search_archive_org(
                            query,
                            max_results=MAX_RESULTS_PER_QUERY,
                            mediatype_filter=ARCHIVE_TEXT_MEDIATYPE_FILTER,
                            media_label="doc",
                        )
                except Exception as e:
                    self._log_query_attempt(
                        {
                            "event": "scene_query_error",
                            "attempt_index": attempt_idx,
                            "query_text": query,
                            "query_tier": query_tier_guess,
                            "stage": stage,
                            "error": str(e),
                        }
                    )
                    continue

                num_found = len(results) if isinstance(results, list) else 0
                self._log_query_attempt(
                    {
                        "event": "scene_query_end",
                        "attempt_index": attempt_idx,
                        "query_text": query,
                        "query_tier": query_tier_guess,
                        "stage": stage,
                        "results_returned": num_found,
                    }
                )

                # Initialize per-query diagnostics
                q_diag: Dict[str, Any] = {
                    "query": query,
                    "stage": stage,
                    "tier": query_tier_guess,
                    "num_found": num_found,
                    "num_accepted_after_filters": 0,
                    "top_item_ids": [],
                    "reject_reasons": {},
                }

                if not results:
                    q_diag["reject_reasons"]["no_results"] = 1
                    reject_reasons_counter["no_results"] = reject_reasons_counter.get("no_results", 0) + 1
                    query_diagnostics.append(q_diag)
                    continue

                # Take top candidates per query (dedupe globally)
                taken = 0
                q_rejected: Dict[str, int] = {}
                for result in results:
                    item_id = result.get("archive_item_id")
                    if not item_id:
                        q_rejected["no_item_id"] = q_rejected.get("no_item_id", 0) + 1
                        continue
                    if item_id in seen_item_ids:
                        q_rejected["duplicate"] = q_rejected.get("duplicate", 0) + 1
                        continue
                    seen_item_ids.add(item_id)

                    # Fetch metadata (size/duration) for smart scoring
                    meta = self._fetch_asset_metadata(item_id)
                    
                    # Track accepted item
                    taken += 1
                    if len(q_diag["top_item_ids"]) < 3:
                        q_diag["top_item_ids"].append(item_id)

                    # Infer tier from query (check if it's in L1, L2, or L3)
                    query_tier = "L3"  # default
                    if query in (tiered_queries.get("L1") or []):
                        query_tier = "L1"
                    elif query in (tiered_queries.get("L2") or []):
                        query_tier = "L2"

                    asset = {
                        "provider": "archive_org",
                        "query_used": query,
                        "query_tier": query_tier,
                        "query_pass": result.get("_search_pass"),
                        "archive_item_id": item_id,
                        "asset_url": result.get("asset_url"),
                        # Downstream (CB) can render stills; for doc/texts we still treat as an image asset.
                        "media_type": "video" if stage == "video" else "image",
                        "priority": 1,  # adjusted later
                        "use_as": "primary_broll",
                        "recommended_subclips": [
                            {
                                # B: NO TITLECARDS default
                                "in_sec": 30,
                                "out_sec": 35,
                                "reason": f"Tier {query_tier} match for: {query[:60]}",
                            }
                        ],
                        "safety_tags": ["no_gore", "implied_only"],
                        "title": result.get("title", ""),
                        "description": result.get("description", ""),
                        "collection": result.get("collection", ""),
                        "downloads": result.get("downloads", 0),
                        "size_bytes": meta.get("size_bytes", 0),
                        "duration_sec": meta.get("duration_sec", 0),
                    }
                    all_results.append(asset)

                    if taken >= MAX_ASSETS_PER_QUERY:
                        q_rejected["max_per_query_reached"] = q_rejected.get("max_per_query_reached", 0) + (num_found - taken)
                        break

                # Finalize query diagnostics
                q_diag["num_accepted_after_filters"] = taken
                q_diag["reject_reasons"] = q_rejected
                for reason, count in q_rejected.items():
                    reject_reasons_counter[reason] = reject_reasons_counter.get(reason, 0) + count
                query_diagnostics.append(q_diag)

                # Stop broadening early if we already have enough candidates (proxy for numFound/approved)
                if len(seen_item_ids) >= MIN_RESULTS_TO_STOP_BROADENING:
                    return

        # Stage 1: video (all passes, in order)
        _run_query_list("video", final_queries)

        # ---------------------------------------------------------------------
        # MEDIA CASCADE FILL TARGET (anti-repetition)
        #
        # Old behavior used "< 2" which often produced exactly 2 videos and then
        # repeated them across beats/scenes. For documentary pacing we want a
        # healthier candidate pool; if video is sparse, we should enrich with
        # images and (optionally) documents.
        #
        # Env override:
        #   AAR_MEDIA_CASCADE_TARGET=8   # desired total candidates before stopping cascade
        # ---------------------------------------------------------------------
        try:
            cascade_target = int(os.getenv("AAR_MEDIA_CASCADE_TARGET", "0"))
        except Exception:
            cascade_target = 0
        if cascade_target <= 0:
            # Default: try to fill up to scene cap (bounded by search guards)
            # NOTE: MIN_RESULTS_TO_STOP_BROADENING is a global early-stop; set target above it so that
            # the cascade can still pull at least some images even when video hits the early-stop.
            cascade_target = max(
                int(min_assets_per_scene or 0),
                # We deliberately aim ABOVE the final scene cap to leave room for mixing media types
                # (video + images) and for ranking to have options.
                int(max_assets_per_scene or 0) * 2,
                int(MIN_RESULTS_TO_STOP_BROADENING) + 1,
            )
        cascade_target = max(2, cascade_target)

        # Stage-specific query lists:
        # - Video can benefit from longer, more specific queries.
        # - Image/doc often needs a simpler anchor query (e.g., just the entity name),
        #   because archive.org image search is much less forgiving to long "scan/engraving" phrasing.
        image_queries = final_queries
        doc_queries = final_queries
        try:
            l2 = (tiered_queries.get("L2") if isinstance(tiered_queries, dict) else []) or []
            l2 = [str(q).strip() for q in l2 if isinstance(q, str) and str(q).strip()]
        except Exception:
            l2 = []

        if l2:
            def _dedupe_keep_order(xs: List[str]) -> List[str]:
                seen = set()
                out = []
                for q in xs:
                    k = str(q).strip().lower()
                    if not k or k in seen:
                        continue
                    seen.add(k)
                    out.append(str(q).strip())
                return out

            # Prepend a couple of simple L2 queries to unlock images/docs
            image_queries = _dedupe_keep_order(l2[:4] + list(final_queries))
            doc_queries = _dedupe_keep_order(l2[:4] + list(final_queries))

        # Stage 2: images (if video stage produced too few to reach target)
        if len(all_results) < cascade_target:
            _run_query_list("image", image_queries)

        # Stage 3: documents/maps (texts) only if still too few
        if len(all_results) < cascade_target:
            _run_query_list("doc", doc_queries)

        # ============================================================================
        # GLOBAL FALLBACK QUERIES (DISABLED by default; prevents off-topic contamination)
        # ============================================================================
        # NOTE: We intentionally do NOT run topic-agnostic fallback queries here.
        # If you enable fallback, it must be episode-anchored.
        enable_global_fallback = str(os.getenv("AAR_ENABLE_GLOBAL_FALLBACK_QUERIES", "0")).strip().lower() in ("1", "true", "yes")
        if enable_global_fallback and GLOBAL_FALLBACK_QUERIES and not all_results:
            print(f"⚠️  AAR: Scene {scene_id} has 0 results - trying GLOBAL FALLBACK QUERIES (enabled)...")
            _run_query_list("video", GLOBAL_FALLBACK_QUERIES[:4])
            if not all_results:
                _run_query_list("image", GLOBAL_FALLBACK_QUERIES[:4])

        # Store diagnostics on self for caller access
        if not hasattr(self, "_scene_diagnostics"):
            self._scene_diagnostics = {}
        self._scene_diagnostics[scene_id] = {
            "queries_attempted": query_diagnostics,
            "reject_reasons_summary": reject_reasons_counter,
            "total_candidates_found": len(all_results),
            "used_global_fallback": bool(enable_global_fallback and GLOBAL_FALLBACK_QUERIES and any(
                (q.get("query") in GLOBAL_FALLBACK_QUERIES) for q in query_diagnostics
            )),
        }

        if not all_results:
            # Still nothing after fallback - log detailed diagnostics
            diag_summary = {
                "scene_id": scene_id,
                "queries_attempted_count": len(query_diagnostics),
                "top_queries": [q.get("query") for q in query_diagnostics[:5]],
                "reject_reasons_summary": reject_reasons_counter,
                "used_global_fallback": bool(enable_global_fallback and GLOBAL_FALLBACK_QUERIES),
            }
            print(f"AAR_SCENE_ZERO_ASSETS {json.dumps(diag_summary, ensure_ascii=False)}")
            return []
        
        # ═══════════════════════════════════════════════════════════════════════════
        # NEW ASSET RANKING SYSTEM
        # ═══════════════════════════════════════════════════════════════════════════
        
        # 1) Deduplicate by archive_item_id
        seen_ids = set()
        unique_results = []
        for asset in all_results:
            item_id = asset["archive_item_id"]
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_results.append(asset)
        
        # 2) Select top assets using new ranking system (hard filters + scoring)
        top_assets = _select_top_assets(
            candidates=unique_results,
            scene=scene,
            max_assets=max_assets_per_scene * 2,  # Get more candidates for fallback logic
            verbose=self.verbose
        )
        
        # 3) Quality floor check - SIMPLIFIED (NO FALLBACK)
        if not top_assets:
            # NO FALLBACK - user request: "žádné fallbacky, žádné chyby"
            # Prostě vrátíme prázdný seznam, pipeline pokračuje
            print(f"⚠️  AAR: Scene {scene.get('scene_id')} - no assets, returning empty list (NO FALLBACK)")
            self._log_query_attempt({
                "event": "no_assets_no_fallback",
                "candidates_count": len(unique_results),
                "reason": "all_filtered_or_low_score"
            })
            return []  # Empty list, pipeline continues
        
        # 4) Telemetry (requirement #6) - log chosen assets with scores
        if top_assets:
            best_asset = top_assets[0]
            best_score = best_asset.get("_rank_score", 0.0)
            top3_scores = [a.get("_rank_score", 0.0) for a in top_assets[:3]]
            
            self._log_query_attempt({
                "event": "assets_selected",
                "candidates_count": len(unique_results),
                "chosen_count": len(top_assets),
                "chosen_id": best_asset.get("archive_item_id"),
                "chosen_title": best_asset.get("title", "")[:60],
                "chosen_score": round(best_score, 3),
                "top3_scores": [round(s, 3) for s in top3_scores],
                "ranking_reason": best_asset.get("_rank_debug", {}),
            })
        
        unique_results = top_assets

        # Episode-level policy: cap unique video sources per episode (videos only).
        # IMPORTANT: For quality, we prefer NOVELTY (avoid repeating the same video across many beats),
        # unless explicitly configured otherwise.
        used = used_video_item_ids if isinstance(used_video_item_ids, set) else set()
        cap = int(max_unique_video_sources_per_episode or 0)
        prefer_reuse = str(os.getenv("AAR_PREFER_REUSE_VIDEO_SOURCES", "0")).strip().lower() in ("1", "true", "yes")
        if cap > 0:
            # Reorder: prefer unused videos first (novelty), keep images always allowed.
            def _episode_key(a: Dict[str, Any]) -> Tuple[int, float]:
                aid = a.get("archive_item_id")
                mt = a.get("media_type")
                score = -float(a.get("_rank_score", 0.0) or 0.0)
                if mt == "video":
                    already_used = bool(aid) and aid in used
                    if prefer_reuse:
                        # Old behavior (opt-in): reuse first
                        return (0 if already_used else 1, score)
                    # Default: novelty first
                    return (0 if not already_used else 1, score)
                # images are not capped and never blocked here
                return (0, score)

            unique_results = sorted(unique_results, key=_episode_key)

            # If cap reached, drop NEW video items (keep already-used videos + all images)
            if len({x for x in used if isinstance(x, str)}) >= cap:
                filtered = []
                for a in unique_results:
                    if a.get("media_type") != "video":
                        filtered.append(a)
                        continue
                    if a.get("archive_item_id") in used:
                        filtered.append(a)
                unique_results = filtered
        
        # Assign pool priority based on rank score
        for i, asset in enumerate(unique_results):
            rank_score = asset.get("_rank_score", 0.0)
            
            if i < 2 and rank_score >= 0.7:
                asset["priority"] = 1
                asset["pool_priority"] = "primary"
            elif i < 5 or rank_score >= 0.5:
                asset["priority"] = 2
                asset["pool_priority"] = "secondary"
            else:
                asset["priority"] = 3
                asset["pool_priority"] = "fallback"
        
        # Limit to max_assets_per_scene
        unique_results = unique_results[:max_assets_per_scene]
        
        # NO FALLBACK - user request: "žádné fallbacky"
        # Prostě použijeme co máme, i když primary_count == 0
        primary_count = sum(1 for a in unique_results if a.get("pool_priority") == "primary")
        if primary_count == 0 and len(unique_results) > 0:
            print(f"⚠️  AAR: Scene {scene.get('scene_id')} has 0 primary assets - promoting best secondary to primary (NO FALLBACK)")
            # Promote best secondary to primary
            for i, asset in enumerate(unique_results[:min(2, len(unique_results))]):
                asset["priority"] = 1
                asset["pool_priority"] = "primary"
        
        # NO FALLBACK - user request: "žádné fallbacky"
        # Pokud máme málo assetů, prostě použijeme co máme
        if len(unique_results) < min_assets_per_scene:
            print(
                f"⚠️  AAR: Scene {scene.get('scene_id')} has only {len(unique_results)} assets "
                f"(wanted {min_assets_per_scene}) - continuing with what we have (NO FALLBACK)"
            )

        # NO PLACEHOLDERS: user requirement is to avoid fallbacks; proceed with what we have.
        # (CompilationBuilder already handles empty assets by skipping scene / using its own internal black-frame fallback.)
        if len(unique_results) < min_assets_per_scene and self.network_error_count > 0:
            print(f"⚠️  AAR: Network/API errors detected; continuing without placeholders (NO FALLBACK)")
        
        return unique_results
    
    def _controlled_fallback_search(self, scene: Optional[Dict[str, Any]] = None, **_kwargs: Any) -> List[Dict[str, Any]]:
        """
        NO FALLBACK: This method is intentionally disabled.
        It still exists (and accepts arbitrary kwargs) to prevent runtime errors from legacy callers.
        """
        if self.verbose:
            sid = scene.get("scene_id") if isinstance(scene, dict) else None
            print(f"⚠️  AAR: _controlled_fallback_search disabled (scene_id={sid})")
        return []
    
    def _generate_placeholder_assets(self, scene: Optional[Dict[str, Any]] = None, **_kwargs: Any) -> List[Dict[str, Any]]:
        """
        NO PLACEHOLDERS: disabled by design.
        Kept only for backward compatibility with legacy call sites; always returns [].
        """
        if self.verbose:
            sid = scene.get("scene_id") if isinstance(scene, dict) else None
            print(f"⚠️  AAR: _generate_placeholder_assets disabled (scene_id={sid})")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# EPISODE-FIRST POOL MODE (Efficiency optimization)
# ═══════════════════════════════════════════════════════════════════════════════
# Instead of searching per-scene (300+ API calls), we:
# 1. Extract TOP queries from ENTIRE episode (10-15 queries)
# 2. Search once, get best materials (5 videos + 10 images)
# 3. Distribute pool across all scenes (0 additional API calls)
#
# RESULT: Same quality, 10-20x faster, 95% fewer API calls
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_episode_queries(
    scenes: List[Dict[str, Any]],
    max_queries: int = 12,
    episode_topic: Optional[str] = None,
) -> List[str]:
    """
    Extract TOP search queries for entire episode.
    
    Strategy:
    1. Collect all anchors (proper nouns, years, places) from all scenes
    2. Dedupe and rank by frequency
    3. Generate archive-friendly queries with object types
    
    Returns:
        List of 10-15 search queries for episode-level pool
    """
    # Collect anchors (entities/places/years) from narration text.
    # IMPORTANT: Do NOT trust FDA keywords/search_queries blindly (they can contain garbage like "burned ruins").
    all_anchors: Dict[str, int] = {}  # anchor -> frequency

    # Connectors allowed INSIDE proper-noun phrases.
    # Keep this tight to avoid generating garbage phrases like "Diana ... and It".
    CONNECTORS = {"of", "de", "da", "di", "la", "le", "du", "del", "von", "van"}
    # Sentence-initial filler words that are NOT entities.
    STOP_SINGLE = {
        "this", "that", "when", "after", "before", "despite", "throughout", "subsequent",
        "however", "therefore", "moreover", "contrary", "primarily", "largely",
        # VERY common sentence starters that should never become "entities" for search queries
        "initial", "early", "later", "eventually", "ultimately", "meanwhile", "then", "next",
        "it", "he", "she", "they", "we", "i",
        "on", "in", "at", "as", "if", "but", "and", "the", "a", "an",
    }
    # Words that often pollute queries and reduce hit-rate / relevance.
    BANNED_QUERY_WORDS = {
        "archival", "archive", "photograph", "photo", "letter", "letters", "document", "documents", "report", "copy",
        "handwriting", "scan", "print", "original", "engraving", "illustration", "painting", "drawing",
        "burned", "ruins", "aftermath", "view", "city", "map", "maps", "decree", "official",
        "monument", "memorial",
        # Generic narrative / meta words that often appear capitalized in summaries and create off-topic queries
        "understanding", "reshaped", "documentary", "examines", "explore", "explores", "future",
    }

    TOPIC_STOPWORDS = {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "from",
        "day", "days", "last", "final", "life", "death", "hours", "hour", "story", "documentary",
        "episode", "part", "chapter", "case",
        "lady",  # too generic for search; we prefer the actual name
        "her", "his", "their",
    }

    # Style / meta words that often appear in user topics ("thriller pacing", "disaster-focused") and must NOT leak into search queries.
    # These are not entities/places/years; including them yields massive off-topic hits.
    TOPIC_STYLE_NOISE = {
        "pacing", "thriller", "dramatic", "cinematic", "tone", "mood", "style",
        "disaster", "focused", "focus",  # covers "disaster-focused" and similar tags
        "true", "crime", "crime-focused",
    }

    def _norm_ws(s: str) -> str:
        return " ".join(str(s or "").split()).strip()

    def _strip_leading_article(p: str) -> str:
        p = _norm_ws(p)
        if p.lower().startswith("the ") and len(p.split()) >= 3:
            return _norm_ws(p.split(" ", 1)[1])
        return p

    def _parse_two_digit_words(s: str) -> Optional[int]:
        """
        Parse a 0-99 number expressed as words/hyphenated words (e.g., 'sixty-six', 'nineteen').
        Best-effort, English only.
        """
        s = _norm_ws(s).lower().replace("-", " ")
        if not s:
            return None
        ones = {
            "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
            "seventeen": 17, "eighteen": 18, "nineteen": 19,
        }
        tens = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
        toks = [t for t in s.split() if t]
        if len(toks) == 1 and toks[0] in ones:
            return ones[toks[0]]
        total = 0
        for t in toks:
            if t in tens:
                total += tens[t]
            elif t in ones:
                total += ones[t]
            else:
                return None
        if 0 <= total <= 99:
            return total
        return None

    def _extract_years_from_text(text: str) -> List[str]:
        """
        Extract years in [1500..2099] from digits OR common spelled-out forms like 'sixteen sixty-six'.
        Returns year strings.
        """
        out: List[str] = []
        t = str(text or "")
        # digit years
        out.extend(re.findall(r"\b(?:15|16|17|18|19|20)\d{2}\b", t))
        # spelled: (fifteen|sixteen|...|twenty) + (two-digit words)
        m = re.findall(r"\b(fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+([a-z-]+(?:\s+[a-z-]+)?)\b", t.lower())
        century_map = {"fifteen": 1500, "sixteen": 1600, "seventeen": 1700, "eighteen": 1800, "nineteen": 1900, "twenty": 2000}
        for c, rest in m:
            base = century_map.get(c)
            if base is None:
                continue
            n = _parse_two_digit_words(rest)
            if n is None:
                continue
            y = base + n
            if 1500 <= y <= 2099:
                out.append(str(y))
        # de-dupe keep order
        seen = set()
        uniq = []
        for y in out:
            ys = str(y).strip()
            if not ys:
                continue
            if ys in seen:
                continue
            seen.add(ys)
            uniq.append(ys)
        return uniq

    def _is_year(s: str) -> bool:
        return bool(re.fullmatch(r"(?:15|16|17|18|19|20)\d{2}", str(s or "").strip()))

    def _tokenize(text: str) -> List[str]:
        # Unicode-aware tokens; keeps hyphen/apostrophe inside words.
        return re.findall(r"[\w]+(?:[-'][\w]+)*", str(text or ""), flags=re.UNICODE)

    def _is_cap_token(tok: str) -> bool:
        if not tok:
            return False
        # Starts with uppercase (Diana, Paris, Ritz, S280)
        if tok[:1].isupper():
            return True
        # Handles tokens like l'Alma (lowercase prefix + apostrophe + Uppercase)
        if "'" in tok:
            after = tok.split("'", 1)[1] if "'" in tok else ""
            if after[:1].isupper():
                return True
        return False

    def _extract_proper_phrases(text: str) -> List[str]:
        toks = _tokenize(text)
        out: List[str] = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if not _is_cap_token(t):
                i += 1
                continue
            phrase = [t]
            j = i + 1
            while j < len(toks):
                nxt = toks[j]
                nl = nxt.lower()
                if nl in CONNECTORS:
                    phrase.append(nxt)
                    j += 1
                    continue
                if _is_cap_token(nxt):
                    phrase.append(nxt)
                    j += 1
                    continue
                break
            p = _norm_ws(" ".join(phrase))
            # Filter obvious fillers ("This", "When", ...)
            if p:
                first = str(phrase[0] or "").strip().lower()
                # Reject phrases that start with discourse/time/location fillers ("On August", "After ...", etc.)
                if first in STOP_SINGLE:
                    pass
                elif len(p.split()) == 1 and p.lower() in STOP_SINGLE:
                    pass
                else:
                    out.append(p)
            i = j
        return out

    def _sanitize_episode_topic_for_queries(topic: Optional[str]) -> str:
        """
        Topic can be a long multi-sentence brief (often includes style notes).
        For search, we only want the MAIN subject entity phrase, not verbs/adjectives.
        """
        t = _norm_ws(topic or "")
        if not t:
            return ""
        # Drop common prefixes
        t = re.sub(r"^(topic|theme)\s*:\s*", "", t, flags=re.IGNORECASE).strip()
        # Prefer the first sentence (usually the actual subject line)
        if "." in t:
            head = t.split(".", 1)[0].strip()
            if head:
                t = head
        # Best signal: take the first multi-word proper noun phrase (e.g., "The Great Fire of London")
        # NOTE: _extract_proper_phrases intentionally rejects phrases starting with filler words like "The".
        # For topic titles this is common, so we pre-strip the leading article for extraction.
        t2 = re.sub(r"^(?:the|a|an)\s+", "", t, flags=re.IGNORECASE).strip()
        phrases = _extract_proper_phrases(t2 or t)
        for p in phrases:
            if len(str(p).split()) >= 3:
                return _strip_leading_article(p)
        for p in phrases:
            if len(str(p).split()) >= 2:
                return _strip_leading_article(p)
        # Fallback: trim at comma (often style tags after comma)
        if "," in t:
            t = t.split(",", 1)[0].strip()
        return _strip_leading_article(t)

    def _add_anchor(a: str, weight: int = 1) -> None:
        a = _strip_leading_article(a)
        if not a:
            return
        # Avoid very long phrases (usually noisy)
        if len(a.split()) > 7:
            return
        al = a.lower()
        if len(a.split()) == 1 and al in STOP_SINGLE:
            return
        # Filter style/meta noise that should not become a search anchor
        # (handles tokens like "Disaster-focused", "thriller pacing", etc.)
        if any(n in al.replace("-", " ").split() for n in TOPIC_STYLE_NOISE):
            # If anchor is a real entity + noise word mix, we still drop it because it is too ambiguous.
            return
        # Avoid polluted phrases that include banned query words.
        if any(w in al.split() for w in BANNED_QUERY_WORDS):
            return
        all_anchors[a] = all_anchors.get(a, 0) + int(weight or 1)

    # 1) Extract from narration_summary (primary signal)
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        summary = str(scene.get("narration_summary") or "")
        for p in _extract_proper_phrases(summary):
            _add_anchor(p, weight=3)  # narration has highest weight
        for y in _extract_years_from_text(summary):
            _add_anchor(str(y), weight=2)

        # 2) Extract from keywords, but ONLY by pulling proper-noun phrases out of them (keywords are often noisy)
        for kw in (scene.get("keywords") or []):
            kw_str = str(kw or "").strip()
            if not kw_str:
                continue
            for p in _extract_proper_phrases(kw_str):
                _add_anchor(p, weight=1)
            for y in _extract_years_from_text(kw_str):
                _add_anchor(str(y), weight=1)

    # 3) Episode topic: treat as text, not as a raw query string
    # IMPORTANT: sanitize long brief/style notes; keep only main subject for search anchors.
    topic = _sanitize_episode_topic_for_queries(episode_topic)
    if topic:
        # Add any proper noun phrases (if topic is Title Case)
        for p in _extract_proper_phrases(topic):
            _add_anchor(p, weight=10)
        # Also add meaningful lowercase tokens (if topic is lower-case)
        topic_tokens = [
            t
            for t in re.findall(r"[a-z0-9]{3,}", topic.lower())
            if t not in TOPIC_STOPWORDS
        ]
        for t in topic_tokens[:4]:
            _add_anchor(t, weight=8)
        for y in _extract_years_from_text(topic):
            _add_anchor(str(y), weight=6)

    # Rank anchors by frequency, prefer multi-word entities over single tokens, keep years lower priority.
    def _anchor_sort_key(item: Tuple[str, int]) -> Tuple[int, int, int, int]:
        a, freq = item
        words = len(str(a).split())
        is_year = 1 if _is_year(a) else 0  # years later
        return (-int(freq or 0), is_year, -min(words, 4), -len(str(a)))

    ranked = sorted(all_anchors.items(), key=_anchor_sort_key)
    ranked_anchors = [a for a, _ in ranked if str(a or "").strip()]

    # Emergency fallback: if extraction failed, fallback to simple tokens.
    if not ranked_anchors:
        ranked_anchors = ["historical", "archive"]

    # Build a compact, high-hit query set.
    years = [a for a in ranked_anchors if _is_year(a)]
    entities = [a for a in ranked_anchors if not _is_year(a)]

    def _trim_query(q: str, max_words: int = 6) -> str:
        toks = [t for t in _norm_ws(q).split() if t]
        return " ".join(toks[:max_words]).strip()

    queries: List[str] = []
    
    # ════════════════════════════════════════════════════════════════════════════
    # STABILITY FIX: Never use single generic words as queries!
    # Single words like "Paris", "Princess", "Wales" return 28000+ irrelevant results.
    # Only use COMBINED queries (2+ words) or known multi-word entities.
    # ════════════════════════════════════════════════════════════════════════════
    
    # Generic single words that should NEVER be used alone
    GENERIC_SINGLE_WORDS = {
        "paris", "london", "berlin", "moscow", "rome", "vienna", "tokyo", "washington",
        "princess", "prince", "king", "queen", "emperor", "general", "president", "chancellor",
        "wales", "england", "france", "germany", "russia", "italy", "spain", "austria",
        "war", "battle", "death", "life", "day", "night", "final", "last", "first",
        "dodi", "fayed", "diana",  # Single names are too ambiguous
    }
    
    def _is_good_query(q: str) -> bool:
        """Check if query is specific enough (not a single generic word)."""
        words = q.lower().split()
        if len(words) == 1:
            return words[0] not in GENERIC_SINGLE_WORDS
        return True  # Multi-word queries are generally OK
    
    mw_entities = [e for e in entities if isinstance(e, str) and len(e.split()) >= 2]
    top_year = years[0] if years else None

    # Prefer the sanitized topic phrase first (most specific anchor)
    if topic and len(topic.split()) >= 2:
        queries.append(_trim_query(topic))

    # Add multi-word entities (specific enough)
    for a in mw_entities[:6]:
        queries.append(_trim_query(a))

    # Add year-disambiguated queries (huge precision boost; prevents modern/irrelevant matches)
    if top_year:
        if topic and len(topic.split()) >= 2:
            queries.append(_trim_query(f"{topic} {top_year}"))
        if mw_entities:
            queries.append(_trim_query(f"{mw_entities[0]} {top_year}"))
        if len(mw_entities) >= 2:
            queries.append(_trim_query(f"{mw_entities[0]} {mw_entities[1]} {top_year}"))

    # If we still don't have enough, add combined multi-word entities (avoid 1-word+1-word garbage like 'London Pudding')
    if len(mw_entities) >= 2:
        queries.append(_trim_query(f"{mw_entities[0]} {mw_entities[1]}"))
    
    # Special handling for known patterns
    has_diana = any(str(a).lower() == "diana" for a in entities) or any(str(a).lower() == "diana" for a in ranked_anchors)
    has_wales = any("wales" in str(a).lower().split() for a in entities) or any("wales" in str(a).lower().split() for a in ranked_anchors)
    if has_diana:
        queries.append("Princess Diana")
        queries.append("Princess Diana 1997")
        if has_wales:
            queries.append("Diana Princess of Wales")

    # Dedupe (keep order)
    seen = set()
    uniq: List[str] = []
    for q in queries:
        qn = _norm_ws(q)
        if not qn:
            continue
        key = qn.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(qn)

    # Final quality gates for queries (generic, cross-topic):
    # - Drop acronym-split junk like "D N" (too ambiguous)
    # - Drop pure temporal queries like "Sunday September" (causes massive off-topic results)
    TEMPORAL_WORDS = {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
    }

    def _is_bad_query(q: str) -> bool:
        toks = [t for t in _norm_ws(q).split() if t]
        # incomplete "tail" queries (often come from copying narrative sentences)
        if toks:
            tail = toks[-1].lower()
            if tail in {"for", "the", "and", "or", "to", "of", "in", "on", "at", "with", "from"}:
                return True
        
        # NEW: Ban overly broad geographic/country queries that return irrelevant results
        OVER_BROAD_QUERIES = {
            "united states", "usa", "america", "united kingdom", "uk", "england", "france", 
            "germany", "russia", "china", "japan", "canada", "australia",
            "europe", "asia", "africa", "north america", "south america",
        }
        q_lower = q.lower().strip()
        if q_lower in OVER_BROAD_QUERIES:
            return True
        
        # NEW: Ban ambiguous geographic names without context (e.g., "Green River" returns geography, not crime)
        # Only ban if it's EXACTLY that phrase (not "Green River Killer")
        AMBIGUOUS_GEO = {
            "green river",  # Ban standalone (geography), but "green river killer" is OK
            "pearl harbor", "pearl", "tower bridge", "brooklyn bridge",
        }
        if q_lower in AMBIGUOUS_GEO:
            return True
        
        if len(toks) >= 2:
            # acronym-split: all tokens are 1 char
            if all(len(t) == 1 for t in toks):
                return True
            # majority 1-char tokens is also bad (e.g., "D N A")
            if sum(1 for t in toks if len(t) == 1) >= max(2, (len(toks) + 1) // 2):
                return True
        # temporal-only (no year, no real entity)
        low = [t.lower() for t in toks]
        has_year = any(re.fullmatch(r"(?:15|16|17|18|19|20)\d{2}", t) for t in low)
        if not has_year and low and all(t in TEMPORAL_WORDS for t in low):
            return True
        return False

    uniq = [q for q in uniq if not _is_bad_query(q)]

    # Avoid highly ambiguous single-token queries when we already have a precise phrase.
    uniq_l = {q.lower() for q in uniq}
    if ("princess diana" in uniq_l) or ("diana princess of wales" in uniq_l):
        uniq = [q for q in uniq if q.lower() not in ("diana", "lady diana")]

    # Add exclusion terms to prevent false positives for ambiguous names
    # This dramatically improves precision for names that match unrelated entities.
    EXCLUSION_RULES = {
        "diana": "-krall -creek -mythology -goddess -wonder -twilight -ross -durbin -rigg",
        "princess diana": "-krall -creek -mythology -goddess",
        "napoleon": "-dynamite -solo -complex -cake",
        "hitler": "-parody -comedy -meme -game",
        "churchill": "-insurance -downs -living",
    }
    
    def _add_exclusions(q: str) -> str:
        ql = q.lower()
        for trigger, exclusions in EXCLUSION_RULES.items():
            if trigger in ql:
                # Don't add if already has exclusions
                if " -" not in q:
                    return f"{q} {exclusions}"
        return q
    
    uniq = [_add_exclusions(q) for q in uniq]

    out_queries = uniq[:max_queries]

    # #region agent log (hypothesis A/B)
    try:
        import time as _time
        import json as _json

        def _safe(s: Any, n: int = 120) -> str:
            ss = str(s or "").replace("\n", " ").replace("\r", " ")
            ss = " ".join(ss.split()).strip()
            return ss[:n]

        # Detect suspicious "profile marker" phrases that can leak into narration_summary and become anchors.
        SUSPECT_PATTERNS = ("initial", "disaster-focused", "disaster focused", "topic:", "profile:")
        suspect_anchors = []
        for a in (ranked_anchors or [])[:60]:
            al = str(a or "").lower()
            if any(p in al for p in SUSPECT_PATTERNS):
                suspect_anchors.append(_safe(a, 80))
                if len(suspect_anchors) >= 8:
                    break

        # Sample the first few narration_summary strings (truncated) WITHOUT dumping full text.
        summaries = []
        for sc in (scenes or [])[:3]:
            if not isinstance(sc, dict):
                continue
            summaries.append(_safe(sc.get("narration_summary") or "", 90))

        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "A",
                "location": "backend/archive_asset_resolver.py:_extract_episode_queries",
                "message": "Episode query extraction snapshot",
                "data": {
                    "scenes_count": len(scenes) if isinstance(scenes, list) else None,
                    "episode_topic": _safe(episode_topic, 120),
                    "narration_summary_samples": summaries,
                    "anchors_total": len(ranked_anchors) if isinstance(ranked_anchors, list) else None,
                    "anchors_head": [ _safe(a, 60) for a in (ranked_anchors or [])[:10] ],
                    "suspect_anchors": suspect_anchors,
                    "queries_out": out_queries,
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion

    return out_queries


def resolve_episode_pool(
    shot_plan: Dict[str, Any],
    cache_dir: str,
    max_videos: int = 8,      # STABILITY: More videos for better variety and video priority
    max_images: int = 15,     # Reduced to balance ratio - videos have priority
    episode_topic: Optional[str] = None,
    verbose: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    EPISODE-FIRST MODE: Resolve materials for entire episode at once.
    
    Instead of per-scene resolution (300+ API calls), we:
    1. Extract TOP 12 queries from entire episode
    2. Search once (12 API calls)
    3. Select TOP 5 videos + TOP 10 images = EPISODE POOL
    
    EFFICIENCY:
    - 12 API calls instead of 300+
    - 15 downloads instead of 100+
    - Same output quality
    
    Args:
        shot_plan: Shot plan from FDA
        cache_dir: Cache directory for search results
        max_videos: Max unique video sources (default 5)
        max_images: Max unique image sources (default 10)
        episode_topic: Main episode topic for relevance
        verbose: Enable debug logging
        progress_callback: Optional progress callback
    
    Returns:
        {
            "videos": [...],  # List of video assets
            "images": [...],  # List of image assets
            "queries_used": [...],  # Queries that were executed
            "stats": {...}  # Pool statistics
        }
    """
    print(f"🎯 AAR: EPISODE-FIRST POOL MODE enabled")
    print(f"   Target: {max_videos} videos + {max_images} images for entire episode")
    
    # Extract scenes
    scenes = []
    if isinstance(shot_plan, dict) and isinstance(shot_plan.get("scenes"), list):
        scenes = shot_plan.get("scenes") or []
    elif isinstance(shot_plan, dict) and isinstance(shot_plan.get("shot_plan"), dict):
        scenes = shot_plan["shot_plan"].get("scenes") or []
    
    if not scenes:
        print("⚠️  AAR: No scenes in shot_plan, cannot build episode pool")
        return {"videos": [], "images": [], "queries_used": [], "stats": {"error": "no_scenes"}}
    
    # Collect stable "global" search queries from scenes.
    # IMPORTANT: only use the FIRST query per scene (this is where we prepend user_search_queries overrides).
    # Do NOT pull arbitrary per-scene queries here; those can be noisy and create off-topic episode pool results.
    forced_queries: List[str] = []
    try:
        from collections import Counter
        counts = Counter()

        def _norm_q(x: Any) -> str:
            if isinstance(x, dict):
                x = x.get("query")
            q = " ".join(str(x or "").split()).strip()
            if len(q) > 160:
                q = q[:160].strip()
            return q

        for sc in scenes:
            if not isinstance(sc, dict):
                continue
            sq = sc.get("search_queries")
            sq = sq if isinstance(sq, list) else []
            if not sq:
                continue
            q0 = _norm_q(sq[0])
            if not q0:
                continue
            counts[q0.lower()] += 1

        # Keep only queries that appear in most scenes (user overrides are prepended everywhere)
        min_freq = max(2, int(round(len(scenes) * 0.6)))
        forced = []
        for k, c in counts.items():
            if c >= min_freq:
                forced.append(k)

        # Extra guard: avoid stylistic/meta garbage in forced queries (local list; do NOT depend on inner-function locals)
        _NOISY_TOKENS = {
            # style tags
            "pacing", "thriller", "dramatic", "cinematic", "tone", "mood", "style",
            "disaster", "focused", "focus", "crime",
            # common query pollution
            "archival", "archive", "photograph", "photo", "letter", "letters", "document", "documents", "report",
            "handwriting", "scan", "print", "original", "engraving", "illustration", "painting", "drawing",
            "burned", "ruins", "aftermath", "view", "map", "maps",
            # narrative verbs / glue words often leaked from topic briefs
            "reshaped", "explore", "explores", "examines", "evaded", "capture", "captured",
        }

        def _looks_noisy(q: str) -> bool:
            parts = str(q or "").lower().replace("-", " ").split()
            return any(w in _NOISY_TOKENS for w in parts)

        forced_queries = [q for q in forced if not _looks_noisy(q)][:2]
    except Exception:
        forced_queries = []

    # Extract episode-level queries (heuristic)
    episode_queries = _extract_episode_queries(scenes, max_queries=12, episode_topic=episode_topic)
    # Merge forced queries first (high priority) + extracted queries
    try:
        seen2 = set()
        merged: List[str] = []
        for q in (forced_queries + episode_queries):
            qq = " ".join(str(q or "").split()).strip()
            if not qq:
                continue
            k = qq.lower()
            if k in seen2:
                continue
            seen2.add(k)
            merged.append(qq)
        episode_queries = merged[:12]
    except Exception:
        pass

    print(f"📝 AAR: Episode queries: {episode_queries}")

    # #region agent log (hypothesis A)
    try:
        import time as _time
        import json as _json
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "post-fix",
                "hypothesisId": "A",
                "location": "backend/archive_asset_resolver.py:resolve_episode_pool",
                "message": "Episode pool queries (forced + extracted)",
                "data": {
                    "forced_queries": forced_queries,
                    "final_queries": episode_queries,
                    "episode_topic_in": str(episode_topic or "")[:180],
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion
    
    if progress_callback:
        try:
            progress_callback({
                "phase": "episode_pool",
                "message": f"Hledám materiály pro celou epizodu ({len(episode_queries)} queries)",
                "queries": episode_queries,
            })
        except Exception:
            pass
    
    # Create resolver (reuse existing cache)
    resolver = ArchiveAssetResolver(cache_dir, throttle_delay_sec=0.3, verbose=verbose)
    
    # Search for videos
    all_video_candidates = []
    for i, query in enumerate(episode_queries):
        if progress_callback:
            try:
                progress_callback({
                    "phase": "episode_pool_search",
                    "message": f"Hledám videa: {query[:40]}...",
                    "query_index": i + 1,
                    "total_queries": len(episode_queries),
                })
            except Exception:
                pass
        
        results = resolver.search_multi_source(query, max_results=10)
        for r in results:
            r["_source_query"] = query
        all_video_candidates.extend(results)
        
        if verbose:
            print(f"   Video query '{query[:40]}': {len(results)} results")
    
    # Search for images (multi-source: Archive + Wikimedia)
    all_image_candidates = []
    for i, query in enumerate(episode_queries[:8]):  # Fewer image queries
        results = resolver.search_images_multi_source(query, max_results=10)
        for r in results:
            r["_source_query"] = query
            r["media_type"] = "image"
        all_image_candidates.extend(results)
        
        if verbose:
            print(f"   Image query '{query[:40]}': {len(results)} results")
    
    # ════════════════════════════════════════════════════════════════════════════
    # LLM VISUAL DEDUPLICATION + QUALITY RANKING (replaces script dedupe/scoring)
    # Uses Visual Assistant to intelligently group duplicates and rank by quality
    # ════════════════════════════════════════════════════════════════════════════
    print(f"🎨 AAR: LLM Visual Deduplication + Quality Ranking...")
    
    # Get API key for Visual Assistant
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if openrouter_key:
        api_key = openrouter_key
        provider = "openrouter"
        model = "openai/gpt-4o"
    elif openai_key:
        api_key = openai_key
        provider = "openai"
        model = "gpt-4o"
    else:
        print(f"⚠️  AAR: No API key for Visual Assistant - falling back to script deduplication")
        api_key = None
    
    if api_key and all_video_candidates:
        try:
            from visual_assistant import VisualAssistant
            
            va = VisualAssistant(
                api_key=api_key,
                model=model,
                temperature=0.15,
                verbose=verbose,
                provider=provider
            )
            
            # Analyze video pool (HLAVNÍ METODA: deduplicate + rank)
            unique_videos = va.deduplicate_and_rank_pool_candidates(
                candidates=all_video_candidates,
                episode_topic=episode_topic or "documentary footage",
                max_analyze=30
            )
            
            print(f"   📹 Videos: {len(all_video_candidates)} → {len(unique_videos)} unique (LLM dedupe + ranking)")
            
            # Analyze image pool (HLAVNÍ METODA: deduplicate + rank)
            unique_images = va.deduplicate_and_rank_pool_candidates(
                candidates=all_image_candidates,
                episode_topic=episode_topic or "documentary footage",
                max_analyze=30
            )
            
            print(f"   🖼️  Images: {len(all_image_candidates)} → {len(unique_images)} unique (LLM dedupe + ranking)")
            
        except Exception as e:
            print(f"⚠️  AAR: Visual Assistant failed: {e}")
            print(f"   Falling back to script deduplication...")
            # Fallback to script dedupe
            seen_video_ids = set()
            unique_videos = []
            for v in all_video_candidates:
                vid = v.get("archive_item_id", "")
                if vid and vid not in seen_video_ids:
                    seen_video_ids.add(vid)
                    unique_videos.append(v)
            
            seen_image_ids = set()
            unique_images = []
            for img in all_image_candidates:
                iid = img.get("archive_item_id", "")
                if iid and iid not in seen_image_ids:
                    seen_image_ids.add(iid)
                    unique_images.append(img)
    else:
        # No API key - use script dedupe as fallback
        print(f"   Using script deduplication (no Visual Assistant)")
        seen_video_ids = set()
        unique_videos = []
        for v in all_video_candidates:
            vid = v.get("archive_item_id", "")
            if vid and vid not in seen_video_ids:
                seen_video_ids.add(vid)
                unique_videos.append(v)
        
        seen_image_ids = set()
        unique_images = []
        for img in all_image_candidates:
            iid = img.get("archive_item_id", "")
            if iid and iid not in seen_image_ids:
                seen_image_ids.add(iid)
                unique_images.append(img)
    
    # ════════════════════════════════════════════════════════════════════════════
    # QUALITY-BASED SELECTION (uses LLM scores if available, else script scoring)
    # Priority: QUALITY > QUANTITY, but NEVER hide results from the user.
    # - We always keep RAW candidates + UNIQUE ranked lists for transparency.
    # - We never "black-box" fail just because thresholding produced 0 results.
    # ════════════════════════════════════════════════════════════════════════════
    MIN_QUALITY_THRESHOLD = 0.70  # Soft threshold for llm_quality_score (not sufficient alone for topic relevance)
    MIN_TOPIC_REL_VIDEO = 0.25    # Minimum topic_relevance to include in selected pool (videos)
    MIN_TOPIC_REL_IMAGE = 0.60    # Minimum topic_relevance to include in selected pool (images) - raised to filter off-topic results
    
    # Check if we have LLM scores
    has_llm_scores = any(v.get('llm_quality_score') is not None for v in unique_videos)
    
    def _topic_rel(x: Dict[str, Any]) -> float:
        try:
            la = x.get("llm_analysis") if isinstance(x, dict) else None
            la = la if isinstance(la, dict) else {}
            tr = la.get("topic_relevance")
            return float(tr) if isinstance(tr, (int, float)) else 0.0
        except Exception:
            return 0.0

    if has_llm_scores:
        print(f"   Using LLM scores for selection (quality soft threshold: {MIN_QUALITY_THRESHOLD}, topic thresholds: v>={MIN_TOPIC_REL_VIDEO}, i>={MIN_TOPIC_REL_IMAGE})")

        # First: enforce topic relevance (prevents selecting obviously off-topic items)
        rel_videos = [v for v in unique_videos if _topic_rel(v) >= MIN_TOPIC_REL_VIDEO]
        rel_images = [i for i in unique_images if _topic_rel(i) >= MIN_TOPIC_REL_IMAGE]

        print(f"   🎯 Topic-relevant videos: {len(rel_videos)}/{len(unique_videos)} (>= {MIN_TOPIC_REL_VIDEO})")
        print(f"   🎯 Topic-relevant images: {len(rel_images)}/{len(unique_images)} (>= {MIN_TOPIC_REL_IMAGE})")

        # Second: within relevant set, prefer high llm_quality_score
        quality_videos = [v for v in rel_videos if float(v.get('llm_quality_score', 0) or 0) >= MIN_QUALITY_THRESHOLD]
        quality_images = [i for i in rel_images if float(i.get('llm_quality_score', 0) or 0) >= MIN_QUALITY_THRESHOLD]

        print(f"   📹 Relevant videos above quality: {len(quality_videos)}/{len(rel_videos)} (>= {MIN_QUALITY_THRESHOLD})")
        print(f"   🖼️  Relevant images above quality: {len(quality_images)}/{len(rel_images)} (>= {MIN_QUALITY_THRESHOLD})")

        # Selection policy:
        # - Prefer (relevant ∩ high-quality), else fallback to relevant (may still be usable).
        # - If NO relevant videos exist, allow pool_videos to be empty (images-only compilation is possible).
        pool_videos = (quality_videos or rel_videos)[:max_videos]
        pool_images = (quality_images or rel_images)[:max_images]

        # If images are empty but videos exist, fallback to at least some images to avoid hard-fail when only images are needed.
        if not pool_images and unique_images:
            pool_images = unique_images[:max_images]
    else:
        print(f"   Using script scoring (fallback)")
        # Script scoring as fallback
        def _score_video_for_pool(v: Dict[str, Any]) -> float:
            score = 0.0
            duration = v.get("duration_sec", 0) or 0
            if duration > 0:
                score += min(10.0, math.log(duration + 1) * 2)
            downloads = v.get("downloads", 0) or 0
            if downloads > 0:
                score += min(5.0, math.log(downloads + 1) * 0.5)
            if episode_topic:
                title = str(v.get("title", "")).lower()
                if episode_topic.lower() in title:
                    score += 5.0
            return score
        
        def _score_image_for_pool(img: Dict[str, Any]) -> float:
            score = 0.0
            downloads = img.get("downloads", 0) or 0
            if downloads > 0:
                score += min(5.0, math.log(downloads + 1) * 0.5)
            if episode_topic:
                title = str(img.get("title", "")).lower()
                if episode_topic.lower() in title:
                    score += 5.0
            return score
        
        unique_videos.sort(key=_score_video_for_pool, reverse=True)
        unique_images.sort(key=_score_image_for_pool, reverse=True)
        
        pool_videos = unique_videos[:max_videos]
        pool_images = unique_images[:max_images]

    # De-dupe selected pool by archive_item_id to avoid duplicates across queries/providers
    def _dedupe_pool(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out = []
        for x in items or []:
            if not isinstance(x, dict):
                continue
            aid = str(x.get("archive_item_id") or "").strip()
            if not aid:
                continue
            if aid in seen:
                continue
            seen.add(aid)
            out.append(x)
        return out

    pool_videos = _dedupe_pool(pool_videos)
    pool_images = _dedupe_pool(pool_images)
    
    # Mark pool priority
    for i, v in enumerate(pool_videos):
        v["pool_priority"] = "primary" if i < 2 else "secondary"
        v["pool_index"] = i
        v["media_type"] = "video"
    
    for i, img in enumerate(pool_images):
        img["pool_priority"] = "primary" if i < 3 else "secondary"
        img["pool_index"] = i
        img["media_type"] = "image"
    
    stats = {
        "total_video_candidates": len(all_video_candidates),
        "total_image_candidates": len(all_image_candidates),
        "unique_videos_found": len(unique_videos),
        "unique_images_found": len(unique_images),
        "pool_videos": len(pool_videos),
        "pool_images": len(pool_images),
        "queries_executed": len(episode_queries),
        "total_scenes": len(scenes),
        "has_llm_scores": bool(has_llm_scores),
        "quality_threshold": float(MIN_QUALITY_THRESHOLD),
        "videos_above_threshold": int(sum(1 for v in unique_videos if float(v.get("llm_quality_score", 0) or 0) >= MIN_QUALITY_THRESHOLD)) if has_llm_scores else None,
        "images_above_threshold": int(sum(1 for i in unique_images if float(i.get("llm_quality_score", 0) or 0) >= MIN_QUALITY_THRESHOLD)) if has_llm_scores else None,
    }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HARD FAIL: If pool is completely empty, raise error instead of silent continue
    # ═══════════════════════════════════════════════════════════════════════════
    if not pool_videos and not pool_images:
        error_msg = (
            f"EPISODE POOL EMPTY: Found 0 videos and 0 images after searching {len(episode_queries)} queries. "
            f"This is a critical failure - cannot create video without visuals. "
            f"Queries attempted: {episode_queries[:5]}... "
            f"Check: 1) Archive.org availability, 2) Wikimedia search, 3) Query relevance."
        )
        print(f"❌ AAR: {error_msg}")
        raise AARHardFail(
            "EPISODE_POOL_EMPTY",
            error_msg,
            details={
                "queries_attempted": episode_queries,
                "video_candidates_raw": len(all_video_candidates),
                "image_candidates_raw": len(all_image_candidates),
                "unique_videos_after_filter": len(unique_videos),
                "unique_images_after_filter": len(unique_images),
            }
        )
    
    print(f"✅ AAR: Episode pool created:")
    print(f"   📹 Videos: {len(pool_videos)} (from {len(unique_videos)} unique)")
    print(f"   🖼️  Images: {len(pool_images)} (from {len(unique_images)} unique)")
    print(f"   🔍 Queries: {len(episode_queries)} (instead of ~{len(scenes) * 5} per-scene)")
    
    def _slim_asset(a: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(a, dict):
            return {}
        aid = str(a.get("archive_item_id") or "").strip()
        thumb = a.get("thumbnail_url")
        if (not thumb) and aid:
            try:
                src = "archive_org"
                raw = aid
                if ":" in aid:
                    p, r = aid.split(":", 1)
                    p = p.strip().lower()
                    raw = r.strip()
                    if p in ("archive", "archiveorg", "archive_org", "archive.org"):
                        src = "archive_org"
                    elif p in ("wikimedia", "commons", "wikimedia_commons"):
                        src = "wikimedia"
                    elif p in ("europeana",):
                        src = "europeana"
                    else:
                        src = p or "other"
                # Only safe auto-thumb we can guarantee without extra API calls is archive.org service thumb.
                if src == "archive_org" and raw:
                    thumb = f"https://archive.org/services/img/{raw}"
            except Exception:
                thumb = a.get("thumbnail_url")
        # Keep only fields needed for UI transparency
        out = {
            "archive_item_id": aid or a.get("archive_item_id"),
            "media_type": a.get("media_type") or a.get("type"),
            "title": a.get("title"),
            "description": (str(a.get("description") or "")[:400] if a.get("description") is not None else ""),
            "thumbnail_url": thumb,
            "asset_url": a.get("asset_url"),
            "downloads": a.get("downloads"),
            "duration_sec": a.get("duration_sec"),
            "_source": a.get("_source") or a.get("source"),
            "_source_query": a.get("_source_query"),
            "llm_quality_score": a.get("llm_quality_score"),
            "llm_analysis": a.get("llm_analysis"),
        }
        return {k: v for k, v in out.items() if v is not None}

    return {
        # Selected pool (used for distribution)
        "videos": pool_videos,
        "images": pool_images,
        "queries_used": episode_queries,
        "stats": stats,
        # Transparency payloads (for UI “show everything”)
        "raw_candidates": {
            "videos": [_slim_asset(x) for x in all_video_candidates if isinstance(x, dict)],
            "images": [_slim_asset(x) for x in all_image_candidates if isinstance(x, dict)],
        },
        "unique_ranked": {
            "videos": [_slim_asset(x) for x in unique_videos if isinstance(x, dict)],
            "images": [_slim_asset(x) for x in unique_images if isinstance(x, dict)],
        },
        "selected_ranked": {
            "videos": [_slim_asset(x) for x in pool_videos if isinstance(x, dict)],
            "images": [_slim_asset(x) for x in pool_images if isinstance(x, dict)],
        },
    }


def _distribute_pool_to_scenes(
    pool: Dict[str, Any],
    scenes: List[Dict[str, Any]],
    narration_blocks: List[Dict[str, Any]],
    block_index: Dict[str, int],
    block_text: Dict[str, str],
    audio_durations_by_block: Dict[str, float],
) -> List[Dict[str, Any]]:
    """
    Distribute episode pool across scenes.
    
    Strategy:
    - Video rotation: each video covers ~N scenes (where N = total_scenes / pool_videos)
    - Image cycling: images rotate through scenes
    - Each beat gets assigned candidates from current rotation
    
    Returns:
        List of scene dicts with visual_beats populated from pool
    """
    pool_videos = pool.get("videos") or []
    pool_images = pool.get("images") or []
    
    if not pool_videos and not pool_images:
        print("⚠️  AAR: Empty pool, cannot distribute")
        return []
    
    total_scenes = len(scenes)
    scenes_per_video = max(1, total_scenes // max(1, len(pool_videos))) if pool_videos else total_scenes
    
    manifest_scenes = []
    
    for scene_idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", f"sc_{scene_idx:04d}")
        block_ids = scene.get("narration_block_ids", [])
        if not isinstance(block_ids, list):
            block_ids = []
        
        shot_strategy = scene.get("shot_strategy") or {}
        shot_types = shot_strategy.get("shot_types") or []
        scene_summary = str(scene.get("narration_summary") or "")
        scene_keywords = scene.get("keywords") or []
        
        # Determine which pool assets to use for this scene
        # Video rotation: cycle through pool videos
        video_idx = scene_idx % len(pool_videos) if pool_videos else -1
        # Also include next video for variety
        video_idx_alt = (scene_idx + 1) % len(pool_videos) if pool_videos else -1
        
        # Image rotation: cycle through pool images
        image_idx = scene_idx % len(pool_images) if pool_images else -1
        image_idx_alt = (scene_idx + 1) % len(pool_images) if pool_images else -1
        image_idx_alt2 = (scene_idx + 2) % len(pool_images) if pool_images else -1
        
        # Build scene assets from pool
        scene_assets = []
        
        # Primary: current rotation video
        if video_idx >= 0 and video_idx < len(pool_videos):
            scene_assets.append(pool_videos[video_idx].copy())
        # Secondary: alternate video
        if video_idx_alt >= 0 and video_idx_alt < len(pool_videos) and video_idx_alt != video_idx:
            scene_assets.append(pool_videos[video_idx_alt].copy())
        
        # Add images
        for img_i in [image_idx, image_idx_alt, image_idx_alt2]:
            if img_i >= 0 and img_i < len(pool_images):
                img_copy = pool_images[img_i].copy()
                if img_copy not in scene_assets:
                    scene_assets.append(img_copy)
        
        # Build visual beats for each narration block
        # ═══════════════════════════════════════════════════════════════════════════
        # VIDEO PRIORITY: Videos are PRIMARY, images are SECONDARY (fallback)
        # Visual Assistant (LLM) can override, but videos are preferred by default
        # VARIETY: Each beat gets DIFFERENT assets from the pool (rotation)
        # ═══════════════════════════════════════════════════════════════════════════
        beats = []
        
        # Separate pools by media type for rotation
        all_videos = pool_videos.copy()
        all_images = pool_images.copy()
        
        for beat_idx, bid in enumerate(block_ids):
            bid = str(bid or "").strip()
            if not bid:
                continue
            
            txt = block_text.get(bid) or ""
            dur = audio_durations_by_block.get(bid)
            
            # VARIETY: Rotate through pool for each beat
            global_beat_idx = scene_idx * 100 + beat_idx  # Unique index across all scenes
            
            beat_candidates = []
            
            # ═══════════════════════════════════════════════════════════════════════
            # PRIORITY ORDER: Video first, then image
            # ═══════════════════════════════════════════════════════════════════════
            
            # Candidate 1 (PRIMARY): Video - HIGHEST PRIORITY
            if all_videos:
                video_idx = global_beat_idx % len(all_videos)
                video_asset = all_videos[video_idx].copy()
                video_asset["_assigned_via"] = "episode_pool_video"
                video_asset["pool_priority"] = "primary"  # VIDEO = PRIMARY
                video_asset["media_type"] = "video"
                video_asset["_priority_rank"] = 1  # Explicit rank for sorting
                beat_candidates.append(video_asset)
            
            # Candidate 2 (SECONDARY): Image - USE ONLY IF NO VIDEO or LLM prefers
            if all_images:
                image_idx = global_beat_idx % len(all_images)
                image_asset = all_images[image_idx].copy()
                image_asset["_assigned_via"] = "episode_pool_image"
                image_asset["pool_priority"] = "secondary"  # IMAGE = SECONDARY (fallback)
                image_asset["media_type"] = "image"
                image_asset["_priority_rank"] = 2  # Lower priority than video
                beat_candidates.append(image_asset)
            
            # Candidate 3 (TERTIARY): Alternative video for variety
            if all_videos and len(all_videos) > 1:
                video_idx_alt = (global_beat_idx + 1) % len(all_videos)
                if video_idx_alt != video_idx:
                    video_alt = all_videos[video_idx_alt].copy()
                    video_alt["_assigned_via"] = "episode_pool_video_alt"
                    video_alt["pool_priority"] = "secondary"
                    video_alt["media_type"] = "video"
                    video_alt["_priority_rank"] = 3
                    beat_candidates.append(video_alt)
            
            # Candidate 4 (FALLBACK): Alternative image
            if all_images and len(all_images) > 1:
                image_idx_alt = (global_beat_idx + 1) % len(all_images)
                if image_idx_alt != image_idx:
                    image_alt = all_images[image_idx_alt].copy()
                    image_alt["_assigned_via"] = "episode_pool_image_alt"
                    image_alt["pool_priority"] = "tertiary"  # Lowest priority
                    image_alt["media_type"] = "image"
                    image_alt["_priority_rank"] = 4
                    beat_candidates.append(image_alt)
            
            # Sort candidates by priority (video first)
            beat_candidates.sort(key=lambda x: x.get("_priority_rank", 99))
            
            beats.append({
                "block_id": bid,
                "block_index": block_index.get(bid),
                "text_preview": (txt[:140] + "...") if (txt and len(txt) > 140) else txt,
                "target_duration_sec": round(float(dur), 2) if isinstance(dur, (int, float)) else None,
                "keywords": (scene_keywords or [])[:18] if isinstance(scene_keywords, list) else [],
                "shot_types": shot_types,
                "asset_candidates": beat_candidates,
                "assets": beat_candidates,  # LLM picks best regardless of type
            })
        
        # Build manifest scene
        primary_assets = [a for a in scene_assets if a.get("pool_priority") == "primary"]
        secondary_assets = [a for a in scene_assets if a.get("pool_priority") == "secondary"]
        
        manifest_scenes.append({
            "scene_id": scene_id,
            "start_sec": scene.get("start_sec", 0),
            "end_sec": scene.get("end_sec", 0),
            "emotion": scene.get("emotion"),
            "narration_block_ids": block_ids,
            "visual_beats": beats,
            "search_queries": scene.get("search_queries", []),
            "assets": scene_assets,
            "primary_assets": primary_assets,
            "secondary_assets": secondary_assets,
            "fallback_assets": [],
            "pool_assignment": {
                "video_indices": [video_idx, video_idx_alt] if pool_videos else [],
                "image_indices": [image_idx, image_idx_alt, image_idx_alt2] if pool_images else [],
            },
        })
    
    return manifest_scenes


def resolve_shot_plan_assets(
    shot_plan: Dict[str, Any],
    cache_dir: str,
    manifest_output_path: str,
    throttle_delay_sec: float = 0.2,
    tts_ready_package: Optional[Dict[str, Any]] = None,
    voiceover_dir: Optional[str] = None,
    episode_id: Optional[str] = None,
    verbose: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    preview_mode: bool = False,
    episode_topic: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Hlavní entry point pro AAR krok v pipeline.
    
    Args:
        shot_plan: Shot plan z FDA (má search_queries, BEZ assets[])
        cache_dir: Cache složka pro search results
        manifest_output_path: Cesta kde uložit archive_manifest.json
        throttle_delay_sec: Delay mezi API calls
        episode_topic: Main episode topic for LLM-based relevance validation
    
    Returns:
        (manifest_dict, manifest_file_path)
    """
    resolver = ArchiveAssetResolver(cache_dir, throttle_delay_sec, verbose=bool(verbose), preview_mode=bool(preview_mode))

    # Normalize shot_plan schema:
    # - Expected: {"scenes": [...]}
    # - Tolerate wrapped: {"shot_plan": {"scenes": [...]}}
    scenes = []
    try:
        if isinstance(shot_plan, dict) and isinstance(shot_plan.get("scenes"), list):
            scenes = shot_plan.get("scenes") or []
        elif isinstance(shot_plan, dict) and isinstance(shot_plan.get("shot_plan"), dict) and isinstance(shot_plan["shot_plan"].get("scenes"), list):
            # unwrap
            shot_plan = shot_plan["shot_plan"]
            scenes = shot_plan.get("scenes") or []
    except Exception:
        scenes = []

    # HARD VALIDATION: shot plan must contain scenes (otherwise coverage becomes 0/0 and UI gets misleading error).
    if not scenes:
        raise AARHardFail(
            "SHOT_PLAN_EMPTY",
            "Shot plan contains 0 scenes. Cannot run Asset Resolver. Ensure FDA output produced shot_plan.scenes.",
            details={"episode_id": episode_id, "total_scenes": 0},
        )
    
    total_assets_resolved = 0
    # Episode-level reuse policy for video sources
    used_video_item_ids: set = set()
    try:
        max_unique_video_sources_per_episode = int(os.getenv("AAR_MAX_UNIQUE_VIDEO_SOURCES_PER_EPISODE", "5"))
    except Exception:
        max_unique_video_sources_per_episode = 5

    # -------------------------------
    # Narration blocks (for block-level beats + scoring)
    # -------------------------------
    def _extract_narration_blocks(tts_pkg: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(tts_pkg, dict):
            return []
        if isinstance(tts_pkg.get("narration_blocks"), list) and tts_pkg.get("narration_blocks"):
            return [b for b in tts_pkg.get("narration_blocks") if isinstance(b, dict)]
        # tolerant: convert from tts_segments
        segs = tts_pkg.get("tts_segments")
        if isinstance(segs, list) and segs:
            out = []
            for seg in segs:
                if not isinstance(seg, dict):
                    continue
                out.append(
                    {
                        "block_id": seg.get("block_id") or seg.get("segment_id"),
                        "text_tts": seg.get("tts_formatted_text") or seg.get("text") or "",
                    }
                )
            return out
        return []

    narration_blocks = _extract_narration_blocks(tts_ready_package)
    block_index: Dict[str, int] = {}
    block_text: Dict[str, str] = {}
    for i, b in enumerate(narration_blocks, start=1):
        bid = str(b.get("block_id") or "").strip()
        if not bid:
            continue
        block_index[bid] = i
        block_text[bid] = str(b.get("text_tts") or b.get("text") or "").strip()

    def _probe_audio_duration_seconds(path: str) -> Optional[float]:
        if not path or not os.path.exists(path):
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

    # Prefer actual MP3 durations when voiceover_dir is provided (video/compile guarantees voiceover exists)
    audio_durations_by_block: Dict[str, float] = {}
    if voiceover_dir and os.path.exists(voiceover_dir) and narration_blocks:
        try:
            mp3s = sorted([f for f in os.listdir(voiceover_dir) if f.startswith("Narrator_") and f.endswith(".mp3")])
            # Narrator_0001.mp3 aligns with narration_blocks order (TTS endpoint)
            for i, b in enumerate(narration_blocks, start=1):
                bid = str(b.get("block_id") or "").strip()
                if not bid:
                    continue
                expected = f"Narrator_{i:04d}.mp3"
                fn = expected if expected in mp3s else (mp3s[i - 1] if (i - 1) < len(mp3s) else None)
                if not fn:
                    continue
                dur = _probe_audio_duration_seconds(os.path.join(voiceover_dir, fn))
                if isinstance(dur, (int, float)) and dur > 0:
                    audio_durations_by_block[bid] = float(dur)
        except Exception:
            pass

    # Keyword extraction + scoring (NO AI)
    # EXPANDED stopwords to remove "plankton" filler words (A1 fix)
    _STOPWORDS = set(
        """
        the a an and or but if then else when while where who whom which what why how
        of to in on at by for from with without over under into onto as is are was were be been being
        this that these those it its it's i you he she we they them his her their our your
        not no yes do does did done can could may might will would should must
        than very more most less least just also only even
        during once held facility capable value critical strategic direct resulting embedded structure
        delayed action involved designed employed relied used indicated falsely
        """.split()
    )

    _SYNONYMS = {
        "arrest": ["detain", "detained", "custody", "captured", "capture", "police", "raid", "handcuffs", "escort"],
        "prison": ["jail", "cell", "detention", "camp", "gulag"],
        "decree": ["proclamation", "order", "edict", "directive", "declaration"],
        "document": ["paper", "dossier", "files", "signature", "signed", "archive", "letter", "telegram"],
        "purge": ["removal", "dismissal", "ousted", "expelled", "crackdown"],
        "army": ["troops", "soldiers", "military", "regiment", "forces"],
        "leader": ["president", "prime minister", "dictator", "general", "commander", "chancellor"],
        "speech": ["address", "announcement", "broadcast", "radio"],
        "map": ["maps", "front", "border", "territory"],
    }

    def _extract_keywords(text: str) -> List[str]:
        if not text or not isinstance(text, str):
            return []
        raw = text.strip()
        kws: List[str] = []

        # A1 FIX: Entity-first extraction
        # 1) Multi-word proper noun phrases (PRIORITY: these are specific entities)
        # Match sequences like "St Nazaire", "HMS Campbeltown", "Operation Chariot"
        # Pattern: Capital + lowercase word(s), up to 4 words
        entity_phrases = []
        for m in re.findall(r"\b[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3}\b", raw):
            val = m.strip()
            # Filter out single generic words (The, A, etc.)
            if len(val) >= 4 and " " in val:  # Multi-word entities only
                entity_phrases.append(val.lower())
        
        # 2) Acronyms and military designations (HMS, USS, etc.)
        for m in re.findall(r"\b(?:HMS|USS|HM|US|RAF|USAF|SS)\s+[A-Z][a-z]+\b", raw):
            entity_phrases.append(m.strip().lower())
        
        # 3) Operation names (Operation X)
        for m in re.findall(r"\bOperation\s+[A-Z][a-z]+\b", raw):
            entity_phrases.append(m.strip().lower())
        
        # Add entity phrases first (highest priority)
        for phrase in entity_phrases:
            if phrase not in kws:
                kws.append(phrase)

        # 4) Single proper nouns (names, places) - secondary priority
        for m in re.findall(r"\b[A-Z][a-z]{2,}\b", raw):
            val = m.strip().lower()
            if val not in _STOPWORDS and len(val) >= 3:
                if val not in kws:
                    kws.append(val)

        # 5) Years (dates are specific)
        for y in re.findall(r"\b(?:18|19|20)\d{2}\b", raw):
            if y not in kws:
                kws.append(y)

        # 6) Concrete object nouns (battleship, dock, destroyer, etc.) - lower priority
        concrete_nouns = ["battleship", "destroyer", "dock", "ship", "submarine", "aircraft", "tank", "fortress", 
                          "bridge", "port", "harbor", "coast", "naval", "military", "raid", "invasion", "battle"]
        tokens = re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", raw)
        for t in tokens:
            tl = t.lower()
            if tl in _STOPWORDS:
                continue
            if len(tl) < 3:
                continue
            # Prioritize concrete nouns
            if tl in concrete_nouns and tl not in kws:
                kws.append(tl)
        
        # 7) Generic tokens (last resort)
        for t in tokens:
            tl = t.lower()
            if tl in _STOPWORDS:
                continue
            if len(tl) < 3:
                continue
            if tl not in kws:
                kws.append(tl)

        # Expand with synonym keys when present
        expanded = set(kws)
        for key, syns in _SYNONYMS.items():
            if key in expanded:
                for s in syns:
                    expanded.add(s.lower())
        
        # De-dup and add synonym expansions
        out = []
        for k in kws:
            if k not in out:
                out.append(k)
        for k in expanded:
            if k not in out:
                out.append(k)
        
        # A1 ACCEPTANCE: Limit to 30 keywords, prioritizing entities
        return out[:30]

    def _score_asset(asset: Dict[str, Any], keywords: List[str]) -> Tuple[float, Dict[str, Any]]:
        title = str(asset.get("title") or "")
        desc = str(asset.get("description") or "")
        coll = str(asset.get("collection") or "")
        downloads = int(asset.get("downloads", 0) or 0)

        title_l = title.lower()
        desc_l = desc.lower()
        coll_l = coll.lower()

        score = 0.0
        matched: List[str] = []
        for kw in keywords or []:
            kw = (kw or "").strip().lower()
            if not kw or kw in _STOPWORDS:
                continue
            hit = False
            if kw in title_l:
                score += 4.0
                hit = True
            if kw in coll_l:
                score += 3.0
                hit = True
            if kw in desc_l:
                score += 2.0
                hit = True
            if hit:
                matched.append(kw)

        # small popularity prior (kept weak; relevance dominates)
        if downloads > 0:
            score += min(3.0, math.log10(downloads + 1))

        dbg = {"matched_keywords": matched[:12], "downloads": downloads}
        return score, dbg
    
    print(f"🔍 AAR: Resolving assets for {len(scenes)} scenes...")
    if episode_topic:
        print(f"🎯 AAR: Topic relevance validation enabled for: '{episode_topic}'")
    
    # Build manifest structure
    manifest = {
        "version": "archive_manifest_v3",  # v3: adds topic_validation
        "generated_at": _now_iso(),
        "episode_id": episode_id,
        "episode_topic": episode_topic,  # v14: for topic validation diagnostics
        "source_shot_plan": {
            "total_scenes": len(scenes),
            "total_duration_sec": scenes[-1].get("end_sec", 0) if scenes else 0
        },
        "compile_plan": {
            "target_fps": 30,
            "resolution": "1920x1080",
            "music": "none",
            "transitions_allowed": ["hard_cut", "fade"],
            "max_clip_repeat_sec": 0,
            "caption_style": "none",
            # B FIX: NO TITLECARDS policy
            "subclip_policy": {
                "min_in_sec": 30,
                "avoid_ranges": [[0, 30]],
                "reason": "Skip title cards, logos, credits commonly found in first 30s of archive videos"
            }
        },
        "scenes": []
    }

    # --------------------------------------------------------------------
    # PREVIEW FAST-PROBE (critical UX):
    # If all queries are dead (0 results), do NOT spend minutes looping scenes.
    # This runs only in preview_mode (aar_only) and exits early with a manifest that
    # contains zero candidates + a query_probe summary for UI.
    # NOTE: Skip Fast-Probe if Episode Pool Mode is enabled (it handles preview too)
    # --------------------------------------------------------------------
    episode_pool_mode = str(os.getenv("AAR_EPISODE_POOL_MODE", "1")).strip().lower() in ("1", "true", "yes")
    
    if preview_mode and not episode_pool_mode:
        try:
            def _norm_q(x: Any) -> str:
                return " ".join(str(x or "").split()).strip()

            all_queries = []
            for sc in scenes:
                if not isinstance(sc, dict):
                    continue
                # Prefer a small, diverse probe set:
                # - L1: strict FDA queries (often image/doc oriented)
                # - L2: include anchored video-friendly variants (entity/newsreel/documentary) to avoid false "0 hits"
                try:
                    tiers = resolver._generate_query_tiers(sc) if hasattr(resolver, "_generate_query_tiers") else {}
                except Exception:
                    tiers = {}

                probe_qs = []
                if isinstance(sc.get("search_queries"), list):
                    probe_qs.extend(sc.get("search_queries") or [])
                if isinstance(tiers, dict):
                    # Keep probe lightweight: add only a couple from L2 (usually: "<Entity>", "<Entity> newsreel", ...)
                    l2 = tiers.get("L2") if isinstance(tiers.get("L2"), list) else []
                    probe_qs.extend(l2[:3])

                for q in probe_qs:
                    nq = _norm_q(q)
                    if nq:
                        all_queries.append(nq)

            # de-dupe, keep order
            seen = set()
            unique_queries = []
            for q in all_queries:
                k = q.lower()
                if k in seen:
                    continue
                seen.add(k)
                unique_queries.append(q)

            try:
                max_probe_queries = int(os.getenv("AAR_PREVIEW_PROBE_MAX_QUERIES", "12"))
            except Exception:
                max_probe_queries = 12

            probe_results = []
            any_hits = False
            for q in unique_queries[:max_probe_queries]:
                # Probe video (multi-source) + image (archive.org) + docs (archive.org texts)
                v = resolver.search_multi_source(q, max_results=1)
                i = resolver.search_archive_org(
                    q,
                    max_results=1,
                    mediatype_filter=ARCHIVE_IMAGE_MEDIATYPE_FILTER,
                    media_label="image_probe",
                )
                d = resolver.search_archive_org(
                    q,
                    max_results=1,
                    mediatype_filter=ARCHIVE_TEXT_MEDIATYPE_FILTER,
                    media_label="doc_probe",
                )
                vh = len(v) if isinstance(v, list) else 0
                ih = len(i) if isinstance(i, list) else 0
                dh = len(d) if isinstance(d, list) else 0
                probe_results.append({"query": q, "video_hits": vh, "image_hits": ih, "doc_hits": dh})
                if (vh + ih + dh) > 0:
                    any_hits = True
                    break

            manifest["query_probe"] = {
                "mode": "preview_fast_probe",
                "unique_queries_total": len(unique_queries),
                "probed_queries": len(probe_results),
                "any_hits": any_hits,
                "probe_results": probe_results,
                "note": "Probe stops early on first hit; if any_hits=false, preview exits early with 0 candidates.",
            }

            if unique_queries and not any_hits:
                # Early exit: Build minimal per-scene structure with 0 candidates.
                for i, scene in enumerate(scenes):
                    scene_id = scene.get("scene_id", f"sc_{i:04d}")
                    block_ids = scene.get("narration_block_ids") if isinstance(scene.get("narration_block_ids"), list) else []
                    shot_strategy = scene.get("shot_strategy") or {}
                    shot_types = shot_strategy.get("shot_types") or []

                    beats = []
                    for bid in block_ids:
                        bid = str(bid or "").strip()
                        if not bid:
                            continue
                        txt = block_text.get(bid) or ""
                        dur = audio_durations_by_block.get(bid)
                        beats.append(
                            {
                                "block_id": bid,
                                "block_index": block_index.get(bid),
                                "text_preview": (txt[:140] + "...") if (txt and len(txt) > 140) else txt,
                                "target_duration_sec": round(float(dur), 2) if isinstance(dur, (int, float)) else None,
                                "keywords": (scene.get("keywords") or [])[:18] if isinstance(scene.get("keywords"), list) else [],
                                "shot_types": shot_types,
                                "asset_candidates": [],
                                "unresolved_reason": "preview_probe_zero_results",
                            }
                        )

                    manifest["scenes"].append(
                        {
                            "scene_id": scene_id,
                            "start_sec": scene.get("start_sec", 0),
                            "end_sec": scene.get("end_sec", 0),
                            "emotion": scene.get("emotion"),
                            "narration_block_ids": block_ids,
                            "visual_beats": beats,
                            "search_queries": scene.get("search_queries", []) if isinstance(scene.get("search_queries"), list) else [],
                            "assets": [],
                            "primary_assets": [],
                            "secondary_assets": [],
                            "fallback_assets": [],
                            "resolve_diagnostics": {
                                "queries_attempted": (scene.get("search_queries") or [])[:10] if isinstance(scene.get("search_queries"), list) else [],
                                "reject_reasons_summary": {"no_results": 1},
                                "total_candidates_found": 0,
                                "used_global_fallback": False,
                                "note": "Preview fast-probe ended early (0 hits).",
                            },
                        }
                    )

                os.makedirs(os.path.dirname(manifest_output_path), exist_ok=True)
                with open(manifest_output_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                return manifest, manifest_output_path
        except Exception:
            # Never let probe break the preview; fall back to normal per-scene processing.
            pass
    
    # ════════════════════════════════════════════════════════════════════════════
    # EPISODE-FIRST POOL MODE (efficiency optimization)
    # Instead of per-scene resolution (300+ API calls), we:
    # 1. Get episode pool (12 API calls)
    # 2. Distribute pool across scenes (0 API calls)
    # ════════════════════════════════════════════════════════════════════════════
    # Episode Pool Mode works for BOTH preview and full compile (same efficiency benefit)
    # (episode_pool_mode already defined above, before PREVIEW FAST-PROBE section)
    if episode_pool_mode:
        print(f"🚀 AAR: Using EPISODE-FIRST POOL MODE (efficient)")
        
        try:
            # Get max pool sizes from env
            try:
                pool_max_videos = int(os.getenv("AAR_POOL_MAX_VIDEOS", "8"))
            except Exception:
                pool_max_videos = 8
            try:
                pool_max_images = int(os.getenv("AAR_POOL_MAX_IMAGES", "15"))
            except Exception:
                pool_max_images = 15
            
            # Resolve episode pool
            pool = resolve_episode_pool(
                shot_plan=shot_plan,
                cache_dir=cache_dir,
                max_videos=pool_max_videos,
                max_images=pool_max_images,
                episode_topic=episode_topic,
                verbose=verbose,
                progress_callback=progress_callback,
            )
            
            # Check if pool has any content
            pool_videos = pool.get("videos") or []
            pool_images = pool.get("images") or []
            
            if pool_videos or pool_images:
                # Distribute pool to scenes
                manifest_scenes = _distribute_pool_to_scenes(
                    pool=pool,
                    scenes=scenes,
                    narration_blocks=narration_blocks,
                    block_index=block_index,
                    block_text=block_text,
                    audio_durations_by_block=audio_durations_by_block,
                )
                
                manifest["scenes"] = manifest_scenes
                manifest["episode_pool"] = {
                    "mode": "episode_first",
                    "videos_count": len(pool_videos),
                    "images_count": len(pool_images),
                    "queries_used": pool.get("queries_used") or [],
                    "stats": pool.get("stats") or {},
                    # Transparency: store raw + unique ranked + selected lists for UI (no black box)
                    "raw_candidates": pool.get("raw_candidates") or {},
                    "unique_ranked": pool.get("unique_ranked") or {},
                    "selected_ranked": pool.get("selected_ranked") or {},
                }
                
                # Calculate coverage
                total_beats = sum(len(s.get("visual_beats", [])) for s in manifest_scenes)
                beats_with_assets = sum(
                    1 for s in manifest_scenes
                    for b in (s.get("visual_beats") or [])
                    if b.get("asset_candidates")
                )
                
                coverage_pct = (beats_with_assets / total_beats * 100) if total_beats > 0 else 0
                
                print(f"✅ AAR: Episode pool mode complete:")
                print(f"   📹 Videos: {len(pool_videos)}")
                print(f"   🖼️  Images: {len(pool_images)}")
                print(f"   📊 Coverage: {beats_with_assets}/{total_beats} beats ({coverage_pct:.1f}%)")
                print(f"   ⚡ Efficiency: ~{len(pool.get('queries_used', []))} queries instead of ~{len(scenes) * 5}")
                
                # Save manifest (before Visual Assistant)
                os.makedirs(os.path.dirname(manifest_output_path), exist_ok=True)
                with open(manifest_output_path, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                
                # ════════════════════════════════════════════════════════════════════════════
                # VISUAL ASSISTANT - LLM reranking (automatic if enabled)
                # Analyzes thumbnails and picks best candidate per beat
                # ════════════════════════════════════════════════════════════════════════════
                # ═══════════════════════════════════════════════════════════════════════════
                # VISUAL ASSISTANT - DEFAULT ENABLED
                # LLM analyzes thumbnails and picks best candidate per beat
                # This is CRITICAL for quality - ensures relevant, high-quality visuals
                # ═══════════════════════════════════════════════════════════════════════════
                # IMPORTANT: No black box by default.
                # Visual Assistant should be an explicit user action (UI button), not an automatic step.
                auto_visual_assistant = str(os.getenv("AAR_AUTO_VISUAL_ASSISTANT", "0")).strip().lower() in ("1", "true", "yes")
                
                if auto_visual_assistant and episode_id:
                    try:
                        print(f"🎨 AAR: Running Visual Assistant (LLM reranking)...")
                        
                        # Import here to avoid circular dependency
                        from visual_assistant import run_visual_assistant
                        
                        # Get API key and settings
                        openai_key = os.getenv("OPENAI_API_KEY")
                        openrouter_key = os.getenv("OPENROUTER_API_KEY")
                        
                        # Prefer OpenRouter, fallback to OpenAI
                        if openrouter_key:
                            api_key = openrouter_key
                            provider = "openrouter"
                            model = "openai/gpt-4o"
                        elif openai_key:
                            api_key = openai_key
                            provider = "openai"
                            model = "gpt-4o"
                        else:
                            print(f"⚠️  AAR: Visual Assistant skipped - no API key (set OPENAI_API_KEY or OPENROUTER_API_KEY)")
                            api_key = None
                        
                        if api_key:
                            # Get projects_dir from manifest_output_path
                            # manifest_output_path = .../projects/ep_xxx/archive_manifest.json
                            projects_dir = os.path.dirname(os.path.dirname(manifest_output_path))
                            
                            enhanced_manifest = run_visual_assistant(
                                episode_id=episode_id,
                                projects_dir=projects_dir,
                                api_key=api_key,
                                model=model,
                                temperature=0.15,  # Low temperature for consistency
                                custom_prompt=None,  # Use default prompt
                                max_analyze_per_beat=3,  # Analyze top 3 candidates
                                verbose=verbose,
                                provider=provider
                            )
                            
                            print(f"✅ AAR: Visual Assistant complete - manifest enhanced with LLM picks")
                            manifest = enhanced_manifest  # Use enhanced manifest
                            
                            # Save enhanced manifest
                            with open(manifest_output_path, 'w', encoding='utf-8') as f:
                                json.dump(manifest, f, ensure_ascii=False, indent=2)
                    
                    except Exception as e:
                        print(f"⚠️  AAR: Visual Assistant failed: {e}")
                        print(f"   Continuing with mechanical pool distribution...")
                
                print(f"✅ AAR: Manifest saved to {manifest_output_path}")
                return manifest, manifest_output_path
            else:
                # NO FALLBACK! Raise hard error if pool is empty
                error_msg = (
                    "Episode pool is empty (0 videos, 0 images). This is a critical failure - "
                    "cannot create video without visuals. Check: 1) Archive.org availability, "
                    "2) Wikimedia search, 3) Query relevance."
                )
                print(f"❌ AAR: {error_msg}")
                raise AARHardFail(
                    "EPISODE_POOL_EMPTY",
                    error_msg,
                    details={
                        "pool_videos": len(pool_videos),
                        "pool_images": len(pool_images),
                        "queries_used": pool.get("queries_used", []),
                    }
                )
        
        except AARHardFail as e:
            # Episode pool failure = HARD STOP. NO FALLBACK TO PER-SCENE MODE.
            print(f"❌ AAR: Episode pool mode hard-failed: {e}")
            raise  # Always raise, never fall back
        except Exception as e:
            # Unexpected error = HARD STOP. NO FALLBACK TO PER-SCENE MODE.
            print(f"❌ AAR: Episode pool mode failed with unexpected error: {e}")
            raise AARHardFail(
                "EPISODE_POOL_ERROR",
                f"Episode pool mode failed: {str(e)}",
                details={"exception": str(e)}
            )
    
    # ════════════════════════════════════════════════════════════════════════════
    # IF WE GET HERE, episode_pool_mode is False (disabled by env var)
    # This should NEVER happen in production - episode pool mode is always enabled.
    # ════════════════════════════════════════════════════════════════════════════
    raise AARHardFail(
        "EPISODE_POOL_MODE_DISABLED",
        "Episode pool mode is disabled. This is not allowed - set AAR_ENABLE_EPISODE_POOL=1 in .env",
        details={"episode_pool_mode": episode_pool_mode}
    )

    return manifest, manifest_output_path

