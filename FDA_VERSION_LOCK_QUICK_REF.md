# FDA Version Lock - Quick Reference

## 🔍 Jak diagnostikovat problém

### Krok 1: Hledání FDA_DIAGNOSTIC logů

```bash
# Pro konkrétní episode
grep "FDA_DIAGNOSTIC" backend_server.log | grep "episode_id: 'ep_abc123'"

# Všechny version mismatches
grep "FDA_VERSION" backend_server.log | grep -E "(MISMATCH|CHANGED|RESTORED)"
```

### Krok 2: Očekávaný výstup (zdravý případ)

```
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'raw_llm', version: 'fda_v2.7'}
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'post_sanitizer', version: 'fda_v2.7'}
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'post_deterministic_gen', version: 'fda_v2.7'}
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'validator', expected_version: 'fda_v2.7', actual_version: 'fda_v2.7'}
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'final_before_emit', version: 'fda_v2.7', use_v27_mode: True}
✅ FDA: Saved fda_v2.7 shot_plan with X scenes
```

### Krok 3: Problematický případ (LLM vrací špatnou verzi)

```
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'raw_llm', version: 'fda_v3.0'}  ← ❌ LLM PROBLÉM
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'post_sanitizer', version: 'fda_v3.0'}
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'post_deterministic_gen', version: 'fda_v3.0'}
⚠️  FDA_VERSION_CHANGED_IN_POSTPROCESS {episode_id: 'ep_abc123', raw_llm_version: 'fda_v3.0', postprocess_version: 'fda_v3.0'}
🔍 FDA_DIAGNOSTIC {episode_id: 'ep_abc123', stage: 'validator', expected_version: 'fda_v2.7', actual_version: 'fda_v3.0'}
❌ FDA_VERSION_MISMATCH: Expected 'fda_v2.7', got 'fda_v3.0'
```

**Diagnóza:** LLM ignoruje prompt instrukce a vrací `fda_v3.0`.

## 🛠️ Rychlá oprava (pokud problém přetrvává)

### Varianta 1: Force version v run_fda_llm (agresivní fix)

**Soubor:** `backend/footage_director.py:4088` (po parsování LLM outputu)

```python
# HARD FIX: Force version to fda_v2.7 (LLM sometimes ignores prompt)
if isinstance(parsed, dict):
    if "shot_plan" in parsed and isinstance(parsed["shot_plan"], dict):
        if parsed["shot_plan"].get("version") != FDA_V27_VERSION:
            print(f"⚠️  FDA_LLM_WRONG_VERSION {{got: '{parsed['shot_plan'].get('version')}', forcing_to: '{FDA_V27_VERSION}'}}")
            parsed["shot_plan"]["version"] = FDA_V27_VERSION
    elif "version" in parsed:
        if parsed.get("version") != FDA_V27_VERSION:
            print(f"⚠️  FDA_LLM_WRONG_VERSION {{got: '{parsed.get('version')}', forcing_to: '{FDA_V27_VERSION}'}}")
            parsed["version"] = FDA_V27_VERSION
```

**Umístění:** Přidat po řádku s `if parsed is None:` check (cca řádek 4088).

### Varianta 2: Posílit prompt (soft fix)

**Soubor:** `config/llm_defaults.json:30` (prompt template pro footage_director)

Změnit sekci `0) VERSION LOCK (CRITICAL)` na:

```
0) VERSION LOCK (CRITICAL - HIGHEST PRIORITY - DO NOT IGNORE)
- The output MUST always contain: \"version\": \"fda_v2.7\"
- NEVER USE \"fda_v3.0\" or any other version number.
- DO NOT UPGRADE the version even if you think it would be better.
- Before final output: CHECK that shot_plan.version == \"fda_v2.7\"
- If wrong, CORRECT IT to \"fda_v2.7\" BEFORE returning JSON.
- This is NON-NEGOTIABLE. Any other version will cause FAIL.
```

## 📍 Klíčové soubory

| Soubor | Řádek | Co se děje |
|--------|-------|------------|
| `backend/footage_director.py` | 30 | Konstanta `FDA_V27_VERSION = "fda_v2.7"` |
| `backend/footage_director.py` | 4088+ | LLM output parsing + diagnostic log |
| `backend/footage_director.py` | 4119-4143 | Pre-FDA Sanitizer + diagnostic log |
| `backend/footage_director.py` | 4145-4163 | Deterministic generators + diagnostic log |
| `backend/footage_director.py` | 3406-3418 | Validátor version check + diagnostic log |
| `backend/script_pipeline.py` | 1048-1055 | Import FDA_V27_VERSION + use_v27_mode check |
| `backend/script_pipeline.py` | 1162-1172 | Finální version check před emit + diagnostic log |
| `backend/pre_fda_sanitizer.py` | 914-942 | Version lock v sanitizeru |
| `config/llm_defaults.json` | 30 | Prompt template s VERSION LOCK instrukcí |

## 🧪 Jak spustit testy

```bash
cd /Users/petrliesner/podcasts
python3 test_fda_version_lock.py
```

**Očekávaný výstup:**
```
======================================================================
FDA VERSION LOCK TEST SUITE
======================================================================

🧪 Test 1: FDA_V27_VERSION constant
   ✅ PASS: Konstanta má správnou hodnotu

🧪 Test 2: Pre-FDA Sanitizer preserves version
   ✅ PASS: Sanitizer zachoval verzi

🧪 Test 3: Deterministic generators preserve version
   ✅ PASS: Deterministic generators zachovaly verzi

🧪 Test 4: Validator detects wrong version
   ✅ PASS: Validátor správně detekoval špatnou verzi

======================================================================
RESULTS: 4 passed, 0 failed
======================================================================
```

## 📚 Související dokumentace

- **Detailní dokumentace:** `FDA_VERSION_LOCK_FIX.md`
- **FDA obecná dokumentace:** `FDA_README.md`
- **Troubleshooting:** `FDA_TROUBLESHOOTING.md`

## 💡 Poznámky

1. **Verze NESMÍ být měněna v postprocessingu** - je to výstup LLM, ne naše odpovědnost
2. **Pokud LLM vrací špatnou verzi** → problém je v LLM, ne v kódu
3. **Defensive programming** - máme hard locks + diagnostic logs na každém kroku
4. **Single source of truth** - vždy používat konstantu `FDA_V27_VERSION`, nikdy hardcoded string

---

**Last updated:** 2026-01-01  
**Status:** ✅ Implementováno



