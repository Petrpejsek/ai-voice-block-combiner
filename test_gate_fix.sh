#!/bin/bash
# Test Gate Filter Fix - Ověří, že systém vrací požadovaný počet doporučení

echo "=========================================="
echo "Topic Intelligence - Gate Filter Fix Test"
echo "=========================================="
echo ""

BACKEND_URL="http://localhost:50000"

# Test 1: Health Check
echo "Test 1: Backend Health Check"
echo "-----------------------------"
HEALTH=$(curl -s "$BACKEND_URL/health")
if echo "$HEALTH" | grep -q "OK"; then
    echo "✅ Backend is running"
else
    echo "❌ Backend is not responding"
    exit 1
fi
echo ""

# Test 2: Request 5 recommendations with Momentum mode
echo "Test 2: Request 5 Recommendations (Momentum Mode)"
echo "--------------------------------------------------"
echo "Sending request: count=5, window_days=7, mode=momentum"
echo ""

RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/topic-intel/research" \
    -H "Content-Type: application/json" \
    -d '{
        "count": 5,
        "window_days": 7,
        "profile_id": "us_true_crime",
        "recommendation_mode": "momentum"
    }' \
    --max-time 120)

# Parse response
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "✅ Research completed successfully!"
    echo ""
    
    # Extract stats
    echo "$RESPONSE" | python3 -c "
import sys
import json
try:
    data = json.load(sys.stdin)
    items_count = len(data.get('items', []))
    stats = data.get('stats', {})
    
    print('Response Summary:')
    print(f'   Requested: 5 recommendations')
    print(f'   Returned: {items_count} recommendations')
    print(f'   Candidates scored: {stats.get(\"candidates_scored\", \"N/A\")}')
    print(f'   Top recommendations: {stats.get(\"top_recommendations\", \"N/A\")}')
    print(f'   Other ideas: {stats.get(\"other_ideas\", \"N/A\")}')
    print(f'   Elapsed time: {stats.get(\"elapsed_seconds\", \"N/A\")}s')
    print('')
    
    # Validation
    if items_count == 5:
        print('✅ SUCCESS: Returned exactly 5 recommendations as requested!')
    elif items_count < 5:
        print(f'⚠️  WARNING: Returned {items_count}/5 recommendations')
        print('   (Check backend logs for \"NEDOSTATEK KANDIDÁTŮ\" warning)')
    else:
        print(f'❌ ERROR: Returned {items_count} recommendations (expected 5)')
    
    print('')
    print('Top Recommendations:')
    for i, item in enumerate(data.get('items', [])[:5], 1):
        gate_passed = '✓ GATE' if item.get('_gate_passed') else '○ OTHER'
        print(f'   {i}. {item.get(\"topic\", \"N/A\")[:60]}')
        print(f'      Score: {item.get(\"score_total\", 0)}/100 [{item.get(\"rating_letter\", \"N/A\")}] {gate_passed}')
        
except Exception as e:
    print(f'❌ Error parsing response: {e}')
    print(f'Response: {sys.stdin.read()[:500]}')
" 2>/dev/null

elif echo "$RESPONSE" | grep -q "není povolena"; then
    echo "❌ Feature not enabled. Add TOPIC_INTEL_ENABLED=true to backend/.env"
elif echo "$RESPONSE" | grep -q "API klíč není nastaven"; then
    echo "❌ OpenRouter API key not configured. Set OPENROUTER_API_KEY in backend/.env"
else
    echo "❌ Research failed"
    echo "Response preview: $(echo "$RESPONSE" | head -c 500)"
fi

echo ""
echo "=========================================="
echo "Check backend logs for detailed gate info:"
echo "  tail -f backend_server_fixed.log"
echo ""
echo "Look for lines like:"
echo "  ⚠️  Gate passed only 4/5 - doplňování z Other..."
echo "  ✅ Doplněno 1 kandidátů (finální TOP: 5)"
echo "=========================================="
echo ""


