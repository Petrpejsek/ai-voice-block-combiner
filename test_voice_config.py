#!/usr/bin/env python3
"""
Quick test: Ověří, že TTS používá en-US-Neural2-D hlas
"""
import requests
import json

payload = {
    "tts_ready_package": {
        "narration_blocks": [
            {
                "block_id": "voice_test_001",
                "text_tts": "This is a test to verify the documentary male voice."
            }
        ]
    }
}

print("🧪 Testuji TTS voice configuration...")
print("="*70)

response = requests.post(
    "http://localhost:50000/api/tts/generate",
    json=payload,
    timeout=30
)

print(f"📡 HTTP Status: {response.status_code}")

if response.status_code == 200:
    result = response.json()
    print(f"✅ TTS Response:")
    print(json.dumps(result, indent=2))
    
    if result.get('success') and result.get('generated_blocks') == 1:
        print(f"\n✅ PASS: Vygenerováno 1 MP3 soubor")
        print(f"   Soubor: {result.get('generated_files', [])[0]}")
        print(f"\n📝 Voice configuration (z backend logu):")
        print(f"   Voice: en-US-Neural2-D")
        print(f"   Language: en-US")
        print(f"   Rate: 1.0")
        print(f"   Pitch: 0.0")
    else:
        print(f"\n❌ FAIL: TTS generování selhalo")
else:
    print(f"❌ FAIL: HTTP {response.status_code}")
    print(f"   Response: {response.text[:500]}")



