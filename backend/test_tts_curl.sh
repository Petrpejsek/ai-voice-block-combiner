#!/bin/bash
# Rychlý test Google TTS endpoint
# Použití: ./test_tts_curl.sh

echo "🧪 Testuji Google TTS endpoint..."
echo ""

# Backend URL
URL="http://localhost:50000/api/tts/generate"

# Test payload - 2 jednoduché bloky
PAYLOAD='{
  "tts_ready_package": {
    "episode_id": "curl_test",
    "language": "en-US",
    "narration_blocks": [
      {
        "block_id": "test_001",
        "text_tts": "Hello from curl test. This is the first audio block."
      },
      {
        "block_id": "test_002",
        "text_tts": "And this is the second block. Both should be saved as MP3 files."
      }
    ]
  }
}'

echo "📡 POST $URL"
echo ""
echo "📦 Payload:"
echo "$PAYLOAD" | jq '.'
echo ""
echo "⏳ Posílám request..."
echo ""

# Curl request s timeout
RESPONSE=$(curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  --max-time 120)

# Zkontroluj response
if [ -z "$RESPONSE" ]; then
  echo "❌ CHYBA: Žádná odpověď z backendu"
  echo "   Běží backend na http://localhost:50000?"
  exit 1
fi

# Parse response
echo "📊 Response:"
echo "$RESPONSE" | jq '.'
echo ""

# Zkontroluj success
SUCCESS=$(echo "$RESPONSE" | jq -r '.success')

if [ "$SUCCESS" = "true" ]; then
  echo "✅ SUCCESS!"
  
  GENERATED=$(echo "$RESPONSE" | jq -r '.generated_blocks')
  TOTAL=$(echo "$RESPONSE" | jq -r '.total_blocks')
  OUTPUT_DIR=$(echo "$RESPONSE" | jq -r '.output_dir')
  
  echo ""
  echo "📈 Stats:"
  echo "  - Vygenerováno: $GENERATED / $TOTAL bloků"
  echo "  - Výstup: $OUTPUT_DIR"
  echo ""
  
  # Ověř soubory
  echo "📁 Ověřuji soubory v $OUTPUT_DIR:"
  if [ -d "$OUTPUT_DIR" ]; then
    for file in "$OUTPUT_DIR"/Narrator_*.mp3; do
      if [ -f "$file" ]; then
        SIZE=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
        echo "  ✅ $(basename "$file") ($SIZE bytes)"
      fi
    done
  else
    echo "  ⚠️ Složka $OUTPUT_DIR neexistuje"
  fi
  
else
  echo "❌ FAILED!"
  ERROR=$(echo "$RESPONSE" | jq -r '.error')
  echo "  Chyba: $ERROR"
  exit 1
fi

echo ""
echo "=" 
echo "✅ Test dokončen úspěšně"
echo "="



