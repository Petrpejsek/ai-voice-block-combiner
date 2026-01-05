"""
Visual Curator - Výběr nejlepších a nejrozmanitějších assetů

Účel:
- Načte raw results z AAR (aar_raw_results.json)
- Aplikuje quality filtering (low-quality vyřazení)
- Provede deduplikaci (perceptual hash, metadata similarity)
- Rankuje assety podle relevance + quality + diversity
- Reportuje coverage balance a deficity

Výstup: visual_curator_output.json
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict
import hashlib


VERSION = "visual_curator_v1"


def _now_iso() -> str:
    """ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _asset_fingerprint(asset: Dict[str, Any]) -> str:
    """
    Vytvoří fingerprint pro asset deduplikaci.
    
    Používá:
    - archive_item_id (primární)
    - asset_url (fallback)
    - title similarity (heuristic)
    """
    item_id = asset.get("archive_item_id", "")
    if item_id:
        return f"item_{item_id}"
    
    url = asset.get("asset_url", "")
    if url:
        # Hash URL (pro non-archive sources)
        return f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}"
    
    # Fallback: title hash
    title = str(asset.get("title", "")).strip().lower()
    if title:
        return f"title_{hashlib.md5(title.encode()).hexdigest()[:12]}"
    
    # Last resort: empty (will be filtered out)
    return ""


def _quality_score(asset: Dict[str, Any]) -> float:
    """
    Vypočítá quality score (0.0 - 1.0).
    
    Faktory:
    - media_type preference (video > image)
    - has_thumbnail
    - title_quality (length, specificity)
    - source_quality (archive.org > stock > generic)
    """
    score = 0.5  # Base score
    
    # Media type preference
    media_type = asset.get("media_type", "image")
    if media_type == "video":
        score += 0.2
    elif media_type == "image":
        score += 0.1
    
    # Thumbnail availability
    if asset.get("thumbnail_url"):
        score += 0.1
    
    # Title quality
    title = str(asset.get("title", "")).strip()
    if len(title) > 20:
        score += 0.1
    if len(title) > 50:
        score += 0.05
    
    # Source quality
    source = asset.get("source", "")
    if "archive.org" in source or source == "archive_org":
        score += 0.15
    elif source in ("wikimedia", "europeana"):
        score += 0.1
    elif source in ("pexels", "pixabay"):
        score += 0.05
    
    return min(1.0, score)


def _relevance_score(asset: Dict[str, Any]) -> float:
    """
    Extrahuje relevance score z AAR.
    
    Fallback:
    - topic_relevance_score (z AAR v14+)
    - score (generic)
    - default 0.5
    """
    # Preferuj topic_relevance_score (AAR v14+)
    if "topic_relevance_score" in asset:
        try:
            return float(asset["topic_relevance_score"])
        except (ValueError, TypeError):
            pass
    
    # Fallback na generic score
    if "score" in asset:
        try:
            return float(asset["score"])
        except (ValueError, TypeError):
            pass
    
    return 0.5


