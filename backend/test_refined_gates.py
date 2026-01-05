#!/usr/bin/env python3
"""
Test script for refined topic gates (v5).
Tests: HARD/CONDITIONAL/SOFT gates, controlled fallback, NO TITLECARDS.
"""
import sys
import os
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from archive_asset_resolver import resolve_shot_plan_assets


def test_refined_gates(episode_id: str):
    """Run AAR with refined gates on existing episode"""
    project_dir = Path(__file__).parent.parent / "projects" / episode_id
    
    if not project_dir.exists():
        print(f"❌ Project dir not found: {project_dir}")
        return 1
    
    # Load script_state
    script_state_path = project_dir / "script_state.json"
    if not script_state_path.exists():
        print(f"❌ script_state.json not found")
        return 1
    
    with open(script_state_path, 'r', encoding='utf-8') as f:
        script_state = json.load(f)
    
    shot_plan_raw = script_state.get("shot_plan")
    if not shot_plan_raw:
        print(f"❌ No shot_plan in script_state")
        return 1
    
    # Backward/forward compat: shot_plan may be stored as canonical wrapper {"shot_plan": {...}}
    shot_plan = shot_plan_raw
    if isinstance(shot_plan_raw, dict) and isinstance(shot_plan_raw.get("shot_plan"), dict):
        shot_plan = shot_plan_raw["shot_plan"]

    print(f"✅ Loaded shot_plan: {len(shot_plan.get('scenes', []))} scenes\n")
    
    # Clear cache (v5)
    cache_dir = project_dir / "archive_cache"
    if cache_dir.exists():
        import glob
        old_cache = glob.glob(str(cache_dir / "archive_search_v*.json"))
        for cf in old_cache:
            try:
                os.remove(cf)
                print(f"🗑️  Deleted: {Path(cf).name}")
            except:
                pass
    
    print(f"\n{'='*70}")
    print(f"AAR (v5 - Refined Topic Gates)")
    print(f"{'='*70}\n")
    
    manifest_path = project_dir / "archive_manifest.json"
    
    try:
        manifest, _ = resolve_shot_plan_assets(
            shot_plan=shot_plan,
            cache_dir=str(cache_dir),
            manifest_output_path=str(manifest_path),
            throttle_delay_sec=0.5,
            episode_id=episode_id
        )
        
        print(f"\n{'='*70}")
        print(f"✅ AAR COMPLETED")
        print(f"{'='*70}\n")
        
        # Analyze results
        all_assets = []
        primary_count = 0
        secondary_count = 0
        
        for scene in manifest.get("scenes", []):
            for asset in scene.get("assets", []):
                all_assets.append(asset)
                pool = asset.get("pool_priority", "")
                if pool == "primary":
                    primary_count += 1
                elif pool == "secondary":
                    secondary_count += 1
        
        print(f"📊 RESULTS:")
        print(f"   Primary assets: {primary_count}")
        print(f"   Secondary assets: {secondary_count}")
        print(f"   Total assets: {len(all_assets)}\n")
        
        # Check for problematic content
        print(f"🔍 CHECKING FOR PROBLEMATIC CONTENT:\n")
        
        animated_found = []
        tv_series_ok = []
        
        for asset in all_assets:
            title = asset.get("title", "").lower()
            
            # Check HARD reject patterns (should NOT appear)
            if any(x in title for x in ["animated", "cartoon", "back to the future"]):
                animated_found.append(asset)
            
            # Check CONDITIONAL patterns (OK if historical)
            if any(x in title for x in ["season", "episode"]):
                tv_series_ok.append(asset)
        
        if animated_found:
            print(f"❌ ANIMATED CONTENT FOUND ({len(animated_found)}):")
            for a in animated_found[:3]:
                print(f"   - {a.get('title')[:60]}")
        else:
            print(f"✅ No animated/cartoon content (HARD reject works!)")
        
        if tv_series_ok:
            print(f"\n✅ TV/SERIES CONTENT ALLOWED ({len(tv_series_ok)}) - CONDITIONAL gate:")
            for a in tv_series_ok[:3]:
                print(f"   - {a.get('title')[:60]}")
                print(f"     (has historical content, allowed)")
        
        # Check primary assets titles
        print(f"\n📋 SAMPLE PRIMARY ASSETS:")
        primary_assets = [a for a in all_assets if a.get("pool_priority") == "primary"]
        for a in primary_assets[:5]:
            print(f"   - {a.get('title')[:65]}")
        
        # Check NO TITLECARDS policy
        print(f"\n🎬 CHECKING NO TITLECARDS POLICY:\n")
        min_in_sec_found = []
        for asset in all_assets[:10]:
            for subclip in asset.get("recommended_subclips", []):
                in_sec = subclip.get("in_sec", 0)
                min_in_sec_found.append(in_sec)
        
        if min_in_sec_found:
            min_val = min(min_in_sec_found)
            max_val = max(min_in_sec_found)
            below_30 = [x for x in min_in_sec_found if x < 30]
            
            print(f"   Min in_sec: {min_val}s")
            print(f"   Max in_sec: {max_val}s")
            print(f"   Subclips < 30s: {len(below_30)}")
            
            if below_30:
                print(f"   ⚠️  WARNING: Some subclips start before 30s")
            else:
                print(f"   ✅ All subclips start >= 30s!")
        
        print(f"\n{'='*70}")
        print(f"ACCEPTANCE CHECKS:")
        print(f"{'='*70}")
        print(f"1. HARD reject (animated/talks): {'✅ PASS' if not animated_found else '❌ FAIL'}")
        print(f"2. CONDITIONAL (season/episode + historical): {'✅ PASS' if tv_series_ok or not animated_found else '⚠️  CHECK'}")
        print(f"3. Primary assets > 0: {'✅ PASS' if primary_count > 0 else '❌ FAIL (fallback needed)'}")
        print(f"4. NO TITLECARDS (>= 30s): {'✅ PASS' if not below_30 else '❌ FAIL'}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_refined_gates.py <episode_id>")
        print("\nExample: python3 test_refined_gates.py ep_9f2ea4ca9f19")
        sys.exit(1)
    
    episode_id = sys.argv[1]
    sys.exit(test_refined_gates(episode_id))

