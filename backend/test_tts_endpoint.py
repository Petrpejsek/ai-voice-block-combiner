#!/usr/bin/env python3
"""
Test skript pro Google TTS endpoint
Použití: python3 test_tts_endpoint.py
"""

import requests
import json
import os

# Backend URL
BASE_URL = "http://localhost:50000"

# Test data - 3 jednoduché bloky
test_package = {
    "tts_ready_package": {
        "episode_id": "test_001",
        "language": "en",
        "narration_blocks": [
            {
                "block_id": "b_0001",
                "text_tts": "Hello, this is the first test block. We are testing Google Cloud Text to Speech."
            },
            {
                "block_id": "b_0002",
                "text_tts": "This is the second block. It should be saved as Narrator underscore zero zero zero two dot mp3."
            },
            {
                "block_id": "b_0003",
                "text_tts": "And finally, the third test block. Let's see if all three files are generated correctly."
            }
        ]
    }
}

def test_tts_generate():
    """Test /api/tts/generate endpoint"""
    print("🧪 Testuji Google TTS endpoint...")
    print(f"📡 URL: {BASE_URL}/api/tts/generate")
    print(f"📦 Počet bloků: {len(test_package['tts_ready_package']['narration_blocks'])}")
    print()
    
    # Check credentials PŘED voláním
    import os
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path:
        print("⚠️ WARNING: GOOGLE_APPLICATION_CREDENTIALS není nastaveno v ENV")
        print("   Test pravděpodobně selže s auth refresh error")
    elif not os.path.exists(creds_path):
        print(f"⚠️ WARNING: Service account JSON neexistuje: {creds_path}")
        print("   Test pravděpodobně selže s auth refresh error")
    else:
        print(f"✅ Service account JSON nalezen: {creds_path}")
    print()
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/tts/generate",
            json=test_package,
            timeout=180  # 3 minuty pro 3 bloky
        )
        
        print(f"📊 HTTP Status: {response.status_code}")
        print()
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS!")
            print(f"📈 Response:")
            print(json.dumps(result, indent=2))
            print()
            
            # Ověř, že token refresh proběhl (mělo by být v logu backendu)
            print("🔍 Kontrola tokenu:")
            print("   → Token by měl být refreshnut 1× na začátku")
            print("   → Check backend logs pro '🔑 Access token úspěšně vygenerován'")
            print()
            
            # Ověř soubory
            output_dir = result.get('output_dir', '../uploads')
            expected_files = [
                'Narrator_0001.mp3',
                'Narrator_0002.mp3',
                'Narrator_0003.mp3'
            ]
            
            print("📁 Ověřuji vygenerované soubory...")
            for filename in expected_files:
                filepath = os.path.join(output_dir, filename)
                if os.path.exists(filepath):
                    size = os.path.getsize(filepath)
                    print(f"  ✅ {filename} ({size} bytes)")
                else:
                    print(f"  ❌ {filename} CHYBÍ")
            
            return True
        elif response.status_code == 500:
            # Check for auth refresh error
            result = response.json()
            error = result.get('error', '')
            
            if 'TTS_AUTH_REFRESH_FAILED' in error:
                print("❌ AUTH REFRESH FAILED!")
                print(f"   {error}")
                print()
                print("📝 Troubleshooting:")
                print("   1. Zkontroluj GOOGLE_APPLICATION_CREDENTIALS v .env")
                print("   2. Zkontroluj, že JSON soubor existuje")
                print("   3. Zkontroluj, že JSON je validní service account")
                print("   4. Zkontroluj service account permissions")
            else:
                print("❌ SERVER ERROR!")
                print(f"Error: {error}")
            return False
        else:
            print("❌ CHYBA!")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ CHYBA: Backend neběží na http://localhost:50000")
        print("   Spusťte backend: cd backend && python3 app.py")
        return False
    except requests.exceptions.Timeout:
        print("❌ CHYBA: Timeout - endpoint trvá příliš dlouho")
        return False
    except Exception as e:
        print(f"❌ CHYBA: {e}")
        return False


def test_video_integration():
    """Ověř, že existující generate_video_with_audio() najde soubory"""
    print()
    print("🎬 Test integrace s video pipeline...")
    
    upload_folder = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    
    # Najdi Narrator_*.mp3 soubory
    narrator_files = []
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            if filename.startswith('Narrator_') and filename.endswith('.mp3'):
                narrator_files.append(filename)
    
    narrator_files.sort()
    
    if narrator_files:
        print(f"✅ Nalezeno {len(narrator_files)} Narrator_*.mp3 souborů:")
        for f in narrator_files[:5]:  # Zobraz prvních 5
            print(f"  - {f}")
        if len(narrator_files) > 5:
            print(f"  ... a {len(narrator_files) - 5} dalších")
        print()
        print("✅ Video pipeline by měla najít tyto soubory automaticky!")
        return True
    else:
        print("⚠️ Žádné Narrator_*.mp3 soubory nenalezeny")
        print(f"   Zkontrolujte: {upload_folder}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("🧪 Google TTS Endpoint Test")
    print("=" * 60)
    print()
    
    # Test 1: TTS endpoint
    success = test_tts_generate()
    
    # Test 2: Video integrace
    if success:
        test_video_integration()
    
    print()
    print("=" * 60)
    print("✅ Test dokončen" if success else "❌ Test selhal")
    print("=" * 60)

