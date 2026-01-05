# Query Guardrails - FINAL PROOF AUDIT

## G) PROOF VÝSTUP - Kompletní dokumentace s důkazy

### 1) Soubor + řádky: kde se bere episode_metadata.topic a jak se předává

#### visual_planning_v3.py (řádky 548-563)

**Kde vzniká episode_topic:**
```python
# Řádky 548-563
episode_topic = None
episode_metadata = tts_ready_package.get("episode_metadata", {})

# Try title first, then topic field
episode_topic = str(episode_metadata.get("title", "")).strip()
if not episode_topic:
    episode_topic = str(episode_metadata.get("topic", "")).strip()

# NO FALLBACK from narration - if no metadata, fail clearly
if not episode_topic:
    raise ValueError(
        "EPISODE_TOPIC_MISSING: episode_metadata must contain 'title' or 'topic' field. "
        "Cannot generate anchored queries without episode context. "
        "Refusing to extract from narration (hacky fallback forbidden)."
    )
```

**Status:** ✅ Canonical source, hard fail pokud chybí

**Jak se předává:**
```python
# Řádek 635
queries = _queries_for_scene(scene_text, focus, shot_types, episode_topic=episode_topic)

# Řádek 675 (fallback scene)
"search_queries": _queries_for_scene(txt, _extract_focus_entities(txt), ["archival_documents"], episode_topic=episode_topic)
```

---

#### footage_director.py (řádky 3555-3570)

**Kde vzniká episode_topic:**
```python
# Řádky 3555-3570
episode_topic = None
if episode_anchor_hints:
    episode_topic = ' '.join(episode_anchor_hints[:2])  # Use first 2 anchors as topic

# CRITICAL: If no episode_anchor_hints, MUST hard fail
if not episode_topic:
    raise ValueError(
        f"EPISODE_TOPIC_MISSING (scene {scene_id}): No episode_anchor_hints available. "
        "episode_metadata must contain identifiable anchors (names/events). "
        "Cannot generate queries without episode context. "
        "Check _extract_episode_anchor_terms_v27() output."
    )
```

**Status:** ✅ Uses `episode_anchor_hints` from `_extract_episode_anchor_terms_v27()` (která čte z metadata), hard fail pokud chybí

**Jak se předává:**
```python
# Řádek 3571
episode_topic=episode_topic,
```

---

### 2) Soubor + řádky: kde se dělá hard fail při missing topic / missing guardrails

#### A) Missing topic

**visual_planning_v3.py řádky 558-563:**
```python
if not episode_topic:
    raise ValueError(
        "EPISODE_TOPIC_MISSING: episode_metadata must contain 'title' or 'topic' field. "
        "Cannot generate anchored queries without episode context. "
        "Refusing to extract from narration (hacky fallback forbidden)."
    )
```

**footage_director.py řádky 3562-3570:**
```python
if not episode_topic:
    raise ValueError(
        f"EPISODE_TOPIC_MISSING (scene {scene_id}): No episode_anchor_hints available. "
        "episode_metadata must contain identifiable anchors (names/events). "
        "Cannot generate queries without episode context. "
        "Check _extract_episode_anchor_terms_v27() output."
    )
```

**query_guardrails.py řádky 544-551:**
```python
# CRITICAL: episode_topic is REQUIRED for valid anchoring
if not episode_topic or not episode_topic.strip():
    raise ValueError(
        "EPISODE_TOPIC_REQUIRED: episode_topic parameter is required for query validation. "
        "Cannot generate anchored queries without episode context. "
        "Provide episode_metadata['title'] or ['topic']."
    )
```

#### B) Missing guardrails

**footage_director.py řádky 3545-3550:**
```python
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError(
        "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded. "
        "Cannot proceed with query generation without validation. "
        "Check import errors at startup."
    )
```

**visual_planning_v3.py řádky 520-525:**
```python
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError(
        "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded in visual_planning_v3. "
        "Cannot proceed with query generation without validation."
    )
```

---

### 3) Soubor + řádky: kde je BROAD_TERMS a kde se používá v anchor validaci

#### Definice BROAD_TERMS

