# Query Guardrails - Final Implementation Summary

## ✅ Všechny požadavky splněny

### A) Co bylo špatně a proč

**Identifikované problémy:**
1. ❌ "United States Navy" → tahal "US Navy Band"
2. ❌ "World War One" → tahal PlayStation, Wii, webm
3. ❌ "1812" → příliš široké bez entity

**Root cause:** Queries byly příliš široké, chyběly konkrétní kotvy.

---

### B) 3 Pravidla - IMPLEMENTOVÁNO

#### 1) ANCHOR RULE ✅

**Implementace:** `backend/query_guardrails.py` řádky 26-114

**Pravidlo:**
```python
# Anchor = ONE of:
# 1. Specific entity: Person/Ship/Battle/Location name
# 2. Multi-word phrase that is NOT broad epoch/org
# 3. Specific quoted phrase

# Year can SUPPLEMENT but never BE the only anchor
# Broad terms like "World War One" or "United States Navy" are NOT anchors
```

**Stoplist broad terms:**
- Epochs: `world war one`, `cold war`, `vietnam war`, `civil war`, etc.
- Organizations: `united states navy`, `us navy`, `royal navy`, etc.

**Test results:**
```
✅ 'World War One' → REJECTED (too broad)
✅ 'United States Navy' → REJECTED (too broad)
✅ '1812 retreat' → REJECTED (year-only)
✅ 'Napoleon 1812' → ACCEPTED (entity + year)
✅ 'USS Enterprise United States Navy' → ACCEPTED (ship + org)
```

#### 2) MEDIA INTENT ✅

**Implementace:** `backend/query_guardrails.py` řádky 144-171

**Whitelist:**
```python
MEDIA_INTENT_TOKENS = {
    'photo', 'photograph', 'archival', 'archive',
    'map', 'maps',
    'document', 'documents',
    'portrait', 'engraving', 'illustration',
    'newspaper', 'manuscript', 'letter',
    'footage', 'film'  # For video queries
}
```

**Shot type mapping:**
```python
'maps_context' → "map"
'archival_documents' → "document"
'portrait' → "photograph"
default → "archival photograph"
```

**Test results:**
```
✅ Map shot → 100% queries contain "map"
✅ Document shot → 100% queries contain "document"
✅ Missing intent → Auto-added based on shot_type
```

#### 3) NOISE GUARD ✅

**Implementace:** `backend/query_guardrails.py` řádky 103-173

**Stoplist (word-boundary match):**
```python
NOISE_STOPLIST = {
    'band', 'album', 'remix', 'soundtrack',
    'game', 'games', 'playstation', 'xbox', 'wii',
    'pc dvd', 'webm', 'meme',
    'youtube', 'tiktok', 'compilation',
}
```

**Legitimate contexts (no false positives):**
```python
LEGITIMATE_CONTEXTS = {
    'game': ['olympic', 'olympics', 'ancient', 'arena'],
    'games': ['olympic', 'olympics', 'ancient'],
}
```

**Test results:**
```
✅ 'Olympic Games Athens' → PASSED (legitimate)
✅ 'Ancient Games Rome' → PASSED (legitimate)
✅ 'video game footage' → REJECTED (noise)
✅ 'games compilation' → REJECTED (noise)
```

---

### C) Žádný Silent Fallback ✅

**PŘED (NEBEZPEČNÉ):**
```python
if QUERY_GUARDRAILS_AVAILABLE:
    validated = apply_guardrails(...)
else:
    queries = raw_queries  # ❌ SILENT FALLBACK
```

**PO (HARD FAIL):**
```python
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError(
        "QUERY_GUARDRAILS_UNAVAILABLE: Cannot proceed without validation"
    )

validated = apply_guardrails(...)
```

**Startup log:**
```
✅ Query Guardrails úspěšně načteny
```

Nebo:
```
❌ CRITICAL: Query Guardrails import failed: {error}
❌ Pipeline will FAIL on query generation without guardrails!
```

**Graceful degradation:**
- Low coverage → `diagnostics['low_coverage'] = True`
- Logged: `⚠️ Scene sc_0001: LOW COVERAGE - only 3/5 valid queries`
- Stored: `scene['_query_diagnostics']`
- **Nikdy ne tichý fallback k raw queries**

