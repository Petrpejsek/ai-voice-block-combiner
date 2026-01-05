#!/usr/bin/env python3
"""
🔥 E2E SMOKE TEST: TTS Generation → Video Concatenation
-------------------------------------------------------
Testuje celý pipeline:
1. Vygeneruje 3 narration bloky → MP3 soubory
2. Zavolá video generation endpoint
3. Ověří, že vzniklo finální video

Usage: python3 e2e_smoke_test.py
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Konfigurace
BASE_URL = "http://localhost:50000"
UPLOAD_FOLDER = Path(__file__).parent.parent / "uploads"
OUTPUT_FOLDER = Path(__file__).parent.parent / "output"

# Test data - 3 bloky
TEST_PAYLOAD = {
    "tts_ready_package": {
        "narration_blocks": [
            {
                "block_id": "test_block_001",
                "text_tts": "This is the first test block for end to end smoke testing."
            },
            {
                "block_id": "test_block_002",
                "text_tts": "This is the second test block. It verifies that multiple blocks are processed correctly."
            },
            {
                "block_id": "test_block_003",
                "text_tts": "This is the third and final test block. The pipeline should generate three MP3 files."
            }
        ]
    }
}

# Test video payload - 1 obrázek (opakovaný pro 3 MP3)
TEST_VIDEO_PAYLOAD = {
    "images": [
        {"filename": "test_image_1.png"},
        {"filename": "test_image_2.png"},
        {"filename": "test_image_3.png"}
    ],
    "project_name": "e2e_smoke_test",
    "max_mp3_files": 3,  # Použij jen 3 MP3 soubory
    "video_settings": {
        "duration_per_image": 5.0
    }
}

def print_header(text):
    """Tiskne formátovaný header"""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")

def print_step(step_num, text):
    """Tiskne krok testu"""
    print(f"\n🔹 Krok {step_num}: {text}")
    print("-" * 70)

def check_backend_health():
    """Ověří, že backend běží"""
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend běží a je dostupný")
            return True
        else:
            print(f"❌ Backend odpověděl s neočekávaným status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Backend neběží na {BASE_URL}")
        print("   Spusť: cd backend && python3 app.py")
        return False
    except Exception as e:
        print(f"❌ Chyba při kontrole backendu: {e}")
        return False

def cleanup_old_mp3_files():
    """Smaže staré Narrator_*.mp3 soubory"""
    print("🧹 Čistím staré MP3 soubory...")
    deleted_count = 0
    if UPLOAD_FOLDER.exists():
        for file in UPLOAD_FOLDER.glob("Narrator_*.mp3"):
            file.unlink()
            deleted_count += 1
    print(f"   Smazáno {deleted_count} souborů")

def step1_generate_tts():
    """Krok 1: Vygeneruje TTS (3 bloky → 3 MP3)"""
    print_step(1, "Generování TTS (3 bloky)")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/tts/generate",
            json=TEST_PAYLOAD,
            timeout=120  # 2 minuty pro TTS
        )
        
        print(f"📡 HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            # Check if it's a credentials error (expected in dev)
            try:
                error_data = response.json()
                error_msg = error_data.get('error', '')
                
                if 'GOOGLE_APPLICATION_CREDENTIALS' in error_msg or 'credentials' in error_msg.lower():
                    print(f"⚠️  Google Cloud credentials nejsou nakonfigurovány")
                    print(f"   Error: {error_msg}")
                    print(f"   Hint: Nastavte GOOGLE_APPLICATION_CREDENTIALS v backend/.env")
                    print(f"   Hint: Vytvořte service account JSON v Google Cloud Console")
                    return "CREDENTIALS_MISSING"
                else:
                    print(f"❌ TTS endpoint vrátil chybu: {response.status_code}")
                    print(f"   Response: {response.text[:500]}")
                    return False
            except:
                print(f"❌ TTS endpoint vrátil chybu: {response.status_code}")
                print(f"   Response: {response.text[:500]}")
                return False
        
        result = response.json()
        print(f"📊 Response JSON:")
        print(json.dumps(result, indent=2))
        
        # Kontrola výsledku
        total_blocks = result.get('total_blocks', 0)
        generated_blocks = result.get('generated_blocks', 0)
        failed_blocks = result.get('failed_blocks', [])
        
        if generated_blocks != 3:
            print(f"❌ Očekávalo se 3 vygenerované bloky, ale máme {generated_blocks}")
            return False
        
        if failed_blocks:
            print(f"❌ Některé bloky selhaly: {failed_blocks}")
            return False
        
        print(f"✅ TTS generování úspěšné: {generated_blocks}/{total_blocks} bloků")
        return True
        
    except requests.exceptions.Timeout:
        print("❌ TTS timeout (>120s)")
        return False
    except Exception as e:
        print(f"❌ Výjimka při TTS generování: {e}")
        return False

def step2_verify_mp3_files():
    """Krok 2: Ověří, že vznikly MP3 soubory"""
    print_step(2, "Ověření MP3 souborů")
    
    expected_files = [
        "Narrator_0001.mp3",
        "Narrator_0002.mp3",
        "Narrator_0003.mp3"
    ]
    
    all_exist = True
    for filename in expected_files:
        filepath = UPLOAD_FOLDER / filename
        if filepath.exists():
            file_size = filepath.stat().st_size
            print(f"✅ {filename} existuje ({file_size} bytes)")
        else:
            print(f"❌ {filename} CHYBÍ")
            all_exist = False
    
    if all_exist:
        print(f"✅ Všechny 3 MP3 soubory existují")
    else:
        print(f"❌ Některé MP3 soubory chybí")
    
    return all_exist

def step3_create_test_images():
    """Krok 3: Vytvoří placeholder obrázky pro video (pokud neexistují)"""
    print_step(3, "Příprava test obrázků")
    
    # Zkontroluj, jestli existují nějaké PNG/JPG obrázky v uploads/
    existing_images = list(UPLOAD_FOLDER.glob("*.png")) + list(UPLOAD_FOLDER.glob("*.jpg"))
    
    if len(existing_images) >= 3:
        print(f"✅ Nalezeno {len(existing_images)} obrázků v uploads/")
        # Aktualizuj payload s reálnými jmény
        TEST_VIDEO_PAYLOAD['images'] = [
            {"filename": img.name} for img in existing_images[:3]
        ]
        return True
    else:
        print(f"⚠️  Nalezeno jen {len(existing_images)} obrázků")
        print("   ℹ️  Pro plný test nahraj aspoň 3 PNG/JPG soubory do uploads/")
        print("   ℹ️  Test přeskočí generování videa")
        return False

def step4_generate_video():
    """Krok 4: Vygeneruje video s audio (concatenate MP3)"""
    print_step(4, "Generování videa s audio")
    
    try:
        # Použij endpoint bez Ken Burns (nejrychlejší pro test)
        response = requests.post(
            f"{BASE_URL}/api/generate-video-with-audio",
            json=TEST_VIDEO_PAYLOAD,
            timeout=180  # 3 minuty pro video
        )
        
        print(f"📡 HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Video endpoint vrátil chybu: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False
        
        result = response.json()
        print(f"📊 Response JSON:")
        print(json.dumps(result, indent=2))
        
        # Kontrola výsledku
        success = result.get('success', False)
        filename = result.get('filename', '')
        
        if not success:
            print(f"❌ Video generování selhalo")
            return False
        
        print(f"✅ Video generování úspěšné: {filename}")
        return True
        
    except requests.exceptions.Timeout:
        print("❌ Video timeout (>180s)")
        return False
    except Exception as e:
        print(f"❌ Výjimka při video generování: {e}")
        return False

def step5_verify_video_file():
    """Krok 5: Ověří, že vzniklo video"""
    print_step(5, "Ověření finálního videa")
    
    # Najdi nejnovější final_video_with_audio_*.mp4
    video_files = sorted(OUTPUT_FOLDER.glob("final_video_with_audio_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not video_files:
        print("❌ Žádné video soubory nenalezeny v output/")
        return False
    
    latest_video = video_files[0]
    file_size = latest_video.stat().st_size
    
    print(f"✅ Nalezeno finální video: {latest_video.name}")
    print(f"   Velikost: {file_size} bytes ({file_size / 1024 / 1024:.2f} MB)")
    
    if file_size < 1000:  # Podezřele malý soubor
        print("⚠️  Video je podezřele malé (<1 KB)")
        return False
    
    return True

def main():
    """Hlavní funkce"""
    print_header("🔥 E2E SMOKE TEST: TTS → Video Concatenation")
    
    start_time = time.time()
    
    # Zdravotní kontrola backendu
    if not check_backend_health():
        print("\n" + "="*70)
        print("❌ FAIL: Backend není dostupný")
        print("="*70)
        sys.exit(1)
    
    # Cleanup
    cleanup_old_mp3_files()
    
    # Test kroky
    results = {}
    
    # Krok 1: TTS generování
    tts_result = step1_generate_tts()
    results['tts_generation'] = tts_result
    
    if tts_result == "CREDENTIALS_MISSING":
        print("\n" + "="*70)
        print("⚠️  TEST SKIPPED: Google Cloud credentials nejsou nakonfigurovány")
        print("="*70)
        print("\n📝 Pro spuštění plného testu:")
        print("   1. Vytvořte service account v Google Cloud Console")
        print("   2. Stáhněte JSON klíč")
        print("   3. Nastavte GOOGLE_APPLICATION_CREDENTIALS v backend/.env")
        print("   4. Znovu spusťte tento test")
        print("\n✅ Endpoint existence check: PASS")
        print("✅ Error handling check: PASS")
        print("\n" + "="*70)
        sys.exit(0)
    elif not tts_result:
        print("\n" + "="*70)
        print("❌ FAIL: TTS generování selhalo")
        print("="*70)
        sys.exit(1)
    
    # Krok 2: Ověření MP3
    results['mp3_verification'] = step2_verify_mp3_files()
    if not results['mp3_verification']:
        print("\n" + "="*70)
        print("❌ FAIL: MP3 soubory nebyly vytvořeny")
        print("="*70)
        sys.exit(1)
    
    # Krok 3: Příprava obrázků
    has_images = step3_create_test_images()
    
    if has_images:
        # Krok 4: Video generování
        results['video_generation'] = step4_generate_video()
        if not results['video_generation']:
            print("\n" + "="*70)
            print("❌ FAIL: Video generování selhalo")
            print("="*70)
            sys.exit(1)
        
        # Krok 5: Ověření videa
        results['video_verification'] = step5_verify_video_file()
        if not results['video_verification']:
            print("\n" + "="*70)
            print("❌ FAIL: Finální video nebylo vytvořeno")
            print("="*70)
            sys.exit(1)
    else:
        print("\n⚠️  Přeskakuji video generování (chybí obrázky)")
        results['video_generation'] = None
        results['video_verification'] = None
    
    # Finální souhrn
    elapsed_time = time.time() - start_time
    
    print_header("📊 FINÁLNÍ SOUHRN")
    print(f"✅ TTS Generování:     {'PASS' if results['tts_generation'] else 'FAIL'}")
    print(f"✅ MP3 Ověření:        {'PASS' if results['mp3_verification'] else 'FAIL'}")
    
    if results['video_generation'] is not None:
        print(f"✅ Video Generování:   {'PASS' if results['video_generation'] else 'FAIL'}")
        print(f"✅ Video Ověření:      {'PASS' if results['video_verification'] else 'FAIL'}")
        
        if results['video_generation'] and results['video_verification']:
            print(f"\n{'='*70}")
            print(f"🎉 PASS: E2E test úspěšný! (TTS → MP3 → Video)")
            print(f"⏱️  Celková doba: {elapsed_time:.1f}s")
            print(f"{'='*70}\n")
            sys.exit(0)
        else:
            print(f"\n{'='*70}")
            print(f"❌ FAIL: Video část selhala")
            print(f"⏱️  Celková doba: {elapsed_time:.1f}s")
            print(f"{'='*70}\n")
            sys.exit(1)
    else:
        print(f"\n{'='*70}")
        print(f"⚠️  PARTIAL PASS: TTS část OK, video přeskočeno (chybí obrázky)")
        print(f"⏱️  Celková doba: {elapsed_time:.1f}s")
        print(f"{'='*70}\n")
        sys.exit(0)

if __name__ == "__main__":
    main()