**query_guardrails.py řádky 69-84:**
```python
# Broad epoch/era terms that are NOT valid anchors (even if capitalized)
BROAD_EPOCH_TERMS = {
    'world war one', 'world war two', 'world war i', 'world war ii', 'wwi', 'wwii',
    'cold war', 'vietnam war', 'korean war', 'civil war', 'revolutionary war',
    'great war', 'great depression', 'industrial revolution',
    'middle ages', 'renaissance', 'dark ages', 'iron age', 'bronze age',
    'ancient rome', 'ancient greece', 'ancient egypt',
}

# Broad organizational names that are NOT valid anchors
BROAD_ORGANIZATIONS = {
    'united states navy', 'us navy', 'royal navy', 'british army',
    'united states air force', 'us air force', 'royal air force',
    'united states army', 'us army',
    'marines', 'marine corps',
    'nato', 'united nations', 'un',
}
```

#### Použití v anchor validaci

**query_guardrails.py řádky 87-132:**
```python
def has_anchor(query: str) -> bool:
    """
    CRITICAL: Year alone is NOT sufficient anchor!
    CRITICAL: Broad epoch/org names are NOT sufficient anchors!
    
    Anchor = ONE of:
    1. Specific entity: Person/Ship/Battle/Location name (not broad org)
    2. Multi-word phrase that is NOT in broad_epoch_terms
    3. Specific quoted phrase
    """
    query_lower = query.lower()
    
    # Check if query contains broad epoch/org terms - these are NOT valid anchors
    for broad_term in BROAD_EPOCH_TERMS | BROAD_ORGANIZATIONS:
        if broad_term in query_lower:
            # This is a broad term - check if there's ALSO a specific entity
            # Extract all capitalized words that are NOT part of the broad term
            words_in_broad = set(broad_term.split())
            all_caps_words = re.findall(r'\b([A-Z][a-z]{2,})\b', query)
            specific_caps = [w for w in all_caps_words if w.lower() not in words_in_broad]
            
            if specific_caps:
                # Has specific entity beyond the broad term - OK
                return True
            else:
                # Only has broad term - NOT valid anchor
                return False
    
    # ... rest of validation
```

**Status:** ✅ BROAD_TERMS blokují "World War One", "United States Navy" pokud nejsou doplněny specifickou entitou

---

### 4) Výpis testů: příkaz + PASS

#### Všechny testy PASSED

```bash
cd /Users/petrliesner/podcasts/backend
python3 test_query_guardrails_unit.py && \
python3 test_query_guardrails_specific.py && \
python3 test_missing_topic.py
```

**Output:**
```
======================================================================
QUERY GUARDRAILS UNIT TESTS - CRITICAL CASES
======================================================================

✅ TEST PASSED: Year-only anchor correctly rejected
✅ TEST PASSED: Legitimate 'games' context preserved  
✅ TEST PASSED: 3/3 queries contain 'map'
✅ TEST PASSED: Regeneration limited to max attempts, low_coverage flag set
✅ TEST PASSED: No infinite loop detected

🎉 ALL UNIT TESTS PASSED!

======================================================================
SPECIFIC EDGE CASE TESTS - REAL PRODUCTION ISSUES
======================================================================

✅ PASS: 'World War One' rejected (too broad)
✅ PASS: 'United States Navy' rejected (too broad)
✅ TEST PASSED: Broad epoch detection complete
✅ TEST PASSED: Repairs added specific battle name

🎉 ALL SPECIFIC TESTS PASSED!

======================================================================
TEST: Missing episode_topic must cause hard fail
======================================================================

✅ PASS: Correctly raised exception with episode_topic=None
```

---

## AUDIT SUMMARY - Všechna místa ověřena

### A) Episode topic sources (canonical)

| Místo | Soubor | Řádky | Source | Fallback? |
|-------|--------|-------|--------|-----------|
| Visual planning | visual_planning_v3.py | 548-563 | `episode_metadata['title']` or `['topic']` | ❌ Hard fail |
| Footage director | footage_director.py | 3555-3570 | `episode_anchor_hints` (from metadata) | ❌ Hard fail |
| Guardrails | query_guardrails.py | 544-551 | Parameter (required) | ❌ Hard fail |

