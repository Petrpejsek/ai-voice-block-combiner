"""
AAR Step-by-Step API
Provides granular control over Archive Asset Resolver workflow.

Workflow:
1. generate_queries() - Extract queries from shot_plan
2. search_with_custom_queries() - Search archives with user-edited queries
3. llm_quality_check() - Run LLM deduplication + quality ranking on raw results
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def _normalize_query_for_archive_search(q: str, episode_topic: str = "") -> str:
    """
    Make queries search-engine friendly (Archive.org / Wikimedia / Europeana).
    Deterministic normalization, not an LLM and not a "fallback generator".
    
    Rationale:
    - Our FDA v2.7 `search_queries` intentionally include tail tokens like
      "archive scan/original print/aftermath view" to satisfy the strict validator.
      Those tokens hurt recall in real search backends (AND-heavy query parsing).
    - Some narration uses spelled-out years ("eighteen seventy-one") while search
      indexes usually contain digits ("1871").
    """
    s = " ".join(str(q or "").split()).strip()
    if not s:
        return ""

    # Remove low-signal tail tokens that reduce recall.
    drop_phrases = [
        "archive scan", "archive print", "archive copy", "archive page",
        "original print", "original handwriting",
        "aftermath view", "archive view",
    ]
    low = s.lower()
    for ph in drop_phrases:
        low = low.replace(ph, " ")

    # Tokenize and drop single-word noise tokens.
    noise_tokens = {
        "archive", "archival", "original", "print", "scan", "copy", "page", "view", "aftermath",
        # common weak verbs from narration that sometimes leak into queries
        "begin", "began", "beginning", "stories", "story",
    }

    tokens = [t for t in low.split() if t and t not in noise_tokens]

    # Convert common spoken-year patterns → digits (limited but effective).
    # Example: "eighteen seventy-one" → "1871"
    year_map = {
        ("eighteen", "seventy-one"): "1871",
        ("eighteen", "seventy", "one"): "1871",
        ("nineteen", "twelve"): "1912",
        ("nineteen", "fourteen"): "1914",
        ("nineteen", "eighteen"): "1918",
    }
    i = 0
    out_tokens: List[str] = []
    while i < len(tokens):
        replaced = False
        for k, v in year_map.items():
            if tuple(tokens[i:i+len(k)]) == k:
                out_tokens.append(v)
                i += len(k)
                replaced = True
                break
        if not replaced:
            out_tokens.append(tokens[i])
            i += 1

    # If episode_topic contains a 4-digit year and query doesn't, add it (helps recall).
    import re
    year_in_topic = ""
    try:
        m = re.search(r"\b(1\d{3}|20\d{2})\b", str(episode_topic or ""))
        if m:
            year_in_topic = m.group(1)
    except Exception:
        year_in_topic = ""
    if year_in_topic and not any(re.fullmatch(r"(1\d{3}|20\d{2})", t) for t in out_tokens):
        out_tokens.insert(1 if len(out_tokens) >= 1 else 0, year_in_topic)

    # Cap length for search (avoid overly long AND queries)
    out_tokens = out_tokens[:8]

    # Re-titlecase first token if it was capitalized in original (helps readability, not logic)
    normalized = " ".join(out_tokens).strip()
    if not normalized:
        return ""
    # Keep original capitalization for known proper nouns like Chicago
    if s.split()[0][:1].isupper():
        normalized = s.split()[0] + " " + " ".join(normalized.split()[1:])
    return " ".join(normalized.split()).strip()


def generate_queries_for_episode(
    episode_id: str,
    project_store,
) -> Dict[str, Any]:
    """
    Step 1: Generate AAR queries from shot_plan (NO SEARCH).
    
    Returns:
        {
            "success": bool,
            "queries": [str],
            "episode_topic": str
        }
    """
    from archive_asset_resolver import _extract_episode_queries
    
    state = project_store.read_script_state(episode_id)
    
    # Extract shot_plan
    shot_plan = None
    if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("shot_plan"), dict):
        shot_plan = state["metadata"]["shot_plan"]
    elif isinstance(state.get("shot_plan"), dict):
        shot_plan = state["shot_plan"]
    
    if not shot_plan:
        raise ValueError("Shot plan nenalezen. Nejdříve spusť FDA (Footage Director).")
    
    # Extract scenes
    scenes = []
    if isinstance(shot_plan.get("scenes"), list):
        scenes = shot_plan["scenes"]
    elif isinstance(shot_plan.get("shot_plan"), dict) and isinstance(shot_plan["shot_plan"].get("scenes"), list):
        scenes = shot_plan["shot_plan"]["scenes"]
    
    if not scenes:
        raise ValueError("Shot plan nemá žádné scény")
    
    # Get episode topic
    episode_topic = (
        state.get("topic") 
        or state.get("metadata", {}).get("topic") 
        or (state.get("episode_input") or {}).get("topic")
        or ""
    )
    
    # Generate queries (STRICT):
    # Prefer FDA-produced scene.search_queries (already structured and guardrailed).
    # This avoids ambiguous anchor-only phrases like "In 1871" which are slow/low-signal for search.
    episode_queries: List[str] = []
    seen = set()
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        sq = sc.get("search_queries")
        if not isinstance(sq, list):
            continue
        for q in sq:
            qq = " ".join(str(q or "").split()).strip()
            if not qq:
                continue
            k = qq.lower()
            if k in seen:
                continue
            seen.add(k)
            episode_queries.append(qq)
            if len(episode_queries) >= 12:
                break
        if len(episode_queries) >= 12:
            break

    if not episode_queries:
        # Explicit fallback (legacy shot plans without search_queries).
        # This is visible in the output so it is not a silent degradation.
        episode_queries = _extract_episode_queries(scenes, max_queries=12, episode_topic=episode_topic)

    # Normalize for search (keeps UI queries more effective).
    episode_queries_norm: List[str] = []
    seen_n = set()
    for q in episode_queries:
        qq = _normalize_query_for_archive_search(q, episode_topic=episode_topic)
        if not qq:
            continue
        k = qq.lower()
        if k in seen_n:
            continue
        seen_n.add(k)
        episode_queries_norm.append(qq)
        if len(episode_queries_norm) >= 12:
            break
    episode_queries = episode_queries_norm or episode_queries
    
    # Save to manifest
    episode_dir = project_store.episode_dir(episode_id)
    manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
    
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    if 'episode_pool' not in manifest:
        manifest['episode_pool'] = {}
    
    manifest['episode_pool']['auto_generated_queries'] = episode_queries
    manifest['episode_pool']['queries_generated_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest['episode_pool']['step'] = 'queries_generated'
    
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "queries": episode_queries,
        "episode_topic": episode_topic,
        "query_count": len(episode_queries)
    }


def search_with_custom_queries(
    episode_id: str,
    custom_queries: List[str],
    project_store,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Step 2: Search Archive.org/Wikimedia/Europeana with user-edited queries.
    Returns RAW results (no LLM quality check yet).
    
    Args:
        custom_queries: User-edited list of search queries
    
    Returns:
        {
            "success": bool,
            "raw_video_candidates": [dict],
            "raw_image_candidates": [dict],
            "queries_executed": [str],
            "stats": {...}
        }
    """
    from archive_asset_resolver import ArchiveAssetResolver
    
    if not custom_queries:
        raise ValueError("custom_queries je povinné (prázdný list není povolen)")
    
    episode_dir = project_store.episode_dir(episode_id)
    cache_dir = os.path.join(episode_dir, "archive_cache")
    os.makedirs(cache_dir, exist_ok=True)

    # Load episode topic (used for deterministic query normalization).
    episode_topic = ""
    try:
        st = project_store.read_script_state(episode_id)
        episode_topic = (
            st.get("topic")
            or (st.get("metadata") or {}).get("topic")
            or ((st.get("metadata") or {}).get("tts_ready_package") or {}).get("episode_metadata", {}).get("topic")
            or (st.get("tts_ready_package") or {}).get("episode_metadata", {}).get("topic")
            or ""
        )
    except Exception:
        episode_topic = ""

    # Normalize queries for real-world search engines (reduces "0 results" cases).
    normalized_queries: List[str] = []
    seenq = set()
    for q in (custom_queries or []):
        qq = _normalize_query_for_archive_search(q, episode_topic=episode_topic)
        if not qq:
            continue
        k = qq.lower()
        if k in seenq:
            continue
        seenq.add(k)
        normalized_queries.append(qq)
    custom_queries = normalized_queries or custom_queries
    
    # Create resolver
    # Step-by-step UI is an interactive "preview mode" → keep requests fast and avoid long hangs.
    resolver = ArchiveAssetResolver(
        cache_dir,
        throttle_delay_sec=0.25,
        verbose=verbose,
        preview_mode=True,
    )

    # #region agent log
    try:
        import time as _time, json as _json, os as _os
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H4",
                "location": "backend/aar_step_by_step.py:search_with_custom_queries",
                "message": "Resolver created for step2 search",
                "data": {
                    "episode_id": str(episode_id),
                    "custom_queries_count": int(len(custom_queries)),
                    "MULTI_SOURCE_AVAILABLE": bool(getattr(__import__("archive_asset_resolver"), "MULTI_SOURCE_AVAILABLE", False)),
                    "has_europeana_key": bool(str(_os.getenv("EUROPEANA_API_KEY") or "").strip()),
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion
    
    # Search videos (cap count for interactive mode)
    all_video_candidates = []
    for query in custom_queries[:12]:
        if verbose:
            print(f"📹 Searching videos: {query}")
        results = resolver.search_multi_source(query, max_results=10)
        for r in results:
            r["_source_query"] = query
        all_video_candidates.extend(results)
    
    # Search images (cap more aggressively)
    all_image_candidates = []
    for query in custom_queries[:8]:  # Fewer image queries
        if verbose:
            print(f"🖼️  Searching images: {query}")
        results = resolver.search_images_multi_source(query, max_results=10)
        for r in results:
            r["_source_query"] = query
            r["media_type"] = "image"
        all_image_candidates.extend(results)

    # #region agent log
    try:
        import time as _time, json as _json
        def _infer_src(item: dict) -> str:
            try:
                src = str(item.get("source") or "").strip().lower()
                if "wiki" in src or "commons" in src:
                    return "wikimedia"
                if "europeana" in src:
                    return "europeana"
                aid = str(item.get("archive_item_id") or "").strip()
                if ":" in aid:
                    p = aid.split(":", 1)[0].strip().lower()
                    if p in ("wikimedia", "commons", "wikimedia_commons"):
                        return "wikimedia"
                    if p == "europeana":
                        return "europeana"
                    if p in ("archive", "archiveorg", "archive_org", "archive.org"):
                        return "archive_org"
                    return p or "other"
                return "archive_org"
            except Exception:
                return "other"
        by_src_v = {"archive_org": 0, "wikimedia": 0, "europeana": 0, "other": 0}
        for v in (all_video_candidates or []):
            if isinstance(v, dict):
                k = _infer_src(v)
                by_src_v[k] = by_src_v.get(k, 0) + 1
        by_src_i = {"archive_org": 0, "wikimedia": 0, "europeana": 0, "other": 0}
        for it in (all_image_candidates or []):
            if isinstance(it, dict):
                k = _infer_src(it)
                by_src_i[k] = by_src_i.get(k, 0) + 1
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H4",
                "location": "backend/aar_step_by_step.py:search_with_custom_queries",
                "message": "Step2 raw candidates source breakdown",
                "data": {
                    "videos_total": int(len(all_video_candidates or [])),
                    "images_total": int(len(all_image_candidates or [])),
                    "videos_by_source": by_src_v,
                    "images_by_source": by_src_i,
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion
    
    # Save RAW results to manifest
    manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    if 'episode_pool' not in manifest:
        manifest['episode_pool'] = {}
    
    manifest['episode_pool']['raw_candidates'] = {
        "videos": all_video_candidates,
        "images": all_image_candidates
    }
    manifest['episode_pool']['queries_used'] = custom_queries
    manifest['episode_pool']['search_completed_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest['episode_pool']['step'] = 'raw_search_completed'
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "raw_video_candidates": all_video_candidates,
        "raw_image_candidates": all_image_candidates,
        "queries_executed": custom_queries,
        "stats": {
            "total_video_candidates": len(all_video_candidates),
            "total_image_candidates": len(all_image_candidates),
            "queries_executed": len(custom_queries)
        }
    }


def llm_quality_check(
    episode_id: str,
    project_store,
    manual_selection: Optional[Dict[str, List[str]]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Step 3: Run LLM Visual Assistant to deduplicate + rank raw candidates.
    Reads raw_candidates from manifest, applies LLM quality check, saves final pool.
    
    Args:
        manual_selection: Optional dict with {"video_ids": [str], "image_ids": [str]}
                         If provided, skips LLM thresholds and uses user's manual selection
    
    Returns:
        {
            "success": bool,
            "unique_videos": [dict],
            "unique_images": [dict],
            "selected_videos": [dict],
            "selected_images": [dict],
            "stats": {...}
        }
    """
    from visual_assistant import VisualAssistant
    
    episode_dir = project_store.episode_dir(episode_id)
    manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
    
    if not os.path.exists(manifest_path):
        raise ValueError("Archive manifest nenalezen. Nejdříve spusť search.")
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    pool = manifest.get('episode_pool') or {}
    raw_cand = pool.get('raw_candidates') or {}
    
    all_video_candidates = raw_cand.get('videos') or []
    all_image_candidates = raw_cand.get('images') or []
    
    if not all_video_candidates and not all_image_candidates:
        raise ValueError("Žádné raw candidates k analýze. Nejdříve spusť search.")
    
    # Get episode topic for LLM context
    state = project_store.read_script_state(episode_id)
    episode_topic = (
        state.get("topic") 
        or state.get("metadata", {}).get("topic") 
        or (state.get("episode_input") or {}).get("topic")
        or "documentary footage"
    )
    
    # Extract additional context from shot_plan for better LLM relevance
    shot_plan = None
    if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("shot_plan"), dict):
        shot_plan = state["metadata"]["shot_plan"]
    elif isinstance(state.get("shot_plan"), dict):
        shot_plan = state["shot_plan"]
    
    # Aggregate scene context (narration summaries + keywords) for richer LLM prompt
    scene_context_parts = []
    all_keywords = set()
    if shot_plan:
        scenes = []
        if isinstance(shot_plan.get("scenes"), list):
            scenes = shot_plan["scenes"]
        elif isinstance(shot_plan.get("shot_plan"), dict) and isinstance(shot_plan["shot_plan"].get("scenes"), list):
            scenes = shot_plan["shot_plan"]["scenes"]
        
        for sc in scenes[:5]:  # First 5 scenes for context (to avoid token bloat)
            if not isinstance(sc, dict):
                continue
            narr_summary = sc.get("narration_summary", "").strip()
            if narr_summary:
                scene_context_parts.append(narr_summary[:150])  # Limit to 150 chars per scene
            
            keywords = sc.get("keywords", [])
            if isinstance(keywords, list):
                all_keywords.update(k for k in keywords if isinstance(k, str) and k.strip())
    
    # Build enriched episode context for LLM
    enriched_topic = episode_topic
    if scene_context_parts:
        enriched_topic += "\n\nKey scenes: " + " • ".join(scene_context_parts[:3])
    if all_keywords:
        enriched_topic += "\n\nKeywords: " + ", ".join(list(all_keywords)[:15])
    
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
        raise ValueError("No API key for Visual Assistant (OPENAI_API_KEY or OPENROUTER_API_KEY)")
    
    print(f"🎨 Running LLM Visual Deduplication + Quality Ranking...")
    
    va = VisualAssistant(
        api_key=api_key,
        model=model,
        temperature=0.15,
        verbose=verbose,
        provider=provider
    )
    
    # Deduplicate + rank videos
    unique_videos = []
    if all_video_candidates:
        unique_videos = va.deduplicate_and_rank_pool_candidates(
            candidates=all_video_candidates,
            episode_topic=enriched_topic,
            max_analyze=30
        )
        print(f"   📹 Videos: {len(all_video_candidates)} → {len(unique_videos)} unique")
    
    # Deduplicate + rank images
    unique_images = []
    if all_image_candidates:
        unique_images = va.deduplicate_and_rank_pool_candidates(
            candidates=all_image_candidates,
            episode_topic=enriched_topic,
            max_analyze=30
        )
        print(f"   🖼️  Images: {len(all_image_candidates)} → {len(unique_images)} unique")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MANUAL SELECTION OVERRIDE (user-controlled workflow)
    # ═══════════════════════════════════════════════════════════════════════════
    if manual_selection and isinstance(manual_selection, dict):
        manual_video_ids = set(manual_selection.get("video_ids") or [])
        manual_image_ids = set(manual_selection.get("image_ids") or [])
        
        if manual_video_ids or manual_image_ids:
            print(f"   ✋ Manual selection detected: {len(manual_video_ids)} videos, {len(manual_image_ids)} images")
            print(f"   🔀 Skipping LLM thresholds - using user selection directly")
            
            # Filter candidates by manual selection
            selected_videos = [v for v in unique_videos if v.get("archive_item_id") in manual_video_ids]
            selected_images = [i for i in unique_images if i.get("archive_item_id") in manual_image_ids]
            
            print(f"   ✅ Manual selection applied: {len(selected_videos)} videos, {len(selected_images)} images")
            
            # Save to manifest and return early
            manifest['episode_pool']['unique_ranked'] = {
                "videos": unique_videos,
                "images": unique_images
            }
            manifest['episode_pool']['selected_ranked'] = {
                "videos": selected_videos,
                "images": selected_images
            }
            manifest['episode_pool']['llm_completed_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            manifest['episode_pool']['step'] = 'llm_quality_complete'
            manifest['episode_pool']['manual_selection_applied'] = True
            manifest['episode_pool']['stats'] = {
                "total_video_candidates": len(all_video_candidates),
                "total_image_candidates": len(all_image_candidates),
                "unique_videos_found": len(unique_videos),
                "unique_images_found": len(unique_images),
                "pool_videos": len(selected_videos),
                "pool_images": len(selected_images),
                "manual_selection": True,
            }
            
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            
            return {
                "success": True,
                "unique_videos": unique_videos,
                "unique_images": unique_images,
                "selected_videos": selected_videos,
                "selected_images": selected_images,
                "stats": manifest['episode_pool']['stats']
            }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # AUTO MODE: Apply quality + relevance thresholds (LLM-driven)
    # ═══════════════════════════════════════════════════════════════════════════
    # RELAXED thresholds for Step-by-Step workflow (user manually approves results anyway)
    MIN_QUALITY_THRESHOLD = 0.30  # Lowered from 0.50 (too strict for diverse archive content)
    MIN_TOPIC_REL_VIDEO = 0.05   # Lowered from 0.10 (LLM often gives very low scores for archive.org)
    MIN_TOPIC_REL_IMAGE = 0.10   # Lowered from 0.30 (images are often tangentially related)
    
    def _topic_rel(x: Dict[str, Any]) -> float:
        try:
            la = x.get("llm_analysis") if isinstance(x, dict) else None
            la = la if isinstance(la, dict) else {}
            tr = la.get("topic_relevance")
            return float(tr) if isinstance(tr, (int, float)) else 0.0
        except Exception:
            return 0.0
    
    # Filter by topic relevance
    rel_videos = [v for v in unique_videos if _topic_rel(v) >= MIN_TOPIC_REL_VIDEO]
    rel_images = [i for i in unique_images if _topic_rel(i) >= MIN_TOPIC_REL_IMAGE]
    
    # Filter by quality
    quality_videos = [v for v in rel_videos if float(v.get('llm_quality_score', 0) or 0) >= MIN_QUALITY_THRESHOLD]
    quality_images = [i for i in rel_images if float(i.get('llm_quality_score', 0) or 0) >= MIN_QUALITY_THRESHOLD]
    
    # If nothing passes strict quality, allow relevant items with lower quality
    selected_videos = quality_videos if quality_videos else rel_videos[:8]
    selected_images = quality_images if quality_images else rel_images[:15]
    
    print(f"   🎯 Selected: {len(selected_videos)} videos, {len(selected_images)} images")
    
    # Update manifest with final results
    manifest['episode_pool']['unique_ranked'] = {
        "videos": unique_videos,
        "images": unique_images
    }
    manifest['episode_pool']['selected_ranked'] = {
        "videos": selected_videos,
        "images": selected_images
    }
    manifest['episode_pool']['llm_completed_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest['episode_pool']['step'] = 'llm_quality_complete'
    manifest['episode_pool']['stats'] = {
        "total_video_candidates": len(all_video_candidates),
        "total_image_candidates": len(all_image_candidates),
        "unique_videos_found": len(unique_videos),
        "unique_images_found": len(unique_images),
        "pool_videos": len(selected_videos),
        "pool_images": len(selected_images),
        "videos_above_threshold": len(quality_videos),
        "images_above_threshold": len(quality_images),
        "has_llm_scores": True,
        "quality_threshold": MIN_QUALITY_THRESHOLD
    }
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "unique_videos": unique_videos,
        "unique_images": unique_images,
        "selected_videos": selected_videos,
        "selected_images": selected_images,
        "stats": manifest['episode_pool']['stats']
    }

