#!/bin/bash
# Test script pro Anti Off-Topic fix

set -e

EPISODE_ID="ep_9f2ea4ca9f19"
PROJECT_DIR="projects/$EPISODE_ID"

echo "🧪 ANTI OFF-TOPIC TEST"
echo "======================"
echo ""

# 1. Clear cache (force fresh queries)
echo "1️⃣ Clearing cache..."
rm -rf "$PROJECT_DIR/archive_cache/"*.json 2>/dev/null || true
echo "✅ Cache cleared"
echo ""

# 2. Run AAR with verbose
echo "2️⃣ Running AAR (verbose)..."
python3 backend/run_step.py --episode "$EPISODE_ID" --step AAR --verbose 2>&1 | tee /tmp/aar_test.log
echo ""

# 3. Check manifest for off-topic queries
echo "3️⃣ Checking manifest for generic queries..."
echo ""

if [ -f "$PROJECT_DIR/archive_manifest.json" ]; then
    echo "📊 Query Analysis:"
    echo "===================="
    
    # Extract all query_used values
    python3 << 'PYEOF'
import json
import sys

try:
    with open("projects/ep_9f2ea4ca9f19/archive_manifest.json") as f:
        manifest = json.load(f)
    
    queries = set()
    generic_count = 0
    duplicate_count = 0
    
    # Extract queries from visual_beats.asset_candidates
    for scene in manifest.get("scenes", []):
        for beat in scene.get("visual_beats", []):
            for cand in beat.get("asset_candidates", []):
                q = cand.get("query_used", "")
                if q:
                    q_lower = q.lower().strip()
                    
                    # Check for duplicates in query text
                    words = q_lower.split()
                    if len(words) != len(set(words)):
                        print(f"❌ DUPLICATE words in query: '{q}'")
                        duplicate_count += 1
                    
                    # Check for generic-only queries
                    generic_words = {"world", "war", "ii", "ww2", "wwii", "2"}
                    query_word_set = set(w.replace("-", "") for w in words)
                    if query_word_set.issubset(generic_words):
                        print(f"❌ GENERIC-ONLY query: '{q}'")
                        generic_count += 1
                    elif q not in queries:
                        print(f"✅ SPECIFIC query: '{q}'")
                        queries.add(q)
    
    print(f"\n📊 Summary:")
    print(f"  - Unique specific queries: {len(queries)}")
    print(f"  - Generic-only queries: {generic_count}")
    print(f"  - Queries with duplicates: {duplicate_count}")
    
    if generic_count == 0 and duplicate_count == 0:
        print(f"\n🎉 SUCCESS! All queries are specific and unique.")
        sys.exit(0)
    else:
        print(f"\n⚠️  ISSUES FOUND - review queries above")
        sys.exit(1)

except Exception as e:
    print(f"❌ Error reading manifest: {e}")
    sys.exit(1)
PYEOF
    
else
    echo "❌ Manifest not found: $PROJECT_DIR/archive_manifest.json"
    exit 1
fi

echo ""
echo "📝 Full AAR log saved to: /tmp/aar_test.log"
echo "🎬 Ready to run CB for video compilation"