**Ověřeno:** ✅ Žádný fallback z narration, všude hard fail pokud chybí

### B) Broad terms blocking

| Term | Status | Source |
|------|--------|--------|
| World War One | ❌ REJECTED | BROAD_EPOCH_TERMS řádek 70 |
| United States Navy | ❌ REJECTED | BROAD_ORGANIZATIONS řádek 79 |
| USS Enterprise United States Navy | ✅ ACCEPTED | Has specific entity (USS Enterprise) |

**Ověřeno:** ✅ Broad terms samy o sobě neprojdou jako anchory

### C) Noise guard (word-boundary)

| Query | Status | Reason |
|-------|--------|--------|
| Olympic Games Athens | ✅ PASS | Legitimate context (olympic) |
| video game footage | ❌ REJECT | Noise (video game) |
| US Navy Band | ❌ REJECT | Noise (band) |

**Ověřeno:** ✅ Legitimate contexts preserved, noise blocked

### D) Hard fail na missing guardrails

| Místo | Soubor | Řádky | Exception Type |
|-------|--------|-------|----------------|
| Footage director | footage_director.py | 3545-3550 | RuntimeError |
| Visual planning | visual_planning_v3.py | 520-525 | RuntimeError |

**Ověřeno:** ✅ Žádný silent fallback, vždy hard fail

### E) Místa kde se queries posílají do vyhledávání

**Soubor:** `archive_asset_resolver.py`
**Funkce:** `search_multi_source()` řádek 1442, `search_images_multi_source()` řádek 1858

**Voláno z:**
- `aar_step_by_step.py` řádky 158, 168
- `archive_asset_resolver.py` řádky 3363, 4437, 4448

**Status:** ✅ Tyto funkce dostanou už validované queries z guardrails

---

## FINAL CHECKLIST

| Požadavek | Status | Evidence |
|-----------|--------|----------|
| A) PROOF audit | ✅ DONE | Tento dokument |
| B) Episode topic = povinný | ✅ DONE | 3 hard fail points |
| C) Broad terms blocking | ✅ DONE | BROAD_TERMS lists |
| D) Noise guard | ✅ DONE | Word-boundary + legitimate contexts |
| E) No silent fallback | ✅ DONE | Hard fail everywhere |
| F) Unit tests | ✅ PASS | test_query_guardrails_unit.py |
| F) Specific tests | ✅ PASS | test_query_guardrails_specific.py |
| F) Missing topic test | ✅ PASS | test_missing_topic.py |

---

## Proof Commands

```bash
# 1. Run all tests
cd /Users/petrliesner/podcasts/backend
python3 test_query_guardrails_unit.py
python3 test_query_guardrails_specific.py
python3 test_missing_topic.py

# 2. Verify BROAD_TERMS definition
grep -A 15 "^BROAD_EPOCH_TERMS" backend/query_guardrails.py
grep -A 10 "^BROAD_ORGANIZATIONS" backend/query_guardrails.py

# 3. Verify episode_topic sources
grep -n "episode_metadata" backend/visual_planning_v3.py | head -n 5
grep -n "episode_anchor_hints" backend/footage_director.py | head -n 5

# 4. Verify hard fails
grep -n "raise ValueError" backend/query_guardrails.py
grep -n "raise RuntimeError" backend/footage_director.py
grep -n "raise RuntimeError" backend/visual_planning_v3.py
```

---

## Status: ✅ PRODUCTION READY

**Žádné skuliny:**
- ❌ No fallback z narration
- ❌ No heuristics topicu
- ❌ No broad terms jako valid anchors
- ❌ No silent fallbacks

**Všechny testy passing:**
- ✅ Unit tests (5 cases)
- ✅ Specific tests (4 production issues)
- ✅ Missing topic test (hard fail verified)

**Hard fail points:**
- visual_planning_v3.py:558
- footage_director.py:3562
- query_guardrails.py:545
- footage_director.py:3546
- visual_planning_v3.py:521

**Date:** January 3, 2026
**Final verification:** ALL TESTS PASSED


