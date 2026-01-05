#!/usr/bin/env python3
"""
FDA Quality Check - Rychlý test že FDA generuje kvalitní output

Spustit: python3 backend/test_fda_quality_check.py
"""

import json
import os
import sys

def check_fda_quality(episode_id):
    """Zkontroluje kvalitu FDA outputu pro danou epizodu"""
    
    script_state_path = f"projects/{episode_id}/script_state.json"
    
    if not os.path.exists(script_state_path):
        print(f"❌ Epizoda {episode_id} neexistuje")
        return False
    
    with open(script_state_path) as f:
        state = json.load(f)
    
    shot_plan_wrapper = state.get('shot_plan', {})
    shot_plan = shot_plan_wrapper.get('shot_plan', {})
    
    print(f"\n{'='*70}")
    print(f"FDA Quality Check: {episode_id}")
    print(f"{'='*70}")
    
    # Check 1: Version
    version = shot_plan.get('version')
    print(f"\n1️⃣ Version: {version}")
    if version == 'fda_v2.7':
        print("   ✅ CORRECT - Using v2.7 with deterministicgenerators")
    elif version == 'shotplan_v3':
        print("   ⚠️  WARNING - Using v3 (basic compiler, no guardrails)")
    else:
        print(f"   ❌ ERROR - Unknown version: {version}")
        return False
    
    # Check 2: Source
    source = shot_plan.get('source')
    print(f"\n2️⃣ Source: {source}")
    if source == 'tts_ready_package':
        print("   ✅ CORRECT")
    else:
        print(f"   ❌ ERROR - Expected 'tts_ready_package', got '{source}'")
        return False
    
    # Check 3: Extra fields
    allowed_keys = {'version', 'source', 'assumptions', 'scenes'}
    extra_keys = set(shot_plan.keys()) - allowed_keys
    print(f"\n3️⃣ Extra fields: {list(extra_keys) if extra_keys else 'None'}")
    if not extra_keys:
        print("   ✅ CORRECT - No extra fields")
    else:
        print(f"   ❌ ERROR - Found extra fields: {extra_keys}")
        return False
    
    # Check 4: Scenes quality
    scenes = shot_plan.get('scenes', [])
    print(f"\n4️⃣ Scenes: {len(scenes)}")
    
    if not scenes:
        print("   ❌ ERROR - No scenes")
        return False
    
    # Check first scene in detail
    scene = scenes[0]
    scene_id = scene.get('scene_id', 'unknown')
    
    print(f"\n5️⃣ First scene ({scene_id}) quality check:")
    
    # Keywords
    keywords = scene.get('keywords', [])
    print(f"\n   Keywords ({len(keywords)}):")
    if len(keywords) == 8:
        print("   ✅ Correct count (8)")
    else:
        print(f"   ⚠️  Expected 8, got {len(keywords)}")
    
    for i, kw in enumerate(keywords[:3]):
        word_count = len(kw.split())
        # Check for forbidden tokens
        forbidden = ['the ', ' a ', ' an ', 'these', 'those', 'this', 'that']
        has_forbidden = any(f in kw.lower() for f in forbidden)
        status = "✅" if (2 <= word_count <= 5 and not has_forbidden) else "⚠️"
        print(f"   {status} {i+1}. {kw} ({word_count} words)")
        if has_forbidden:
            print(f"      ⚠️  Contains forbidden token!")
    
    # Queries
    queries = scene.get('search_queries', [])
    print(f"\n   Search Queries ({len(queries)}):")
    if len(queries) == 5:
        print("   ✅ Correct count (5)")
    else:
        print(f"   ⚠️  Expected 5, got {len(queries)}")
    
    quality_score = 0
    for i, q in enumerate(queries[:5]):
        word_count = len(q.split())
        q_lower = q.lower()
        
        # Check anchors
        has_anchor = any(anchor in q_lower for anchor in ['moscow', 'napoleon', '1812', 'tsar', 'borodino'])
        
        # Check forbidden starts
        first_word = q.split()[0].lower() if q.split() else ""
        forbidden_starts = {'these', 'the', 'a', 'an', 'following', 'upon', 'he', 'she', 'they'}
        bad_start = first_word in forbidden_starts
        
        # Quality indicators
        if has_anchor and 5 <= word_count <= 9 and not bad_start:
            status = "✅"
            quality_score += 1
        else:
            status = "⚠️"
        
        print(f"   {status} {i+1}. {q} ({word_count} words)")
        if not has_anchor:
            print(f"      ⚠️  Missing anchor (Moscow/Napoleon/1812/Tsar/Borodino)")
        if bad_start:
            print(f"      ⚠️  Forbidden start word: '{first_word}'")
        if word_count < 5 or word_count > 9:
            print(f"      ⚠️  Word count out of range (need 5-9)")
    
    # Shot strategy
    shot_strategy = scene.get('shot_strategy', {})
    source_pref = shot_strategy.get('source_preference')
    print(f"\n   Shot Strategy:")
    print(f"   source_preference: {source_pref}")
    if isinstance(source_pref, list) and source_pref == ['archive_org']:
        print("   ✅ CORRECT - List ['archive_org']")
    elif source_pref == 'archive_org':
        print("   ❌ ERROR - String instead of list!")
        return False
    else:
        print(f"   ⚠️  Unexpected value: {source_pref}")
    
    # Overall quality
    print(f"\n{'='*70}")
    print(f"QUALITY SCORE: {quality_score}/5 queries are high quality")
    print(f"{'='*70}")
    
    if version == 'fda_v2.7' and quality_score >= 4:
        print("\n✅ FDA OUTPUT IS HIGH QUALITY")
        return True
    elif version == 'shotplan_v3':
        print("\n⚠️  Using v3 mode - quality may vary (no guardrails)")
        print("   💡 TIP: v2.7 mode is now DEFAULT for new episodes")
        return True
    else:
        print("\n❌ FDA OUTPUT NEEDS IMPROVEMENT")
        print(f"   Version: {version}")
        print(f"   Quality: {quality_score}/5")
        return False


if __name__ == "__main__":
    # Find latest episode
    import glob
    episodes = glob.glob("projects/ep_*/script_state.json")
    if not episodes:
        print("❌ No episodes found")
        sys.exit(1)
    
    # Sort by modification time
    episodes.sort(key=os.path.getmtime, reverse=True)
    latest = episodes[0].split('/')[1]
    
    print(f"Checking latest episode: {latest}")
    
    success = check_fda_quality(latest)
    sys.exit(0 if success else 1)