---

### D) Jasný kontrakt na episode_topic ✅

**PŘED (HACK):**
```python
# ❌ Fallback z first narration block
episode_topic = extract_from_narration_heuristic(...)
```

**PO (CLEAN CONTRACT):**
```python
# visual_planning_v3.py řádky 540-555
episode_topic = episode_metadata.get("title", "").strip()
if not episode_topic:
    episode_topic = episode_metadata.get("topic", "").strip()

if not episode_topic:
    raise ValueError(
        "EPISODE_TOPIC_MISSING: episode_metadata must contain 'title' or 'topic'. "
        "Cannot generate anchored queries without episode context. "
        "Refusing to extract from narration (hacky fallback forbidden)."
    )
```

**Kontrakt:**
- Source: `tts_ready_package["episode_metadata"]["title"]` OR `["topic"]`
- Fallback: **NONE** (hard fail pokud chybí)
- No heuristics z narration

**footage_director.py:**
- Používá `episode_anchor_hints` z `_extract_episode_anchor_terms_v27()`
- Tato funkce už pracuje s episode metadata (ne narration)

---

### E) Integrace v správných místech ✅

#### footage_director.py

**Funkce:** `apply_deterministic_generators_v27()` (řádky 3536-3575)

**Workflow:**
1. Generate raw queries: `_generate_deterministic_queries_v27()`
2. Apply guardrails: `validate_and_fix_queries()`
3. Store diagnostics: `scene['_query_diagnostics']`
4. Hard fail pokud guardrails unavailable

#### visual_planning_v3.py

**Funkce:** `_queries_for_scene()` (řádky 518-534)

**Workflow:**
1. Generate deterministic queries
2. Apply guardrails: `validate_and_fix_queries()`
3. Hard fail pokud guardrails unavailable
4. Return validated[:5]

**Garance:** Guardrails se volají JEDNOU per scene (final pass).

---

### F) Diagnostika do UI ✅

**Uloženo v:** `scene['_query_diagnostics']`

**Formát:**
```python
{
    'original_count': 5,           # Vygenerováno
    'valid_count': 3,              # Okamžitě validní
    'invalid_count': 2,            # Selhaly validaci
    'refined_count': 1,            # Opraveno refinement
    'regenerated_count': 1,        # Vygenerováno z template
    'final_count': 5,              # Celkem vráceno
    'low_coverage': False,         # True pokud < minimum
    'rejection_reasons': {         # Důvody zamítnutí
        'NO_ANCHOR': 1,
        'NO_MEDIA_INTENT': 1,
        'STOPLIST_HIT': 0,
        'TOO_SHORT': 0
    }
}
```

**Logy (example):**
```
✅ Scene sc_0001: Generated 5 queries (validated)

   Query validation: 3/5 valid
   Rejection reasons: {'NO_ANCHOR': 2}
   ✓ Refined: 'World War One' → 'USS Cyclops World War One document'
   ✓ Refined: 'United States Navy' → 'Admiral Nimitz United States Navy photograph'
✅ Scene sc_0001: Generated 5 queries (validated)
```

---

### G) Testy ✅

#### Unit testy - Critical cases

**Soubor:** `backend/test_query_guardrails_unit.py`

**Spuštění:**
```bash
cd backend && python3 test_query_guardrails_unit.py
```

**Výsledek:**
```
✅ Year-only anchor correctly rejected
✅ 'Olympic Games' NOT blocked (legitimate context)
✅ Map shot contains 'map'
✅ Max 2 regen attempts, low_coverage flag set
✅ No infinite loop detected

🎉 ALL UNIT TESTS PASSED!
```

#### Specific tests - Production issues

**Soubor:** `backend/test_query_guardrails_specific.py`

**Spuštění:**
```bash
cd backend && python3 test_query_guardrails_specific.py
```

**Výsledek:**
```
✅ 'World War One' rejected (too broad)
✅ 'United States Navy' rejected (too broad)
✅ Repairs add SPECIFIC anchors from beat/episode
✅ No broad epoch terms pass without specific entities

🎉 ALL SPECIFIC TESTS PASSED!
```

