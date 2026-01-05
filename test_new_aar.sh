#!/bin/bash
# Test script: Regenerate AAR manifest with new diversity settings

cd /Users/petrliesner/podcasts/backend

echo "🔄 Regenerating AAR manifest with diversity fixes..."

AAR_ENABLE_LLM_TOPIC_VALIDATION=0 python3 - <<'PY'
import json, os
from archive_asset_resolver import resolve_shot_plan_assets

ep='ep_8786858c6a08'
base=f'/Users/petrliesner/podcasts/projects/{ep}'
state=json.load(open(os.path.join(base,'script_state.json'),'r',encoding='utf-8'))
shot_plan=state.get('shot_plan')
tts=state.get('tts_ready_package')
episode_id=state.get('episode_id')
topic=(state.get('episode_input') or {}).get('topic')
cache_dir=os.path.join(base,'archive_cache')
out_path=os.path.join(base,'archive_manifest.json')  # OVERWRITE existing!

print(f"📋 Topic: {topic}")
print(f"📋 Shot plan scenes: {len(shot_plan.get('scenes', []))}")
print()

manifest, mp = resolve_shot_plan_assets(
    shot_plan=shot_plan,
    cache_dir=cache_dir,
    manifest_output_path=out_path,
    throttle_delay_sec=0.5,  # Gentle on APIs
    tts_ready_package=tts,
    voiceover_dir=os.path.join(base,'voiceover'),
    episode_id=episode_id,
    verbose=True,
    preview_mode=False,  # Full mode
    episode_topic=topic,
)

print()
print("="*80)
print("📊 NEW MANIFEST STATS:")
print("="*80)

scenes=manifest.get('scenes') or []
unique=set()
media_counts={}
for sc in scenes:
    for beat in (sc.get('visual_beats') or []):
        for cand in (beat.get('asset_candidates') or []):
            if isinstance(cand,dict):
                unique.add(cand.get('archive_item_id'))
                media_counts[cand.get('media_type')] = media_counts.get(cand.get('media_type'),0)+1

print(f"✅ Unique video sources: {len([u for u in unique if u])} (target: 5-8)")
print(f"✅ Media type counts: {media_counts}")

# Beat candidates distribution
cand_counts=[]
for sc in scenes:
    for beat in (sc.get('visual_beats') or []):
        cand_counts.append(len(beat.get('asset_candidates') or []))
print(f"✅ Asset candidates per beat (min/median/max): {min(cand_counts) if cand_counts else 0}/{sorted(cand_counts)[len(cand_counts)//2] if cand_counts else 0}/{max(cand_counts) if cand_counts else 0}")

print()
print(f"📝 Manifest saved to: {out_path}")
print()
print("🎬 Next step: Spusťte video kompilaci (Generovat video button v UI)")
PY

echo ""
echo "✅ Hotovo! Nyní můžete spustit kompilaci."

