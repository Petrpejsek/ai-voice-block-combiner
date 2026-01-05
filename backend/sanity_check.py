#!/usr/bin/env python3
"""
🔍 Sanity Check - Google TTS Implementation
Ověří všechny kritické komponenty před prvním použitím
"""

import os
import sys
import json

# Barvy pro terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_check(status, message):
    """Print formatted check result"""
    symbol = "✅" if status else "❌"
    color = GREEN if status else RED
    print(f"{symbol} {color}{message}{RESET}")

def print_section(title):
    """Print section header"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

def check_backend_structure():
    """Check 1: Backend struktura"""
    print_section("1. Backend struktura")
    
    checks = []
    
    # Backend entrypoint
    app_py = os.path.exists('backend/app.py')
    print_check(app_py, "backend/app.py existuje")
    checks.append(app_py)
    
    # Requirements
    req_txt = os.path.exists('backend/requirements.txt')
    print_check(req_txt, "backend/requirements.txt existuje")
    checks.append(req_txt)
    
    if req_txt:
        with open('backend/requirements.txt', 'r') as f:
            content = f.read()
            has_google = 'google-auth' in content
            print_check(has_google, "google-auth v requirements.txt (REST API)")
            checks.append(has_google)
    
    # Env example
    env_ex = os.path.exists('backend/env_example.txt')
    print_check(env_ex, "backend/env_example.txt existuje")
    checks.append(env_ex)
    
    if env_ex:
        with open('backend/env_example.txt', 'r') as f:
            content = f.read()
            has_creds = 'GOOGLE_APPLICATION_CREDENTIALS' in content
            print_check(has_creds, "GOOGLE_APPLICATION_CREDENTIALS v env_example.txt")
            checks.append(has_creds)
    
    return all(checks)

def check_endpoint_implementation():
    """Check 2: TTS endpoint"""
    print_section("2. TTS Endpoint")
    
    checks = []
    
    if not os.path.exists('backend/app.py'):
        print_check(False, "backend/app.py nenalezen")
        return False
    
    with open('backend/app.py', 'r') as f:
        content = f.read()
    
    # Endpoint existuje
    has_route = '@app.route(\'/api/tts/generate\'' in content
    print_check(has_route, "Route /api/tts/generate definován")
    checks.append(has_route)
    
    # Tolerantní vstup
    has_tolerance = 'tts_ready_package' in content and 'narration_blocks' in content
    print_check(has_tolerance, "Tolerantní vstup (tts_ready_package/narration_blocks)")
    checks.append(has_tolerance)
    
    # Fixed-width naming
    has_naming = 'Narrator_{i:04d}.mp3' in content
    print_check(has_naming, "Fixed-width naming (Narrator_{i:04d}.mp3)")
    checks.append(has_naming)
    
    # Cleanup
    has_cleanup = 'Narrator_' in content and 'os.remove' in content
    print_check(has_cleanup, "Cleanup starých Narrator_*.mp3")
    checks.append(has_cleanup)
    
    # Retry logic
    has_retry = 'max_retries' in content and 'retry_delay' in content
    print_check(has_retry, "Retry mechanismus s backoff")
    checks.append(has_retry)
    
    # Response JSON
    has_response = 'generated_blocks' in content and 'failed_blocks' in content
    print_check(has_response, "Response JSON s generated/failed blocks")
    checks.append(has_response)
    
    return all(checks)

def check_test_tools():
    """Check 3: Test nástroje"""
    print_section("3. Test nástroje")
    
    checks = []
    
    # Python test
    py_test = os.path.exists('backend/test_tts_endpoint.py')
    print_check(py_test, "backend/test_tts_endpoint.py existuje")
    checks.append(py_test)
    
    # Bash test
    sh_test = os.path.exists('backend/test_tts_curl.sh')
    print_check(sh_test, "backend/test_tts_curl.sh existuje")
    checks.append(sh_test)
    
    if sh_test:
        is_exec = os.access('backend/test_tts_curl.sh', os.X_OK)
        print_check(is_exec, "test_tts_curl.sh je executable")
        checks.append(is_exec)
    
    return all(checks)

def check_documentation():
    """Check 4: Dokumentace"""
    print_section("4. Dokumentace")
    
    checks = []
    
    # Quick start
    quick = os.path.exists('QUICK_START_TTS.md')
    print_check(quick, "QUICK_START_TTS.md existuje")
    checks.append(quick)
    
    # Setup guide
    setup = os.path.exists('GOOGLE_TTS_SETUP.md')
    print_check(setup, "GOOGLE_TTS_SETUP.md existuje")
    checks.append(setup)
    
    # README
    readme = os.path.exists('TTS_MVP_README.md')
    print_check(readme, "TTS_MVP_README.md existuje")
    checks.append(readme)
    
    # Summary
    summary = os.path.exists('TTS_IMPLEMENTATION_SUMMARY.md')
    print_check(summary, "TTS_IMPLEMENTATION_SUMMARY.md existuje")
    checks.append(summary)
    
    return all(checks)

def check_env_configuration():
    """Check 5: ENV konfigurace"""
    print_section("5. ENV konfigurace (uživatel musí doplnit)")
    
    env_path = 'backend/.env'
    env_exists = os.path.exists(env_path)
    
    if env_exists:
        print_check(True, "backend/.env existuje")
        
        with open(env_path, 'r') as f:
            content = f.read()
        
        has_creds = 'GOOGLE_APPLICATION_CREDENTIALS' in content
        print_check(has_creds, "GOOGLE_APPLICATION_CREDENTIALS definován")
        
        if has_creds:
            # Najdi hodnotu
            for line in content.split('\n'):
                if line.startswith('GOOGLE_APPLICATION_CREDENTIALS'):
                    value = line.split('=', 1)[1].strip()
                    if value and not value.startswith('/path/'):
                        creds_exist = os.path.exists(value)
                        print_check(creds_exist, f"Service account JSON existuje: {value}")
                    else:
                        print_check(False, f"GOOGLE_APPLICATION_CREDENTIALS = placeholder")
                        print(f"{YELLOW}   → Uživatel musí nastavit správnou cestu{RESET}")
    else:
        print_check(False, "backend/.env neexistuje")
        print(f"{YELLOW}   → Vytvořte z env_example.txt: cp backend/env_example.txt backend/.env{RESET}")
    
    return True  # ENV check je informativní

def check_video_integration():
    """Check 6: Video pipeline integrace"""
    print_section("6. Video pipeline integrace")
    
    checks = []
    
    with open('backend/app.py', 'r') as f:
        content = f.read()
    
    # Hledání Narrator_*.mp3 v video funkcích
    has_narrator_search = content.count('Narrator_') >= 4  # Multiple places
    print_check(has_narrator_search, "Video funkce hledají Narrator_*.mp3")
    checks.append(has_narrator_search)
    
    # Sorting by name
    has_sort = 'narrator_files.sort()' in content
    print_check(has_sort, "Narrator files jsou sorted (deterministické pořadí)")
    checks.append(has_sort)
    
    # Concatenation
    has_concat = 'concatenate_audioclips' in content
    print_check(has_concat, "MoviePy concatenate_audioclips použito")
    checks.append(has_concat)
    
    return all(checks)

def check_safety():
    """Check 7: Safety checks"""
    print_section("7. Safety checks")
    
    checks = []
    
    # Žádné credentials v kódu
    sensitive_files = ['backend/app.py', 'backend/requirements.txt', 'backend/test_tts_endpoint.py']
    has_secrets = False
    
    for fpath in sensitive_files:
        if os.path.exists(fpath):
            with open(fpath, 'r') as f:
                content = f.read()
                # Hledej patterns jako "service_account_key" nebo JSON obsahy
                if '"type": "service_account"' in content or 'private_key' in content:
                    has_secrets = True
                    print_check(False, f"{fpath} obsahuje credentials!")
    
    if not has_secrets:
        print_check(True, "Žádné credentials v kódu")
        checks.append(True)
    
    # .gitignore pro .env
    gitignore = os.path.exists('.gitignore')
    if gitignore:
        with open('.gitignore', 'r') as f:
            content = f.read()
            has_env = '.env' in content or '*.env' in content
            print_check(has_env, ".env je v .gitignore")
            checks.append(has_env)
    
    return all(checks)

def main():
    """Run all checks"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}🔍 Google TTS Implementation - Sanity Check{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    
    results = []
    
    results.append(("Backend struktura", check_backend_structure()))
    results.append(("TTS Endpoint", check_endpoint_implementation()))
    results.append(("Test nástroje", check_test_tools()))
    results.append(("Dokumentace", check_documentation()))
    results.append(("ENV konfigurace", check_env_configuration()))
    results.append(("Video integrace", check_video_integration()))
    results.append(("Safety", check_safety()))
    
    # Final summary
    print_section("📊 SUMMARY")
    
    all_passed = True
    for name, passed in results:
        print_check(passed, name)
        if not passed:
            all_passed = False
    
    print(f"\n{BLUE}{'='*60}{RESET}")
    
    if all_passed:
        print(f"\n{GREEN}✅ Všechny checks prošly!{RESET}")
        print(f"\n{BLUE}Next steps:{RESET}")
        print("1. Setup Google Cloud (GOOGLE_TTS_SETUP.md)")
        print("2. Nastav backend/.env s credentials")
        print("3. pip install -r backend/requirements.txt")
        print("4. python3 backend/app.py")
        print("5. ./backend/test_tts_curl.sh")
        return 0
    else:
        print(f"\n{RED}❌ Některé checks selhaly{RESET}")
        print(f"{YELLOW}Zkontrolujte výše uvedené chyby před použitím{RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

