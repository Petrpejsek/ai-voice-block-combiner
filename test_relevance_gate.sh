#!/bin/bash
# Test script pro Relevance Gate V8

set -e

EPISODE_ID="ep_9f2ea4ca9f19"
PROJECT_DIR="projects/$EPISODE_ID"

echo "🎯 RELEVANCE GATE V8 TEST"
echo "=========================="
echo ""

# 1. Clear cache
echo "1️⃣ Clearing cache (force gate application)..."
rm -rf "$PROJECT_DIR/archive_cache/"*.json 2>/dev/null || true
echo "✅ Cache cleared (v8_relevance_gate will be used)"
echo ""

# 2. Run AAR with verbose
echo "2️⃣ Running AAR with verbose mode..."
python3 backend/run_step.py --episode "$EPISODE_ID" --step AAR --verbose 2>&1 | tee /tmp/aar_gate_test.log
echo ""

# 3. Analyze results
echo "3️⃣ Analyzing Relevance Gate results..."
echo ""

if [ -f "$PROJECT_DIR/archive_manifest.json" ]; then
    python3 << 'PYEOF'
import json
import sys

try:
    with open("projects/ep_9f2ea4ca9f19/archive_manifest.json") as f:
        manifest = json.load(f)
    
    print("📊 RELEVANCE GATE ANALYSIS")
    print("=" * 60)
    
    total_beats = 0
    total_candidates = 0
    passed_gate = 0
    failed_gate = 0
    
    for scene in manifest.get("scenes", []):
        for beat in scene.get("visual_beats", []):
            total_beats += 1
            candidates = beat.get("asset_candidates", [])
            total_candidates += len(candidates)
            
            for cand in candidates:
                dbg = cand.get("debug", {})
                gate_result = dbg.get("gate_result")
                gate_details = dbg.get("gate_details", {})
                
                if gate_result == "PASS":
                    passed_gate += 1
                
                if gate_details:
                    rules_passed = gate_details.get("rules_passed", "?/?")
                    print(f"\n  Beat {beat.get('block_id')}:")
                    print(f"    Asset: {cand.get('archive_item_id')}")
                    print(f"    Gate: {gate_result} ({rules_passed})")
                    print(f"    Score: {cand.get('score')}")
                    
                    # Show which rules passed/failed
                    for rule_key in ["rule_1_anchor", "rule_2_visual", "rule_3_forbidden"]:
                        rule_val = gate_details.get(rule_key, "")
                        status = "✅" if rule_val == "PASS" else "❌"
                        print(f"      {status} {rule_key}: {rule_val}")
    
    print(f"\n📈 Summary:")
    print(f"  Total beats: {total_beats}")
    print(f"  Total candidates shown: {total_candidates}")
    print(f"  Passed gate: {passed_gate}")
    
    # Check for generic queries
    print(f"\n🔍 Query Quality Check:")
    generic_count = 0
    for scene in manifest.get("scenes", []):
        for beat in scene.get("visual_beats", []):
            for cand in beat.get("asset_candidates", []):
                query = cand.get("query_used", "")
                query_lower = query.lower()
                
                # Check for generic-only queries
                generic_words = {"world", "war", "ii", "ww2", "wwii", "2"}
                query_word_set = set(query_lower.replace("-", " ").split())
                
                if query_word_set.issubset(generic_words):
                    print(f"  ❌ Generic query found: '{query}'")
                    generic_count += 1
    
    if generic_count == 0:
        print(f"  ✅ No generic-only queries found!")
    
    # Success criteria
    print(f"\n🎯 DEFINITION OF DONE CHECK:")
    
    checks = []
    checks.append(("Gate applied to all beats", total_beats > 0 and total_candidates > 0))
    checks.append(("No generic-only queries", generic_count == 0))
    checks.append(("Assets have gate details", passed_gate > 0))
    
    all_pass = all(c[1] for c in checks)
    
    for check_name, check_pass in checks:
        status = "✅" if check_pass else "❌"
        print(f"  {status} {check_name}")
    
    if all_pass:
        print(f"\n🎉 SUCCESS! Relevance Gate V8 funguje správně.")
        sys.exit(0)
    else:
        print(f"\n⚠️  Some checks failed - review above")
        sys.exit(1)

except Exception as e:
    print(f"❌ Error analyzing manifest: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYEOF
    
else
    echo "❌ Manifest not found: $PROJECT_DIR/archive_manifest.json"
    exit 1
fi

echo ""
echo "📝 Full AAR log: /tmp/aar_gate_test.log"
echo "📋 Manifest: $PROJECT_DIR/archive_manifest.json"