#### Test bez guardrails (hard fail expected)

**Test:** Pokud guardrails nejde importnout → pipeline musí failnout

**Implementace:**
```python
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError("QUERY_GUARDRAILS_UNAVAILABLE: ...")
```

**Status:** ✅ Ověřeno (pipeline failuje hned při prvním query generation)

---

### H) Postup ověření

#### 1. Unit testy
```bash
cd backend
python3 test_query_guardrails_unit.py
python3 test_query_guardrails_specific.py
```

**Očekávaný výstup:**
```
🎉 ALL UNIT TESTS PASSED!
🎉 ALL SPECIFIC TESTS PASSED!
```

#### 2. Restart aplikace
```bash
cd /Users/petrliesner/podcasts
./dev.sh restart
```

**Check startup log:**
```bash
head -n 50 /tmp/backend_restart.log | grep Guardrails
```

**Očekávaný výstup:**
```
✅ Query Guardrails úspěšně načteny
```

#### 3. Smoke test - Vytvoř epizodu

**V UI:**
1. Vytvoř novou epizodu s tématem "USS Cyclops Mystery" nebo "Admiral Nimitz"
2. Spusť pipeline (FDA)
3. Zkontroluj logy

**Expected v logách:**
```
✅ Scene sc_0001: Generated 5 queries (validated)
   Query validation: X/5 valid
   Rejection reasons: {...}
   ✓ Refined: 'broad query' → 'specific query'
```

**Ověř:**
- ❌ "World War One" se NESMÍ propustit bez entity
- ❌ "United States Navy" se NESMÍ propustit bez entity  
- ✅ Všechny queries mají anchor + media intent

#### 4. Check scene diagnostics

**V kódu/debug:**
```python
for scene in shot_plan['scenes']:
    diag = scene.get('_query_diagnostics', {})
    print(f"Scene {scene['scene_id']}:")
    print(f"  Original: {diag['original_count']}")
    print(f"  Final: {diag['final_count']}")
    print(f"  Rejected: {diag['rejection_reasons']}")
    print(f"  Refined: {diag['refined_count']}")
```

---

## Checklist - Všechny požadavky

| Požadavek | Status | Poznámka |
|-----------|--------|----------|
| A) Identifikace problému | ✅ DONE | USN, WWI příliš široké |
| B1) Anchor rule (konkrétní) | ✅ DONE | Broad terms stoplist |
| B2) Media intent | ✅ DONE | Whitelist + shot_type mapping |
| B3) Noise guard | ✅ DONE | Stoplist + legitimate contexts |
| C) Žádný silent fallback | ✅ DONE | Hard fail když guardrails missing |
| D) Episode topic kontrakt | ✅ DONE | Pouze z metadata, no heuristics |
| E) Správná integrace | ✅ DONE | footage_director + visual_planning_v3 |
| F) Diagnostika do UI | ✅ DONE | _query_diagnostics per scene |
| G) Testy - unit | ✅ DONE | test_query_guardrails_unit.py |
| G) Testy - specific | ✅ DONE | test_query_guardrails_specific.py |
| G) Test - no fallback | ✅ DONE | Hard fail verified |
| H) Postup ověření | ✅ DONE | 4-step verification guide |

---

## Status

**🎯 COMPLETE - Ready for production smoke test**

**Next step:** Spusť reálnou epizodu a ověř že:
1. Žádný "World War One" bez entity
2. Žádný "United States Navy" bez entity
3. Všechny queries mají anchor + intent
4. Low coverage je logged, ne tichý

**Files:**
- `backend/query_guardrails.py` (kompletní implementace)
- `backend/test_query_guardrails_unit.py` (5 critical tests)
- `backend/test_query_guardrails_specific.py` (4 production tests)
- `backend/footage_director.py` (integrace + hard fail)
- `backend/visual_planning_v3.py` (integrace + hard fail)

**Tests passing:**
```bash
✅ python3 test_query_guardrails_unit.py
✅ python3 test_query_guardrails_specific.py
```

**Backend running:**
```
✅ http://localhost:50000 (Query Guardrails loaded)
```


