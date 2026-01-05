"""
Query Director - Strategický plánovač vizuálních dotazů

Účel:
- Analyzuje shot_plan.json z FDA
- Deduplikuje redundantní queries cross-scene
- Vytváří strategické dotazy s prioritami
- Generuje coverage requirements a plán

Výstup: query_director_output.json
"""

import json
import hashlib
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict


VERSION = "query_director_v1"


def _now_iso() -> str:
    """ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_query(q: str) -> str:
    """Normalizace pro deduplikaci (lowercase, whitespace)"""
    return " ".join(q.lower().strip().split())


def _query_hash(q: str) -> str:
    """Stable hash pro query identity"""
    normalized = _normalize_query(q)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _extract_visual_type(shot_types: List[str]) -> str:
    """
    Určí primární visual type ze shot_types.
    
    Priority (od nejvíce specifických):
    1. maps_context → "map"
    2. archival_documents → "document"
    3. leaders_speeches → "portrait"
    4. destruction_aftermath → "destruction"
    5. troop_movement → "military_action"
    6. ostatní → "general"
    """
    st_set = {str(st).strip().lower() for st in shot_types if st}
    
    if "maps_context" in st_set:
        return "map"
    elif "archival_documents" in st_set:
        return "document"
    elif "leaders_speeches" in st_set:
        return "portrait"
    elif "destruction_aftermath" in st_set:
        return "destruction"
    elif "troop_movement" in st_set:
        return "military_action"
    elif "civilian_life" in st_set:
        return "civilian"
    elif "industry_war_effort" in st_set:
        return "industrial"
    else:
        return "general"


def _calculate_priority(
    query: str,
    visual_type: str,
    num_scenes: int,
    shot_types: List[str],
) -> int:
    """
    Vypočítá prioritu dotazu (1-10, 10=highest).
    
    Pravidla:
    - Mapy: priorita 9-10 (omezit počet)
    - Dokumenty: priorita 7-9 (backbone)
    - Portraits: priorita 6-8 (variety)
    - Destruction/action: priorita 5-7 (dramatic)
    - General: priorita 3-5 (filler)
    """
    base_priority = 5
    
    if visual_type == "map":
        # GUARD: Omezit map queries (high temptation risk)
        base_priority = 9
    elif visual_type == "document":
        base_priority = 8
    elif visual_type == "portrait":
        base_priority = 7
    elif visual_type in ("destruction", "military_action"):
        base_priority = 6
    elif visual_type == "civilian":
        base_priority = 5
    else:
        base_priority = 4
    
    # Boost pokud je to jediná query pro tento typ
    if num_scenes == 1:
        base_priority = min(10, base_priority + 1)
    
    return base_priority


def _dedupe_queries_cross_scene(
    shot_plan: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Deduplikuje queries cross-scene a vytvoří strategické dotazy.
    
    Returns:
        (strategic_queries[], dedupe_report)
    """
    scenes = shot_plan.get("scenes", [])
    if not scenes:
        return [], {"total_raw_queries": 0, "duplicates_removed": 0, "strategic_queries": 0}
    
    # Collector: query → {scenes[], shot_types[], first_scene_id}
    query_map: Dict[str, Dict[str, Any]] = {}
    total_raw = 0
    
    for scene in scenes:
        scene_id = scene.get("scene_id", "unknown")
        search_queries = scene.get("search_queries", [])
        shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
        
        for q in search_queries:
            q_str = str(q).strip()
            if not q_str:
                continue
            
            total_raw += 1
            q_norm = _normalize_query(q_str)
            q_hash = _query_hash(q_str)
            
            if q_hash not in query_map:
                query_map[q_hash] = {
                    "query": q_str,  # Preserve original casing
                    "scenes": [],
                    "shot_types": set(),
                    "first_scene_id": scene_id,
                }
            
            query_map[q_hash]["scenes"].append(scene_id)
            for st in shot_types:
                query_map[q_hash]["shot_types"].add(str(st).strip())
    
    # Build strategic queries
    strategic_queries = []
    query_counter = 1
    
    for q_hash, info in query_map.items():
        query_str = info["query"]
        scenes_using = info["scenes"]
        shot_types_list = sorted(list(info["shot_types"]))
        
        visual_type = _extract_visual_type(shot_types_list)
        priority = _calculate_priority(
            query_str,
            visual_type,
            len(scenes_using),
            shot_types_list,
        )
        
        # Reasoning pro transparency
        reasoning = f"Used by {len(scenes_using)} scene(s), visual_type={visual_type}"
        
        strategic_queries.append({
            "query_id": f"q_{query_counter:03d}",
            "query": query_str,
            "priority": priority,
            "visual_type": visual_type,
            "intended_scenes": scenes_using,
            "reasoning": reasoning,
        })
        query_counter += 1
    
    # Sort by priority (desc), then by query_id
    strategic_queries.sort(key=lambda x: (-x["priority"], x["query_id"]))
    
    # Dedupe report
    duplicates_removed = total_raw - len(strategic_queries)
    dedupe_report = {
        "total_raw_queries": total_raw,
        "duplicates_removed": duplicates_removed,
        "strategic_queries": len(strategic_queries),
        "deduplication_rate": round(duplicates_removed / max(1, total_raw), 3),
    }
    
    return strategic_queries, dedupe_report


