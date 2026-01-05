"""
CB v2 - Compilation Builder s Source Pack podporou

Rozšíření CB o schopnost číst source_pack.json místo archive_manifest.json.

Konverze:
- source_pack.json → archive_manifest.json (legacy format)
- scene_assignments → scenes s assets[]
- Použije fallback pools kde je deficit
"""

import json
import os
from typing import Dict, List, Any, Optional, Tuple


def convert_source_pack_to_manifest(
    source_pack: Dict[str, Any],
    shot_plan: Dict[str, Any],
    output_path: str,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """
    Převede source_pack.json na archive_manifest.json formát.
    
    Args:
        source_pack: Source pack z Source Pack Builder
        shot_plan: Shot plan z FDA (pro compile_plan a scene metadata)
        output_path: Cesta kam uložit archive_manifest.json
        verbose: Logování detailů
    
    Returns:
        (manifest_dict, manifest_file_path)
    """
    if verbose:
        print("🔄 CB v2: Converting source pack to manifest...")
    
    # Extract data
    scene_assignments = source_pack.get("scene_assignments", [])
    fallback_pools = source_pack.get("fallback_pools", {})
    texture_pool = fallback_pools.get("texture_pool", [])
    
    # Build compile_plan (from shot_plan or defaults)
    sp = shot_plan if isinstance(shot_plan, dict) else {}
    if isinstance(shot_plan.get("shot_plan"), dict):
        sp = shot_plan["shot_plan"]
    
    compile_plan = {
        "target_fps": 30,
        "resolution": "1920x1080",
        "total_duration_sec": sp.get("total_duration_sec", 0),
    }
    
    # Convert scene_assignments to manifest scenes
    manifest_scenes = []
    
    for sa in scene_assignments:
        scene_id = sa.get("scene_id", "")
        
        # Collect all assets (primary + secondary + texture)
        all_assets = []
        
        for asset_ref in sa.get("primary_assets", []):
            all_assets.append(_convert_asset_ref(asset_ref, priority="primary"))
        
        for asset_ref in sa.get("secondary_assets", []):
            all_assets.append(_convert_asset_ref(asset_ref, priority="secondary"))
        
        for asset_ref in sa.get("texture_assets", []):
            all_assets.append(_convert_asset_ref(asset_ref, priority="texture"))
        
        # If deficit, add from texture pool
        if sa.get("has_deficit", False) and texture_pool:
            if verbose:
                print(f"   - {scene_id}: Using texture pool (deficit)")
            
            for tex_asset in texture_pool[:2]:  # Add max 2 from pool
                all_assets.append(_convert_asset_ref(tex_asset, priority="fallback"))
        
        # Build manifest scene
        manifest_scene = {
            "scene_id": scene_id,
            "start_sec": sa.get("start_sec", 0),
            "end_sec": sa.get("end_sec", 0),
            "assets": all_assets,
            "narration_block_ids": [],  # Will be filled from shot_plan if needed
        }
        
        manifest_scenes.append(manifest_scene)
    
    # Build manifest
    manifest = {
        "version": "archive_manifest_v2_from_source_pack",
        "episode_id": source_pack.get("episode_id", ""),
        "compile_plan": compile_plan,
        "scenes": manifest_scenes,
        "provenance": {
            "source_pack_version": source_pack.get("version"),
            "converted_at": source_pack.get("generated_at"),
        },
    }
    
    # Write manifest
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"✅ CB v2: Manifest saved to {output_path}")
        print(f"   - Scenes: {len(manifest_scenes)}")
        print(f"   - Total assets: {sum(len(s['assets']) for s in manifest_scenes)}")
    
    return manifest, output_path