def _is_low_quality(asset: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Detekuje low-quality assety pro vyřazení.
    
    Returns:
        (is_low_quality, rejection_reason)
    """
    # Missing essential fields
    if not asset.get("archive_item_id") and not asset.get("asset_url"):
        return True, "missing_identifier"
    
    # Very low relevance
    relevance = _relevance_score(asset)
    if relevance < 0.2:
        return True, "very_low_relevance"
    
    # Quality score too low
    quality = _quality_score(asset)
    if quality < 0.3:
        return True, "low_quality_score"
    
    # Title too generic (common noise)
    title = str(asset.get("title", "")).strip().lower()
    generic_titles = {
        "untitled", "image", "video", "file", "document", "photo",
        "picture", "scan", "archive", "item", "record",
    }
    if title in generic_titles:
        return True, "generic_title"
    
    return False, None


def _dedupe_assets(
    candidates: List[Dict[str, Any]],
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Deduplikuje assety podle fingerprints.
    
    Returns:
        (unique_assets[], dedupe_report)
    """
    seen_fingerprints: Set[str] = set()
    unique_assets = []
    duplicates_removed = 0
    
    for asset in candidates:
        fp = _asset_fingerprint(asset)
        if not fp:
            # Skip assets bez fingerprints (low quality)
            duplicates_removed += 1
            continue
        
        if fp in seen_fingerprints:
            duplicates_removed += 1
            if verbose:
                print(f"   - Duplicate detected: {fp} (title: {asset.get('title', 'N/A')[:50]})")
            continue
        
        seen_fingerprints.add(fp)
        unique_assets.append(asset)
    
    dedupe_report = {
        "total_candidates": len(candidates),
        "unique_assets": len(unique_assets),
        "duplicates_removed": duplicates_removed,
        "deduplication_rate": round(duplicates_removed / max(1, len(candidates)), 3),
    }
    
    return unique_assets, dedupe_report


def _rank_assets(
    assets: List[Dict[str, Any]],
    coverage_requirements: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Rankuje assety podle combined score.
    
    Combined score = relevance * 0.6 + quality * 0.4
    """
    ranked = []
    
    for i, asset in enumerate(assets):
        relevance = _relevance_score(asset)
        quality = _quality_score(asset)
        combined_score = relevance * 0.6 + quality * 0.4
        
        # Add ranking metadata
        ranked_asset = dict(asset)
        ranked_asset["global_rank"] = i + 1  # Will be re-ranked after sorting
        ranked_asset["global_score"] = round(combined_score, 3)
        ranked_asset["relevance_score"] = round(relevance, 3)
        ranked_asset["quality_score"] = round(quality, 3)
        
        ranked.append(ranked_asset)
    
    # Sort by global_score (desc)
    ranked.sort(key=lambda x: -x["global_score"])
    
    # Re-assign global_rank after sorting
    for i, asset in enumerate(ranked, start=1):
        asset["global_rank"] = i
    
    return ranked


def _analyze_coverage(
    curated_assets: List[Dict[str, Any]],
    coverage_requirements: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Analyzuje coverage balance a deficity.
    
    Returns:
        (coverage_balance, deficits[])
    """
    # Count assets by visual_type
    by_visual_type: Dict[str, int] = defaultdict(int)
    for asset in curated_assets:
        vt = asset.get("visual_type", "general")
        by_visual_type[vt] += 1
    
    # Required visual types
    required_vts = coverage_requirements.get("required_visual_types", {})
    
    # Check deficits
    deficits = []
    for vt, req in required_vts.items():
        min_assets = req.get("min_assets", 2)
        actual = by_visual_type.get(vt, 0)
        
        if actual < min_assets:
            deficits.append({
                "visual_type": vt,
                "required": min_assets,
                "actual": actual,
                "deficit": min_assets - actual,
                "severity": "critical" if actual == 0 else "warning",
            })
    
    # Coverage balance summary
    coverage_balance = {
        "by_visual_type": dict(by_visual_type),
        "total_curated_assets": len(curated_assets),
        "coverage_status": "adequate" if not deficits else "deficient",
    }
    
    return coverage_balance, deficits


def _recommend_scenes_for_assets(
    curated_assets: List[Dict[str, Any]],
    shot_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Pro každý asset doporučí scény kde by mohl být použit.
    
    Založeno na:
    - visual_type match s shot_types
    - query match (pokud asset má query_source_id)
    """
    scenes = shot_plan.get("scenes", [])
    
    # Build scene → shot_types mapping
    scene_shot_types: Dict[str, List[str]] = {}
    for scene in scenes:
        scene_id = scene.get("scene_id", "")
        shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
        scene_shot_types[scene_id] = shot_types
    
    # Recommend scenes for each asset
    for asset in curated_assets:
        vt = asset.get("visual_type", "general")
        recommended_scenes = []
        
        # Simple heuristic: match visual_type with shot_types
        for scene_id, shot_types in scene_shot_types.items():
            # Convert shot_types to visual_types
            scene_vts = set()
            for st in shot_types:
                if "map" in st:
                    scene_vts.add("map")
                elif "document" in st:
                    scene_vts.add("document")
                elif "leader" in st or "speech" in st:
                    scene_vts.add("portrait")
                elif "destruction" in st:
                    scene_vts.add("destruction")
                elif "troop" in st or "movement" in st:
                    scene_vts.add("military_action")
                else:
                    scene_vts.add("general")
            
            if vt in scene_vts:
                recommended_scenes.append(scene_id)
        
        asset["recommended_scenes"] = recommended_scenes
        asset["reasoning"] = f"Visual type '{vt}' matches {len(recommended_scenes)} scene(s)"
    
    return curated_assets


def run_visual_curator(
    aar_raw_results: Dict[str, Any],
    shot_plan: Dict[str, Any],
    coverage_requirements: Dict[str, Any],
    episode_id: str,
    output_path: str,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """
    Hlavní entry point pro Visual Curator.
    
    Args:
        aar_raw_results: Raw results z AAR (všechny kandidáti)
        shot_plan: Shot plan z FDA (pro scene matching)
        coverage_requirements: Z Query Director
        episode_id: ID epizody
        output_path: Cesta kam uložit visual_curator_output.json
        verbose: Logování detailů
    
    Returns:
        (output_dict, output_file_path)
    """
    if verbose:
        print(f"🎨 Visual Curator: Starting for episode {episode_id}")
    
    # 1. Extract candidates from AAR raw results
    candidates = []
    results_by_query = aar_raw_results.get("results_by_query", [])
    
    for query_result in results_by_query:
        query_id = query_result.get("query_id", "")
        results = query_result.get("results", [])
        
        for result in results:
            # Enrich with query context
            asset = dict(result)
            asset["query_source_id"] = query_id
            candidates.append(asset)
    
    if verbose:
        print(f"   - Total candidates: {len(candidates)}")
    
    # 2. Filter out low quality
    filtered_candidates = []
    low_quality_count = 0
    rejection_reasons: Dict[str, int] = defaultdict(int)
    
    for asset in candidates:
        is_low, reason = _is_low_quality(asset)
        if is_low:
            low_quality_count += 1
            if reason:
                rejection_reasons[reason] += 1
        else:
            filtered_candidates.append(asset)
    
    if verbose:
        print(f"   - Low quality rejected: {low_quality_count}")
        print(f"   - Filtered candidates: {len(filtered_candidates)}")
    
    # 3. Dedupe assets
    unique_assets, dedupe_report = _dedupe_assets(filtered_candidates, verbose=verbose)
    
    if verbose:
        print(f"   - Unique assets after dedupe: {len(unique_assets)}")
    
    # 4. Rank assets
    ranked_assets = _rank_assets(unique_assets, coverage_requirements)
    
    if verbose:
        print(f"   - Ranked assets: {len(ranked_assets)}")
        if ranked_assets:
            print(f"   - Top asset score: {ranked_assets[0]['global_score']}")
    
    # 5. Recommend scenes for assets
    curated_assets = _recommend_scenes_for_assets(ranked_assets, shot_plan)
    
    # 6. Analyze coverage
    coverage_balance, deficits = _analyze_coverage(curated_assets, coverage_requirements)
    
    if verbose:
        print(f"   - Coverage status: {coverage_balance['coverage_status']}")
        if deficits:
            print(f"   - Deficits detected: {len(deficits)}")
            for d in deficits:
                print(f"     * {d['visual_type']}: {d['actual']}/{d['required']} ({d['severity']})")
    
    # 7. Build output
    output = {
        "version": VERSION,
        "episode_id": episode_id,
        "generated_at": _now_iso(),
        "curated_assets": curated_assets,
        "dedupe_report": dedupe_report,
        "quality_report": {
            "total_candidates": len(candidates),
            "low_quality_rejected": low_quality_count,
            "rejection_reasons": dict(rejection_reasons),
            "filtered_candidates": len(filtered_candidates),
            "final_curated_count": len(curated_assets),
        },
        "coverage_balance": coverage_balance,
        "deficits": deficits,
    }
    
    # 8. Write to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"✅ Visual Curator: Output saved to {output_path}")
    
    return output, output_path


def load_visual_curator_output(file_path: str) -> Dict[str, Any]:
    """Helper: načte Visual Curator output z JSON souboru"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Simple test
    test_aar_raw = {
        "version": "aar_raw_v1",
        "episode_id": "test_ep",
        "results_by_query": [
            {
                "query_id": "q_001",
                "query": "Napoleon 1812 map",
                "results": [
                    {
                        "archive_item_id": "item_001",
                        "asset_url": "https://archive.org/details/item_001",
                        "title": "Map of Napoleon's 1812 Campaign",
                        "media_type": "image",
                        "source": "archive_org",
                        "thumbnail_url": "https://archive.org/thumb/item_001",
                        "topic_relevance_score": 0.85,
                        "visual_type": "map",
                    },
                    {
                        "archive_item_id": "item_001",  # duplicate
                        "asset_url": "https://archive.org/details/item_001",
                        "title": "Map of Napoleon's 1812 Campaign",
                        "media_type": "image",
                        "source": "archive_org",
                        "thumbnail_url": "https://archive.org/thumb/item_001",
                        "topic_relevance_score": 0.85,
                        "visual_type": "map",
                    },
                ],
            },
        ],
    }
    
    test_shot_plan = {
        "scenes": [
            {
                "scene_id": "sc_0001",
                "shot_strategy": {"shot_types": ["maps_context"]},
            },
        ],
    }
    
    test_coverage_req = {
        "required_visual_types": {
            "map": {"min_assets": 2, "reason": "Test"},
        },
    }
    
    output, path = run_visual_curator(
        test_aar_raw,
        test_shot_plan,
        test_coverage_req,
        episode_id="test_ep",
        output_path="/tmp/visual_curator_output.json",
        verbose=True,
    )
    
    print("\n✅ Visual Curator test completed")
    print(f"   Curated assets: {len(output['curated_assets'])}")
    print(f"   Dedupe report: {output['dedupe_report']}")


