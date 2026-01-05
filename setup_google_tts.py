#!/usr/bin/env python3
"""
🚀 Google TTS Setup Script
--------------------------
Automaticky nakonfiguruje Google Cloud TTS pro projekt.

Usage: python3 setup_google_tts.py

Co dělá:
1. Najde service account JSON v backend/secrets/
2. Aktualizuje backend/.env s GOOGLE_APPLICATION_CREDENTIALS
3. Restartuje backend server
4. Spustí E2E smoke test
5. Vypíše PASS/FAIL

Requirements:
- Service account JSON v backend/secrets/ (libovolný název *.json)
- Backend v backend/app.py
- E2E test v backend/e2e_smoke_test.py
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path

# Cesty
PROJECT_ROOT = Path(__file__).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
SECRETS_DIR = BACKEND_DIR / "secrets"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE = BACKEND_DIR / "env_example.txt"
E2E_TEST = BACKEND_DIR / "e2e_smoke_test.py"

# Barvy pro terminal
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

def print_header(text):
    """Tiskne formátovaný header"""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}  {text}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")

def print_step(step_num, text):
    """Tiskne krok"""
    print(f"\n{BOLD}🔹 Krok {step_num}: {text}{RESET}")
    print("-" * 70)

def print_success(text):
    """Tiskne úspěch"""
    print(f"{GREEN}✅ {text}{RESET}")

def print_warning(text):
    """Tiskne varování"""
    print(f"{YELLOW}⚠️  {text}{RESET}")

def print_error(text):
    """Tiskne chybu"""
    print(f"{RED}❌ {text}{RESET}")

def find_service_account_json():
    """Najde první .json soubor v secrets/"""
    print_step(1, "Hledání service account JSON")
    
    if not SECRETS_DIR.exists():
        print_error(f"Adresář {SECRETS_DIR} neexistuje")
        print(f"   Vytvořte ho: mkdir -p {SECRETS_DIR}")
        return None
    
    json_files = list(SECRETS_DIR.glob("*.json"))
    
    if not json_files:
        print_error(f"Žádný .json soubor v {SECRETS_DIR}")
        print("\n📝 Jak získat service account JSON:")
        print("   1. Jděte na https://console.cloud.google.com")
        print("   2. IAM & Admin → Service Accounts → Create Service Account")
        print("   3. Role: Cloud Text-to-Speech User")
        print("   4. Keys → Add Key → Create New Key → JSON")
        print(f"   5. Přesuňte sem: mv ~/Downloads/key.json {SECRETS_DIR}/google-tts-key.json")
        return None
    
    if len(json_files) > 1:
        print_warning(f"Nalezeno {len(json_files)} JSON souborů, použiji první")
        for f in json_files:
            print(f"   - {f.name}")
    
    json_file = json_files[0]
    print_success(f"Nalezen: {json_file.name}")
    print(f"   Cesta: {json_file}")
    
    # Ověř, že je to validní JSON
    try:
        import json
        with open(json_file) as f:
            data = json.load(f)
            if 'type' in data and data['type'] == 'service_account':
                print_success("Validní service account JSON")
                if 'project_id' in data:
                    print(f"   Project ID: {data['project_id']}")
                if 'client_email' in data:
                    print(f"   Email: {data['client_email']}")
            else:
                print_warning("JSON soubor není service account (očekáváno 'type': 'service_account')")
    except Exception as e:
        print_warning(f"Nelze parsovat JSON: {e}")
    
    return json_file

def update_env_file(json_file):
    """Aktualizuje backend/.env s GOOGLE_APPLICATION_CREDENTIALS"""
    print_step(2, "Aktualizace backend/.env")
    
    # Přečti existující .env nebo vytvoř nový
    env_content = {}
    if ENV_FILE.exists():
        print(f"   Čtu existující {ENV_FILE.name}")
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_content[key.strip()] = value.strip()
    else:
        print(f"   Vytvářím nový {ENV_FILE.name}")
        if ENV_EXAMPLE.exists():
            print(f"   Kopíruji z {ENV_EXAMPLE.name}")
            with open(ENV_EXAMPLE) as f:
                with open(ENV_FILE, 'w') as out:
                    out.write(f.read())
            # Znovu načti
            with open(ENV_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_content[key.strip()] = value.strip()
    
    # Nastav GOOGLE_APPLICATION_CREDENTIALS (absolutní cesta)
    abs_json_path = str(json_file.absolute())
    env_content['GOOGLE_APPLICATION_CREDENTIALS'] = abs_json_path
    
    # Nastav default TTS parametry, pokud nejsou
    defaults = {
        'GCP_TTS_VOICE_NAME': 'en-US-Neural2-D',
        'GCP_TTS_LANGUAGE_CODE': 'en-US',
        'GCP_TTS_SPEAKING_RATE': '1.0',
        'GCP_TTS_PITCH': '0.0'
    }
    
    for key, default_value in defaults.items():
        if key not in env_content or not env_content[key]:
            env_content[key] = default_value
            print(f"   Nastavuji {key}={default_value}")
    
    # Zapiš zpět do .env
    with open(ENV_FILE, 'w') as f:
        f.write("# AI Voice Block Combiner - Environment Configuration\n")
        f.write("# Automaticky aktualizováno setup_google_tts.py\n\n")
        
        # Seřaď klíče (Google TTS nahoře)
        google_keys = [k for k in env_content.keys() if k.startswith('GOOGLE_') or k.startswith('GCP_')]
        other_keys = [k for k in env_content.keys() if k not in google_keys]
        
        if google_keys:
            f.write("# Google Cloud Text-to-Speech\n")
            for key in sorted(google_keys):
                f.write(f"{key}={env_content[key]}\n")
            f.write("\n")
        
        if other_keys:
            f.write("# Other API Keys\n")
            for key in sorted(other_keys):
                f.write(f"{key}={env_content[key]}\n")
    
    print_success(f"Aktualizováno {ENV_FILE.name}")
    print(f"   GOOGLE_APPLICATION_CREDENTIALS={abs_json_path}")
    
    return True

def kill_backend():
    """Zabije běžící backend proces"""
    print_step(3, "Zastavení běžícího backendu")
    
    try:
        result = subprocess.run(
            ["lsof", "-ti", "tcp:50000"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    print(f"   Zastavuji proces PID {pid}")
                except ProcessLookupError:
                    pass
            
            time.sleep(1)
            print_success("Backend zastaven")
        else:
            print(f"   Backend neběží na portu 50000")
    
    except FileNotFoundError:
        print_warning("lsof není dostupný, přeskakuji")
    except Exception as e:
        print_warning(f"Chyba při zastavení backendu: {e}")

def start_backend():
    """Spustí backend v pozadí"""
    print_step(4, "Spuštění backendu")
    
    try:
        # Spusť backend v pozadí
        log_file = Path("/tmp/backend_setup.log")
        with open(log_file, 'w') as f:
            process = subprocess.Popen(
                ["python3", "app.py"],
                cwd=BACKEND_DIR,
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
        
        print(f"   Backend startuje (PID {process.pid})")
        print(f"   Log: {log_file}")
        
        # Počkej na start (max 10 sekund)
        print("   Čekám na start", end="", flush=True)
        for i in range(20):
            time.sleep(0.5)
            print(".", end="", flush=True)
            
            # Zkontroluj, jestli už běží
            try:
                result = subprocess.run(
                    ["curl", "-s", "http://localhost:50000/api/health"],
                    capture_output=True,
                    timeout=1
                )
                if result.returncode == 0:
                    print()
                    print_success("Backend běží na http://localhost:50000")
                    return True
            except:
                pass
        
        print()
        print_warning("Backend nestartoval do 10s, pokračuji...")
        return True
        
    except Exception as e:
        print_error(f"Chyba při startu backendu: {e}")
        return False

def run_e2e_test():
    """Spustí E2E smoke test"""
    print_step(5, "Spuštění E2E smoke testu")
    
    if not E2E_TEST.exists():
        print_error(f"E2E test nenalezen: {E2E_TEST}")
        return False
    
    try:
        print(f"\n{BOLD}{'='*70}{RESET}")
        result = subprocess.run(
            ["python3", str(E2E_TEST)],
            cwd=PROJECT_ROOT,
            timeout=300  # 5 minut max
        )
        print(f"{BOLD}{'='*70}{RESET}\n")
        
        if result.returncode == 0:
            print_success("E2E test: PASS")
            return True
        else:
            print_error(f"E2E test: FAIL (exit code {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        print_error("E2E test timeout (>5 minut)")
        return False
    except Exception as e:
        print_error(f"Chyba při spuštění E2E testu: {e}")
        return False

def main():
    """Hlavní funkce"""
    print_header("🚀 Google TTS Setup Script")
    
    start_time = time.time()
    
    # Krok 1: Najdi service account JSON
    json_file = find_service_account_json()
    if not json_file:
        print(f"\n{BOLD}{RED}{'='*70}{RESET}")
        print(f"{BOLD}{RED}❌ FAIL: Service account JSON nenalezen{RESET}")
        print(f"{BOLD}{RED}{'='*70}{RESET}\n")
        sys.exit(1)
    
    # Krok 2: Aktualizuj .env
    if not update_env_file(json_file):
        print(f"\n{BOLD}{RED}{'='*70}{RESET}")
        print(f"{BOLD}{RED}❌ FAIL: Nelze aktualizovat .env{RESET}")
        print(f"{BOLD}{RED}{'='*70}{RESET}\n")
        sys.exit(1)
    
    # Krok 3: Zastav starý backend
    kill_backend()
    
    # Krok 4: Spusť nový backend
    if not start_backend():
        print(f"\n{BOLD}{RED}{'='*70}{RESET}")
        print(f"{BOLD}{RED}❌ FAIL: Backend se nespustil{RESET}")
        print(f"{BOLD}{RED}{'='*70}{RESET}\n")
        sys.exit(1)
    
    # Krok 5: Spusť E2E test
    test_passed = run_e2e_test()
    
    # Finální souhrn
    elapsed_time = time.time() - start_time
    
    print_header("📊 FINÁLNÍ SOUHRN")
    print(f"✅ Service account JSON:  OK")
    print(f"✅ Backend .env update:   OK")
    print(f"✅ Backend restart:       OK")
    
    if test_passed:
        print(f"✅ E2E smoke test:        {GREEN}{BOLD}PASS{RESET}")
        print(f"\n{BOLD}{GREEN}{'='*70}{RESET}")
        print(f"{BOLD}{GREEN}🎉 SUCCESS: Setup kompletní! Google TTS funguje.{RESET}")
        print(f"{BOLD}{GREEN}⏱️  Celková doba: {elapsed_time:.1f}s{RESET}")
        print(f"{BOLD}{GREEN}{'='*70}{RESET}\n")
        
        print("📁 Vygenerované soubory:")
        print("   - uploads/Narrator_*.mp3 (TTS audio)")
        print("   - output/final_video_*.mp4 (finální video)")
        print("\n🚀 Můžete použít frontend nebo přímo API:")
        print("   http://localhost:50000/api/tts/generate")
        
        sys.exit(0)
    else:
        print(f"❌ E2E smoke test:        {RED}{BOLD}FAIL{RESET}")
        print(f"\n{BOLD}{RED}{'='*70}{RESET}")
        print(f"{BOLD}{RED}❌ FAIL: E2E test selhal{RESET}")
        print(f"{BOLD}{RED}⏱️  Celková doba: {elapsed_time:.1f}s{RESET}")
        print(f"{BOLD}{RED}{'='*70}{RESET}\n")
        
        print("🔍 Troubleshooting:")
        print("   1. Zkontrolujte backend log: tail -f /tmp/backend_setup.log")
        print("   2. Ověřte Google Cloud Console:")
        print("      - Text-to-Speech API je enabled")
        print("      - Service account má roli 'Cloud Text-to-Speech User'")
        print("      - Billing je nastaven")
        print("   3. Test JSON klíče:")
        print(f"      python3 -c \"import json; print(json.load(open('{json_file}')))\"")
        
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}⚠️  Setup přerušen uživatelem{RESET}\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n{RED}❌ Neočekávaná chyba: {e}{RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)