def _generate_coverage_requirements(
    shot_plan: Dict[str, Any],
    strategic_queries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Analyzuje coverage requirements z shot types.
    
    Returns:
        {
            "required_visual_types": {
                "map": {"min_assets": N, "reason": str},
                ...
            },
            "diversity_targets": {...},
        }
    """
    scenes = shot_plan.get("scenes", [])
    
    # Count shot_types frequency
    shot_type_freq: Dict[str, int] = defaultdict(int)
    for scene in scenes:
        shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
        for st in shot_types:
            shot_type_freq[str(st).strip()] += 1
    
    # Map to visual types
    visual_type_demand: Dict[str, int] = defaultdict(int)
    for st, freq in shot_type_freq.items():
        vt = _extract_visual_type([st])
        visual_type_demand[vt] += freq
    
    # Required visual types (at least 2 assets per type if demanded by 2+ scenes)
    required_visual_types = {}
    for vt, demand in visual_type_demand.items():
        if demand >= 2:
            required_visual_types[vt] = {
                "min_assets": max(2, min(5, demand)),
                "reason": f"Requested by {demand} scene(s)",
            }
    
    # Diversity targets
    total_scenes = len(scenes)
    diversity_targets = {
        "min_unique_items": min(10, total_scenes * 2),  # At least 2 per scene
        "max_reuse_per_item": 2,  # Same asset max 2x across all scenes
        "cross_scene_duplicate_tolerance": 0,  # ZERO cross-scene duplicates
    }
    
    return {
        "required_visual_types": required_visual_types,
        "diversity_targets": diversity_targets,
    }


def _generate_coverage_plan(
    strategic_queries: List[Dict[str, Any]],
    coverage_requirements: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Vytvoří coverage plán - mapování visual_type → queries.
    """
    # Group queries by visual_type
    by_visual_type: Dict[str, List[str]] = defaultdict(list)
    for sq in strategic_queries:
        vt = sq.get("visual_type", "general")
        by_visual_type[vt].append(sq["query_id"])
    
    # Coverage plan
    coverage_plan = {
        "queries_by_visual_type": dict(by_visual_type),
        "expected_coverage": {},
    }
    
    # Expected coverage pro každý visual type
    required_vts = coverage_requirements.get("required_visual_types", {})
    for vt, req in required_vts.items():
        query_count = len(by_visual_type.get(vt, []))
        coverage_plan["expected_coverage"][vt] = {
            "min_assets_required": req.get("min_assets", 2),
            "queries_available": query_count,
            "status": "adequate" if query_count >= 2 else "deficit",
        }
    
    return coverage_plan


def _validate_strategic_queries(
    strategic_queries: List[Dict[str, Any]],
    episode_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Quality guardrails pro Query Director output.
    
    Kontroluje:
    1. Query count limit (≤ 8 pro epizodu)
    2. Map query temptation (max 20% map queries)
    3. Duplicate queries (< 10%)
    
    Returns:
        warnings[] (může být prázdný)
    """
    warnings = []
    total_queries = len(strategic_queries)
    
    # GUARD 1: Query count limit
    if total_queries > 8:
        warnings.append({
            "code": "QD_TOO_MANY_QUERIES",
            "message": f"Strategic queries count ({total_queries}) exceeds recommended limit (8)",
            "severity": "warning",
        })
    
    # GUARD 2: Map query temptation
    map_queries = [sq for sq in strategic_queries if sq.get("visual_type") == "map"]
    if len(map_queries) > total_queries * 0.2:
        warnings.append({
            "code": "QD_MAP_TEMPTATION_HIGH",
            "message": f"Map queries ({len(map_queries)}) exceed 20% threshold",
            "severity": "warning",
        })
    
    # GUARD 3: Duplicate detection (by normalized query string)
    seen_norms: Set[str] = set()
    duplicates = 0
    for sq in strategic_queries:
        q_norm = _normalize_query(sq.get("query", ""))
        if q_norm in seen_norms:
            duplicates += 1
        seen_norms.add(q_norm)
    
    dup_rate = duplicates / max(1, total_queries)
    if dup_rate > 0.1:
        warnings.append({
            "code": "QD_DUPLICATE_QUERIES_HIGH",
            "message": f"Duplicate query rate ({dup_rate:.1%}) exceeds 10% threshold",
            "severity": "error",
        })
    
    return warnings


def run_query_director(
    shot_plan: Dict[str, Any],
    episode_id: str,
    output_path: str,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """
    Hlavní entry point pro Query Director.
    
    Args:
        shot_plan: Shot plan z FDA (má scenes[] s search_queries[])
        episode_id: ID epizody
        output_path: Cesta kam uložit query_director_output.json
        verbose: Logování detailů
    
    Returns:
        (output_dict, output_file_path)
    """
    if verbose:
        print(f"🎯 Query Director: Starting for episode {episode_id}")
    
    # Unwrap shot_plan if wrapped
    if isinstance(shot_plan.get("shot_plan"), dict):
        shot_plan = shot_plan["shot_plan"]
    
    # 1. Dedupe queries cross-scene
    strategic_queries, dedupe_report = _dedupe_queries_cross_scene(shot_plan, episode_id)
    
    if verbose:
        print(f"   - Raw queries: {dedupe_report['total_raw_queries']}")
        print(f"   - Strategic queries: {dedupe_report['strategic_queries']}")
        print(f"   - Deduplication rate: {dedupe_report['deduplication_rate']:.1%}")
    
    # 2. Generate coverage requirements
    coverage_requirements = _generate_coverage_requirements(shot_plan, strategic_queries)
    
    if verbose:
        print(f"   - Required visual types: {len(coverage_requirements['required_visual_types'])}")
    
    # 3. Generate coverage plan
    coverage_plan = _generate_coverage_plan(strategic_queries, coverage_requirements)
    
    # 4. Validate (quality guardrails)
    warnings = _validate_strategic_queries(strategic_queries, episode_id)
    
    if warnings and verbose:
        print(f"   - Warnings: {len(warnings)}")
        for w in warnings:
            print(f"     * {w['code']}: {w['message']}")
    
    # 5. Build output
    output = {
        "version": VERSION,
        "episode_id": episode_id,
        "generated_at": _now_iso(),
        "coverage_requirements": coverage_requirements,
        "strategic_queries": strategic_queries,
        "dedupe_report": dedupe_report,
        "coverage_plan": coverage_plan,
        "warnings": warnings,
    }
    
    # 6. Write to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"✅ Query Director: Output saved to {output_path}")
    
    return output, output_path


def load_query_director_output(file_path: str) -> Dict[str, Any]:
    """Helper: načte Query Director output z JSON souboru"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Simple test
    test_shot_plan = {
        "version": "shotplan_v3",
        "scenes": [
            {
                "scene_id": "sc_0001",
                "search_queries": [
                    "Napoleon 1812 map",
                    "Moscow 1812 map",
                    "Grande Armée map",
                ],
                "shot_strategy": {"shot_types": ["maps_context", "troop_movement"]},
            },
            {
                "scene_id": "sc_0002",
                "search_queries": [
                    "Napoleon 1812 map",  # duplicate
                    "Moscow fire 1812 documents",
                    "Russian winter 1812 painting",
                ],
                "shot_strategy": {"shot_types": ["archival_documents", "destruction_aftermath"]},
            },
        ],
    }
    
    output, path = run_query_director(
        test_shot_plan,
        episode_id="test_ep",
        output_path="/tmp/query_director_output.json",
        verbose=True,
    )
    
    print("\n✅ Query Director test completed")
    print(f"   Strategic queries: {len(output['strategic_queries'])}")
    print(f"   Dedupe report: {output['dedupe_report']}")