def _convert_asset_ref(asset_ref: Dict[str, Any], priority: str) -> Dict[str, Any]:
    """
    Převede asset reference ze source pack na manifest asset format.
    
    Manifest format očekává:
    - archive_item_id
    - asset_url
    - media_type
    - priority
    """
    return {
        "archive_item_id": asset_ref.get("archive_item_id", ""),
        "asset_url": asset_ref.get("asset_url", ""),
        "media_type": asset_ref.get("media_type", "image"),
        "priority": priority,
        "source": "source_pack",
        "visual_type": asset_ref.get("visual_type", "general"),
        "global_rank": asset_ref.get("global_rank"),
        "global_score": asset_ref.get("global_score"),
    }


def build_compilation_from_source_pack(
    source_pack_path: str,
    shot_plan_path: str,
    episode_id: str,
    storage_dir: str,
    output_dir: str,
    verbose: bool = False,
    progress_callback: Optional[Any] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Hlavní entry point pro CB v2.
    
    Args:
        source_pack_path: Cesta k source_pack.json
        shot_plan_path: Cesta k shot_plan.json (nebo script_state.json s shot_plan)
        episode_id: ID epizody
        storage_dir: Cache storage pro downloads
        output_dir: Output složka pro finální video
        verbose: Logování detailů
        progress_callback: Optional callback pro progress
    
    Returns:
        (output_video_path, metadata)
    """
    if verbose:
        print(f"🎬 CB v2: Building compilation from source pack for episode {episode_id}")
    
    # Load source pack
    if not os.path.exists(source_pack_path):
        return None, {"error": f"Source pack not found: {source_pack_path}"}
    
    with open(source_pack_path, "r", encoding="utf-8") as f:
        source_pack = json.load(f)
    
    # Load shot plan
    if not os.path.exists(shot_plan_path):
        return None, {"error": f"Shot plan not found: {shot_plan_path}"}
    
    with open(shot_plan_path, "r", encoding="utf-8") as f:
        shot_plan_data = json.load(f)
    
    # Extract shot_plan (tolerant)
    if isinstance(shot_plan_data.get("shot_plan"), dict):
        shot_plan = shot_plan_data["shot_plan"]
    elif isinstance(shot_plan_data.get("metadata", {}).get("shot_plan"), dict):
        shot_plan = shot_plan_data["metadata"]["shot_plan"]
    else:
        shot_plan = shot_plan_data
    
    # Convert to manifest
    manifest_path = os.path.join(storage_dir, "archive_manifest_from_source_pack.json")
    manifest, _ = convert_source_pack_to_manifest(
        source_pack,
        shot_plan,
        manifest_path,
        verbose=verbose,
    )
    
    # Use legacy CB to build video
    try:
        from compilation_builder import build_episode_compilation
        
        output_video, metadata = build_episode_compilation(
            manifest_path=manifest_path,
            episode_id=episode_id,
            storage_dir=storage_dir,
            output_dir=output_dir,
            target_duration_sec=None,
            progress_callback=progress_callback,
        )
        
        return output_video, metadata
    
    except Exception as e:
        return None, {"error": f"CB failed: {e}"}


if __name__ == "__main__":
    # Simple test
    test_source_pack = {
        "version": "source_pack_v1",
        "episode_id": "test_ep",
        "scene_assignments": [
            {
                "scene_id": "sc_0001",
                "start_sec": 0,
                "end_sec": 10,
                "primary_assets": [
                    {
                        "asset_id": "asset_0001",
                        "archive_item_id": "item_001",
                        "asset_url": "https://archive.org/details/item_001",
                        "media_type": "image",
                        "visual_type": "map",
                        "global_rank": 1,
                    }
                ],
                "secondary_assets": [],
                "texture_assets": [],
                "total_assets": 1,
                "has_deficit": False,
            }
        ],
        "fallback_pools": {
            "texture_pool": [],
            "emergency_pool": [],
        },
    }
    
    test_shot_plan = {
        "version": "shotplan_v3",
        "total_duration_sec": 10,
    }
    
    manifest, path = convert_source_pack_to_manifest(
        test_source_pack,
        test_shot_plan,
        output_path="/tmp/archive_manifest_from_sp.json",
        verbose=True,
    )
    
    print("\n✅ CB v2 test completed")
    print(f"   Manifest scenes: {len(manifest['scenes'])}")


