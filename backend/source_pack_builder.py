"""
Source Pack Builder - Deterministické sestavení source pack pro CB

Účel:
- Načte visual_curator_output.json (curated assets)
- Přiřadí assety do scén (primary/secondary/texture)
- Enforce cross-scene dedupe (žádný asset 2x ve více scénách)
- Vytvoří fallback pools pro scény s nedostatkem materiálu
- Generuje source_pack.json pro CB

Výstup: source_pack.json
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict


VERSION = "source_pack_v1"


def _now_iso() -> str:
    """ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _create_episode_asset_pool(
    curated_assets: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Vytvoří episode-level asset pool z curated assets.
    
    Přidá metadata pro tracking:
    - asset_id (unique)
    - used_in_scenes[] (tracking cross-scene usage)
    """
    pool = []
    
    for i, asset in enumerate(curated_assets, start=1):
        pool_asset = dict(asset)
        pool_asset["asset_id"] = f"asset_{i:04d}"
        pool_asset["used_in_scenes"] = []  # Will be populated during assignment
        pool.append(pool_asset)
    
    return pool


def _match_assets_to_scene(
    scene: Dict[str, Any],
    asset_pool: List[Dict[str, Any]],
    used_asset_ids: Set[str],
    min_assets_per_scene: int = 2,
) -> List[Dict[str, Any]]:
    """
    Přiřadí assety do scény na základě recommended_scenes.
    
    Args:
        scene: Scene dict z shot_plan
        asset_pool: Episode asset pool
        used_asset_ids: Set už použitých asset_id (cross-scene tracking)
        min_assets_per_scene: Minimální počet assetů na scénu
    
    Returns:
        assigned_assets[] (sorted by global_rank)
    """
    scene_id = scene.get("scene_id", "")
    
    # Filter eligible assets (not yet used + recommended for this scene)
    eligible = []
    for asset in asset_pool:
        asset_id = asset.get("asset_id", "")
        if asset_id in used_asset_ids:
            continue
        
        recommended = asset.get("recommended_scenes", [])
        if scene_id in recommended:
            eligible.append(asset)
    
    # Sort by global_rank (best first)
    eligible.sort(key=lambda x: x.get("global_rank", 9999))
    
    # Assign assets
    assigned = []
    for asset in eligible:
        assigned.append(asset)
        if len(assigned) >= min_assets_per_scene:
            break
    
    return assigned


def _classify_asset_role(
    asset: Dict[str, Any],
    rank_in_scene: int,
) -> str:
    """
    Klasifikuje roli assetu ve scéně.
    
    Roles:
    - primary: rank 1 (main visual)
    - secondary: rank 2-3 (alternates)
    - texture: rank 4+ (b-roll, filler)
    """
    if rank_in_scene == 1:
        return "primary"
    elif rank_in_scene <= 3:
        return "secondary"
    else:
        return "texture"


def _assign_assets_to_scenes(
    shot_plan: Dict[str, Any],
    asset_pool: List[Dict[str, Any]],
    min_assets_per_scene: int = 2,
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Přiřadí assety do scén s cross-scene dedupe enforcement.
    
    Returns:
        (scene_assignments[], assignment_report)
    """
    scenes = shot_plan.get("scenes", [])
    used_asset_ids: Set[str] = set()
    scene_assignments = []
    
    # Stats
    total_assigned = 0
    scenes_with_deficit = 0
    
    for scene in scenes:
        scene_id = scene.get("scene_id", "")
        
        # Match assets
        assigned = _match_assets_to_scene(
            scene,
            asset_pool,
            used_asset_ids,
            min_assets_per_scene,
        )
        
        if len(assigned) < min_assets_per_scene:
            scenes_with_deficit += 1
        
        # Mark assets as used
        for asset in assigned:
            asset_id = asset.get("asset_id", "")
            used_asset_ids.add(asset_id)
            asset["used_in_scenes"].append(scene_id)
        
        # Classify roles
        primary_assets = []
        secondary_assets = []
        texture_assets = []
        
        for i, asset in enumerate(assigned, start=1):
            role = _classify_asset_role(asset, i)
            
            asset_ref = {
                "asset_id": asset.get("asset_id"),
                "archive_item_id": asset.get("archive_item_id"),
                "asset_url": asset.get("asset_url"),
                "media_type": asset.get("media_type"),
                "visual_type": asset.get("visual_type"),
                "global_rank": asset.get("global_rank"),
                "global_score": asset.get("global_score"),
                "role": role,
            }
            
            if role == "primary":
                primary_assets.append(asset_ref)
            elif role == "secondary":
                secondary_assets.append(asset_ref)
            else:
                texture_assets.append(asset_ref)
        
        total_assigned += len(assigned)
        
        # Build scene assignment
        scene_assignment = {
            "scene_id": scene_id,
            "start_sec": scene.get("start_sec", 0),
            "end_sec": scene.get("end_sec", 0),
            "duration_sec": scene.get("end_sec", 0) - scene.get("start_sec", 0),
            "primary_assets": primary_assets,
            "secondary_assets": secondary_assets,
            "texture_assets": texture_assets,
            "total_assets": len(assigned),
            "has_deficit": len(assigned) < min_assets_per_scene,
        }
        
        scene_assignments.append(scene_assignment)
        
        if verbose:
            status = "✅" if len(assigned) >= min_assets_per_scene else "⚠️"
            print(f"   {status} {scene_id}: {len(assigned)} asset(s) assigned")
    
    assignment_report = {
        "total_scenes": len(scenes),
        "total_assets_assigned": total_assigned,
        "scenes_with_deficit": scenes_with_deficit,
        "average_assets_per_scene": round(total_assigned / max(1, len(scenes)), 2),
    }
    
    return scene_assignments, assignment_report


def _create_fallback_pools(
    asset_pool: List[Dict[str, Any]],
    scene_assignments: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Vytvoří fallback pools pro scény s deficitem.
    
    Pools:
    - texture_pool: Safe b-roll assety (používají se když scéna nemá dost assetů)
    - emergency_pool: Last-resort assety (když texture pool není dost)
    """
    # Unused assets (not assigned to any scene)
    used_asset_ids = set()
    for scene in scene_assignments:
        for asset_list in [scene["primary_assets"], scene["secondary_assets"], scene["texture_assets"]]:
            for asset in asset_list:
                used_asset_ids.add(asset.get("asset_id", ""))
    
    unused_assets = [a for a in asset_pool if a.get("asset_id", "") not in used_asset_ids]
    
    # Sort by global_rank (best unused assets first)
    unused_assets.sort(key=lambda x: x.get("global_rank", 9999))
    
    # Texture pool: top 5 unused
    texture_pool = []
    for asset in unused_assets[:5]:
        texture_pool.append({
            "asset_id": asset.get("asset_id"),
            "archive_item_id": asset.get("archive_item_id"),
            "asset_url": asset.get("asset_url"),
            "media_type": asset.get("media_type"),
            "visual_type": asset.get("visual_type"),
            "global_rank": asset.get("global_rank"),
            "usage_note": "texture_fallback",
        })
    
    # Emergency pool: next 3 unused
    emergency_pool = []
    for asset in unused_assets[5:8]:
        emergency_pool.append({
            "asset_id": asset.get("asset_id"),
            "archive_item_id": asset.get("archive_item_id"),
            "asset_url": asset.get("asset_url"),
            "media_type": asset.get("media_type"),
            "visual_type": asset.get("visual_type"),
            "global_rank": asset.get("global_rank"),
            "usage_note": "emergency_fallback",
        })
    
    return {
        "texture_pool": texture_pool,
        "emergency_pool": emergency_pool,
    }


def _validate_source_pack(
    scene_assignments: List[Dict[str, Any]],
    episode_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Validuje source pack podle quality guardrails.
    
    Kontroly:
    1. Žádná scéna nemá méně než 1 asset (hard fail)
    2. Cross-scene duplicate enforcement (hard fail)
    3. Preferovaně min 2 assety na scénu (warning)
    
    Returns:
        warnings[]
    """
    warnings = []
    
    # Check 1: Min 1 asset per scene
    for scene in scene_assignments:
        scene_id = scene.get("scene_id", "")
        total = scene.get("total_assets", 0)
        
        if total < 1:
            warnings.append({
                "code": "SP_SCENE_NO_ASSETS",
                "message": f"Scene {scene_id} has 0 assets",
                "severity": "critical",
            })
        elif total < 2:
            warnings.append({
                "code": "SP_SCENE_MIN_ASSETS",
                "message": f"Scene {scene_id} has only {total} asset (recommended 2+)",
                "severity": "warning",
            })
    
    # Check 2: Cross-scene duplicate detection
    asset_id_usage: Dict[str, List[str]] = defaultdict(list)
    
    for scene in scene_assignments:
        scene_id = scene.get("scene_id", "")
        for asset_list in [scene["primary_assets"], scene["secondary_assets"], scene["texture_assets"]]:
            for asset in asset_list:
                asset_id = asset.get("asset_id", "")
                if asset_id:
                    asset_id_usage[asset_id].append(scene_id)
    
    for asset_id, scenes_using in asset_id_usage.items():
        if len(scenes_using) > 1:
            warnings.append({
                "code": "SP_CROSS_SCENE_DUPLICATE",
                "message": f"Asset {asset_id} used in multiple scenes: {scenes_using}",
                "severity": "critical",
            })
    
    return warnings


def _generate_coverage_summary(
    scene_assignments: List[Dict[str, Any]],
    asset_pool: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Generuje coverage summary pro reporting.
    """
    # Total assets in pool
    total_pool = len(asset_pool)
    
    # Assets assigned
    used_asset_ids = set()
    for scene in scene_assignments:
        for asset_list in [scene["primary_assets"], scene["secondary_assets"], scene["texture_assets"]]:
            for asset in asset_list:
                used_asset_ids.add(asset.get("asset_id", ""))
    
    total_used = len(used_asset_ids)
    
    # Assets by visual type
    by_visual_type: Dict[str, int] = defaultdict(int)
    for asset in asset_pool:
        if asset.get("asset_id", "") in used_asset_ids:
            vt = asset.get("visual_type", "general")
            by_visual_type[vt] += 1
    
    return {
        "total_pool_assets": total_pool,
        "total_assigned_assets": total_used,
        "unused_assets": total_pool - total_used,
        "usage_rate": round(total_used / max(1, total_pool), 3),
        "assets_by_visual_type": dict(by_visual_type),
    }


def run_source_pack_builder(
    visual_curator_output: Dict[str, Any],
    shot_plan: Dict[str, Any],
    episode_id: str,
    output_path: str,
    min_assets_per_scene: int = 2,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """
    Hlavní entry point pro Source Pack Builder.
    
    Args:
        visual_curator_output: Output z Visual Curator
        shot_plan: Shot plan z FDA
        episode_id: ID epizody
        output_path: Cesta kam uložit source_pack.json
        min_assets_per_scene: Min počet assetů na scénu (default 2)
        verbose: Logování detailů
    
    Returns:
        (output_dict, output_file_path)
    """
    if verbose:
        print(f"📦 Source Pack Builder: Starting for episode {episode_id}")
    
    # 1. Create episode asset pool
    curated_assets = visual_curator_output.get("curated_assets", [])
    asset_pool = _create_episode_asset_pool(curated_assets)
    
    if verbose:
        print(f"   - Asset pool size: {len(asset_pool)}")
    
    # 2. Assign assets to scenes
    scene_assignments, assignment_report = _assign_assets_to_scenes(
        shot_plan,
        asset_pool,
        min_assets_per_scene,
        verbose=verbose,
    )
    
    if verbose:
        print(f"   - Total assigned: {assignment_report['total_assets_assigned']}")
        print(f"   - Avg per scene: {assignment_report['average_assets_per_scene']:.1f}")
        if assignment_report['scenes_with_deficit'] > 0:
            print(f"   - Scenes with deficit: {assignment_report['scenes_with_deficit']}")
    
    # 3. Create fallback pools
    fallback_pools = _create_fallback_pools(asset_pool, scene_assignments)
    
    if verbose:
        print(f"   - Texture pool: {len(fallback_pools['texture_pool'])} assets")
        print(f"   - Emergency pool: {len(fallback_pools['emergency_pool'])} assets")
    
    # 4. Validate source pack
    warnings = _validate_source_pack(scene_assignments, episode_id)
    
    if warnings and verbose:
        print(f"   - Validation warnings: {len(warnings)}")
        for w in warnings:
            print(f"     * {w['code']}: {w['message']} [{w['severity']}]")
    
    # 5. Generate coverage summary
    coverage_summary = _generate_coverage_summary(scene_assignments, asset_pool)
    
    # 6. Build output
    output = {
        "version": VERSION,
        "episode_id": episode_id,
        "generated_at": _now_iso(),
        "episode_asset_pool": asset_pool,
        "scene_assignments": scene_assignments,
        "coverage_summary": coverage_summary,
        "provenance": {
            "visual_curator_version": visual_curator_output.get("version"),
            "shot_plan_version": shot_plan.get("version"),
            "curated_assets_count": len(curated_assets),
        },
        "fallback_pools": fallback_pools,
        "warnings": warnings,
    }
    
    # 7. Write to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"✅ Source Pack Builder: Output saved to {output_path}")
    
    return output, output_path


def load_source_pack(file_path: str) -> Dict[str, Any]:
    """Helper: načte Source Pack z JSON souboru"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Simple test
    test_vc_output = {
        "version": "visual_curator_v1",
        "episode_id": "test_ep",
        "curated_assets": [
            {
                "archive_item_id": "item_001",
                "asset_url": "https://archive.org/details/item_001",
                "title": "Napoleon Map",
                "media_type": "image",
                "visual_type": "map",
                "global_rank": 1,
                "global_score": 0.85,
                "recommended_scenes": ["sc_0001"],
            },
            {
                "archive_item_id": "item_002",
                "asset_url": "https://archive.org/details/item_002",
                "title": "Moscow Fire Document",
                "media_type": "image",
                "visual_type": "document",
                "global_rank": 2,
                "global_score": 0.78,
                "recommended_scenes": ["sc_0001", "sc_0002"],
            },
        ],
    }
    
    test_shot_plan = {
        "version": "shotplan_v3",
        "scenes": [
            {
                "scene_id": "sc_0001",
                "start_sec": 0,
                "end_sec": 10,
                "shot_strategy": {"shot_types": ["maps_context"]},
            },
            {
                "scene_id": "sc_0002",
                "start_sec": 10,
                "end_sec": 20,
                "shot_strategy": {"shot_types": ["archival_documents"]},
            },
        ],
    }
    
    output, path = run_source_pack_builder(
        test_vc_output,
        test_shot_plan,
        episode_id="test_ep",
        output_path="/tmp/source_pack.json",
        verbose=True,
    )
    
    print("\n✅ Source Pack Builder test completed")
    print(f"   Scene assignments: {len(output['scene_assignments'])}")
    print(f"   Coverage summary: {output['coverage_summary']}")


