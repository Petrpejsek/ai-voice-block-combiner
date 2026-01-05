#!/bin/bash
# Topic Intelligence Assistant - End-to-End Test
# Tests the isolated research feature without impacting the pipeline

echo "=========================================="
echo "Topic Intelligence Assistant - E2E Test"
echo "=========================================="
echo ""

# Configuration
BACKEND_URL="http://localhost:50000"
TEST_COUNT=5
TEST_WINDOW=7

echo "📋 Test Configuration:"
echo "   Backend URL: $BACKEND_URL"
echo "   Request count: $TEST_COUNT"
echo "   Time window: ${TEST_WINDOW}d"
echo ""

# Test 1: Health Check
echo "Test 1: Backend Health Check"
echo "-----------------------------"
HEALTH_RESPONSE=$(curl -s "$BACKEND_URL/health")
if echo "$HEALTH_RESPONSE" | grep -q "OK"; then
    echo "✅ Backend is running"
else
    echo "❌ Backend is not responding"
    echo "Response: $HEALTH_RESPONSE"
    exit 1
fi
echo ""

# Test 2: Feature Flag Check (should fail if not enabled)
echo "Test 2: Feature Flag Check"
echo "--------------------------"
echo "Attempting research with feature disabled..."
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/topic-intel/research" \
    -H "Content-Type: application/json" \
    -d "{\"count\": $TEST_COUNT, \"window_days\": $TEST_WINDOW}")

if echo "$RESPONSE" | grep -q "není povolena\|not enabled"; then
    echo "✅ Feature flag correctly blocks when disabled"
    echo "⚠️  To enable: Add TOPIC_INTEL_ENABLED=true to backend/.env and restart backend"
else
    echo "⚠️  Feature appears to be enabled or returned unexpected response"
fi
echo ""

# Test 3: Input Validation
echo "Test 3: Input Validation"
echo "------------------------"

# Test invalid count (too high)
echo "Testing count=100 (should fail)..."
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/topic-intel/research" \
    -H "Content-Type: application/json" \
    -d '{"count": 100, "window_days": 7}')

if echo "$RESPONSE" | grep -q "mezi 5 a 50\|must be"; then
    echo "✅ Count validation works"
else
    echo "⚠️  Count validation may not be working"
fi

# Test invalid window
echo "Testing window_days=14 (should fail)..."
RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/topic-intel/research" \
    -H "Content-Type: application/json" \
    -d '{"count": 10, "window_days": 14}')

if echo "$RESPONSE" | grep -q "7 nebo 30\|7 or 30"; then
    echo "✅ Window validation works"
else
    echo "⚠️  Window validation may not be working"
fi
echo ""

# Test 4: Full Research Request (only if feature enabled and OpenAI configured)
echo "Test 4: Full Research Request"
echo "-----------------------------"
echo "⚠️  This test requires:"
echo "   1. TOPIC_INTEL_ENABLED=true in backend/.env"
echo "   2. OPENAI_API_KEY configured in backend/.env"
echo "   3. Backend restarted after config changes"
echo ""
echo "Attempting full research request..."
echo "Request: count=$TEST_COUNT, window_days=$TEST_WINDOW"
echo ""

RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/topic-intel/research" \
    -H "Content-Type: application/json" \
    -d "{\"count\": $TEST_COUNT, \"window_days\": $TEST_WINDOW}" \
    --max-time 180)  # 3 minute timeout

if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "✅ Research completed successfully!"
    echo ""
    
    # Parse and display summary
    echo "Response Summary:"
    echo "$RESPONSE" | python3 -c "
import sys
import json
try:
    data = json.load(sys.stdin)
    print(f\"   Request ID: {data.get('request_id', 'N/A')}\")
    print(f\"   Items returned: {len(data.get('items', []))}\")
    stats = data.get('stats', {})
    print(f\"   Seeds collected: {stats.get('seeds_collected', 'N/A')}\")
    print(f\"   Candidates generated: {stats.get('candidates_generated', 'N/A')}\")
    print(f\"   Elapsed time: {stats.get('elapsed_seconds', 'N/A')}s\")
    print(\"\")
    print(\"   Top 3 Recommendations:\")
    for i, item in enumerate(data.get('items', [])[:3], 1):
        print(f\"   {i}. {item.get('topic', 'N/A')} [{item.get('rating_letter', 'N/A')}, {item.get('score_total', 0)}/100]\")
except Exception as e:
    print(f\"   Error parsing response: {e}\")
" 2>/dev/null || echo "   (Could not parse detailed response)"

elif echo "$RESPONSE" | grep -q "není povolena\|not enabled"; then
    echo "⚠️  Feature not enabled. Enable with TOPIC_INTEL_ENABLED=true in backend/.env"
elif echo "$RESPONSE" | grep -q "API klíč není nastaven\|API key not set"; then
    echo "⚠️  OpenAI API key not configured. Set OPENAI_API_KEY in backend/.env"
else
    echo "❌ Research failed"
    echo "Response: $RESPONSE"
fi
echo ""

# Test 5: UI Access Check
echo "Test 5: Frontend UI Check"
echo "--------------------------"
FRONTEND_URL="http://localhost:4000"
echo "Frontend should be running at: $FRONTEND_URL"
echo "✅ Check manually: Look for 'Topic Intelligence (US)' panel at bottom of page"
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "✅ Completed E2E test suite"
echo ""
echo "Next Steps:"
echo "1. If feature flag test failed, add to backend/.env:"
echo "   TOPIC_INTEL_ENABLED=true"
echo ""
echo "2. If OpenAI test failed, add to backend/.env:"
echo "   OPENAI_API_KEY=your_key_here"
echo ""
echo "3. Restart backend: cd backend && python3 app.py"
echo ""
echo "4. Test in UI:"
echo "   - Open $FRONTEND_URL"
echo "   - Scroll to bottom"
echo "   - Look for 'Topic Intelligence (US)' panel"
echo "   - Click 'Start Research'"
echo "   - Verify results display correctly"
echo ""
echo "=========================================="



