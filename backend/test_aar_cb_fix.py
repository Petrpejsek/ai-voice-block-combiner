#!/usr/bin/env python3
"""
Test AAR + CB fixes on existing episode

Usage:
    python3 test_aar_cb_fix.py <episode_id>

Example:
    python3 test_aar_cb_fix.py ep_9f2ea4ca9f19
"""

import sys
import os
import json
from project_store import ProjectStore
from archive_asset_resolver import resolve_shot_plan_assets
from compilation_builder import build_episode_compilation


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_aar_cb_fix.py <episode_id>")
        print("\nExample: python3 test_aar_cb_fix.py ep_9f2ea4ca9f19")
        sys.exit(1)
    
    episode_id = sys.argv[1]
    
    print(f"🧪 Testing AAR + CB fixes on: {episode_id}\n")
    
    # Load project
    store = ProjectStore('../projects')
    
    try:
        state = store.read_script_state(episode_id)
    except FileNotFoundError:
        print(f"❌ Project {episode_id} not found!")
        sys.exit(1)
    
    # Check prerequisites
    print("📋 Checking prerequisites...")
    
    if not state.get('shot_plan'):
        print("❌ Project has no shot_plan - run FDA first")
        sys.exit(1)
    
    print("✅ shot_plan found")
    
    if not state.get('tts_ready_package'):
        print("❌ Project has no tts_ready_package")
        sys.exit(1)
    
    print("✅ tts_ready_package found")
    
    # Check voiceover
    voiceover_dir = f"../projects/{episode_id}/voiceover"
    if not os.path.exists(voiceover_dir):
        print(f"❌ Voiceover directory not found: {voiceover_dir}")
        sys.exit(1)
    
    mp3_files = [f for f in os.listdir(voiceover_dir) if f.endswith('.mp3')]
    if not mp3_files:
        print(f"❌ No MP3 files in {voiceover_dir}")
        sys.exit(1)
    
    print(f"✅ Voiceover found ({len(mp3_files)} MP3 files)")
    
    # Backup old manifest (if exists)
    manifest_path = f"../projects/{episode_id}/archive_manifest.json"
    if os.path.exists(manifest_path):
        backup_path = manifest_path.replace('.json', '_OLD.json')
        print(f"📦 Backing up old manifest: {backup_path}")
        os.rename(manifest_path, backup_path)
    
    # ============================================================
    # STEP 1: Run AAR (Archive Asset Resolver)
    # ============================================================
    print("\n🔍 STEP 1: Running AAR (Archive Asset Resolver)...")
    print("=" * 60)
    
    shot_plan = state['shot_plan']
    tts_ready_package = state.get('tts_ready_package')
    
    cache_dir = f"../projects/{episode_id}/archive_cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    try:
        manifest, manifest_file = resolve_shot_plan_assets(
            shot_plan=shot_plan,
            cache_dir=cache_dir,
            manifest_output_path=manifest_path,
            throttle_delay_sec=0.5,
            tts_ready_package=tts_ready_package,
            voiceover_dir=voiceover_dir,
            episode_id=episode_id
        )
        
        print(f"\n✅ AAR completed successfully!")
        print(f"   Manifest: {manifest_file}")
        print(f"   Scenes: {len(manifest.get('scenes', []))}")
        
        # Show first scene assets
        if manifest.get('scenes'):
            sc = manifest['scenes'][0]
            print(f"\n📊 Scene {sc['scene_id']} assets:")
            print(f"   Primary: {len(sc.get('primary_assets', []))}")
            print(f"   Secondary: {len(sc.get('secondary_assets', []))}")
            print(f"   Visual beats: {len(sc.get('visual_beats', []))}")
            
            # Show primary assets titles
            if sc.get('primary_assets'):
                print(f"\n   Primary asset titles:")
                for asset in sc['primary_assets'][:3]:
                    print(f"   - {asset.get('title', 'Untitled')[:60]}")
        
        # Check subclip_policy
        policy = manifest.get('compile_plan', {}).get('subclip_policy')
        if policy:
            print(f"\n✅ Subclip policy found:")
            print(f"   min_in_sec: {policy.get('min_in_sec')}")
            print(f"   avoid_ranges: {policy.get('avoid_ranges')}")
        else:
            print(f"\n⚠️  No subclip_policy in manifest")
        
    except Exception as e:
        print(f"\n❌ AAR failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # ============================================================
    # STEP 2: Run CB (Compilation Builder)
    # ============================================================
    print("\n\n🎬 STEP 2: Running CB (Compilation Builder)...")
    print("=" * 60)
    
    storage_dir = f"../projects/{episode_id}/assets"
    output_dir = "../output"
    
    try:
        video_path, metadata = build_episode_compilation(
            manifest_path=manifest_path,
            episode_id=episode_id,
            storage_dir=storage_dir,
            output_dir=output_dir,
            target_duration_sec=None
        )
        
        if video_path:
            print(f"\n✅ CB completed successfully!")
            print(f"   Video: {video_path}")
            print(f"   Duration: {metadata['compilation_report']['total_actual_duration_sec']:.1f}s")
            print(f"   Subclips: {metadata['compilation_report']['total_subclips']}")
            
            # Check for override_info in clips
            clips = []
            for scene in metadata['compilation_report']['scenes']:
                clips.extend(scene.get('clips_metadata', []))
            
            overrides = [c for c in clips if c.get('override_info')]
            print(f"\n📊 Override analysis:")
            print(f"   Total clips: {len(clips)}")
            print(f"   Overrides: {len(overrides)}")
            
            if overrides:
                print(f"\n   Override reasons:")
                reasons = {}
                for c in overrides:
                    reason = c['override_info'].get('override_reason', 'unknown')
                    reasons[reason] = reasons.get(reason, 0) + 1
                for reason, count in reasons.items():
                    print(f"   - {reason}: {count}")
            
            # Check in_sec values
            in_secs = [c.get('in_sec', 0) for c in clips]
            below_30 = [x for x in in_secs if x < 30]
            print(f"\n📊 Timestamp analysis:")
            print(f"   Min in_sec: {min(in_secs):.1f}s" if in_secs else "   No clips")
            print(f"   Max in_sec: {max(in_secs):.1f}s" if in_secs else "")
            print(f"   Clips starting < 30s: {len(below_30)}")
            
            if below_30:
                print(f"\n⚠️  WARNING: {len(below_30)} clips start before 30s!")
                for c in clips:
                    if c.get('in_sec', 0) < 30:
                        print(f"   - {c.get('block_id')}: in_sec={c.get('in_sec'):.1f}s, asset={c.get('asset_id')}")
            else:
                print(f"\n✅ All clips start >= 30s (NO TITLECARDS)")
            
        else:
            print(f"\n❌ CB failed - no video produced")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ CB failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n\n" + "=" * 60)
    print("🎉 TEST COMPLETED SUCCESSFULLY")
    print("=" * 60)
    
    print(f"\n📁 Output files:")
    print(f"   Manifest: {manifest_path}")
    print(f"   Video: {video_path}")
    
    # Find compilation report
    report_files = [f for f in os.listdir(output_dir) if f.startswith(f"compilation_report_{episode_id}")]
    if report_files:
        latest_report = sorted(report_files)[-1]
        print(f"   Report: {output_dir}/{latest_report}")
    
    print(f"\n✅ All acceptance criteria to check:")
    print(f"   1. Primary assets contain NO TV/animated/talks")
    print(f"   2. No subclips with in_sec < 30")
    print(f"   3. Override info present when needed")
    print(f"   4. Visual relevance improved")
    
    print(f"\n💡 Next steps:")
    print(f"   1. Review manifest: {manifest_path}")
    print(f"   2. Review compilation report in output/")
    print(f"   3. Watch video: {video_path}")
    print(f"   4. Compare with old manifest backup (if exists)")


if __name__ == "__main__":
    main()



