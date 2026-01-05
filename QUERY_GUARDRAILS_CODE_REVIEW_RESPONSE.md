# Query Guardrails - Code Review Response

## 1) PROOF - Konkrétní místa a tok dat

### A) footage_director.py - Integrace

**Soubor:** `backend/footage_director.py`

**Funkce:** `apply_deterministic_generators_v27()` (řádky 3443-3578)

**Přesný blok validace (řádky 3536-3572):**

```python
# 3. Generate search_queries (with templates + guardrails)
try:
    # First generate queries deterministically
    raw_queries = _generate_deterministic_queries_v27(
        narration_text, i, episode_anchor_hints=episode_anchor_hints
    )
    
    # Then apply guardrails for validation/refinement
    if not QUERY_GUARDRAILS_AVAILABLE:
        raise RuntimeError(
            "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded. "
            "Cannot proceed with query generation without validation. "
            "Check import errors at startup."
        )
    
    shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
    
    # Extract episode topic for fallback anchors
    episode_topic = None
    if episode_anchor_hints:
        episode_topic = ' '.join(episode_anchor_hints[:2])  # Use first 2 anchors as topic
    
    validated_queries, diagnostics = validate_and_fix_queries(
        raw_queries,
        narration_text,
        shot_types=shot_types,
        episode_topic=episode_topic,
        min_valid_queries=5,
        max_regen_attempts=2,
        verbose=False
    )
    
    scene["search_queries"] = validated_queries
    scene["_query_diagnostics"] = diagnostics
    
    if diagnostics.get('low_coverage'):
        print(f"⚠️  Scene {scene_id}: LOW COVERAGE - only {diagnostics['final_count']}/5 valid queries")
    else:
        print(f"✅ Scene {scene_id}: Generated {len(validated_queries)} queries (validated)")
        
except Exception as e:
    print(f"⚠️  Scene {scene_id}: Queries generation failed: {e}")
    raise  # Re-raise to fail loudly
```

**Tok dat:**
1. `narration_text` - z `block_dict` (řádky 3505-3514), obsahuje `text_tts` z narration blocků
2. `shot_types` - z `scene["shot_strategy"]["shot_types"]`, list shot typů jako `['maps_context', 'archival_documents']`
3. `episode_topic` - extrahovaný z `episode_anchor_hints` (řádky 3496), které pocházejí z `_extract_episode_anchor_terms_v27(tts_ready_package)`

---

### B) visual_planning_v3.py - Integrace

**Soubor:** `backend/visual_planning_v3.py`

**Funkce:** `_queries_for_scene()` (řádky 453-531)

**Přesný blok validace (řádky 518-531):**

```python
# Apply guardrails if available (REQUIRED - fail if not available)
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError(
        "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded in visual_planning_v3. "
        "Cannot proceed with query generation without validation."
    )

validated, diagnostics = validate_and_fix_queries(
    out,
    text,
    shot_types=shot_types,
    episode_topic=episode_topic or ent,
    min_valid_queries=5,
    max_regen_attempts=2,
    verbose=False
)
return validated[:5]
```

**Tok dat:**
1. `text` - `scene_text` z compile_shotplan_v3 (řádek 585), obsahuje narration text pro scénu
2. `shot_types` - z scene config (řádek 618), list jako `['maps_context']`
3. `episode_topic` - extrahován v `compile_shotplan_v3()` (řádky 542-560):
   ```python
   episode_topic = str(tts_ready_package.get("episode_metadata", {}).get("title", "")).strip()
   if not episode_topic:
       # Fallback: use first narration block
       segments = tts_ready_package.get("tts_segments", [])
       if segments:
           first_text = segments[0].get("tts_formatted_text", "")
           words = first_text.split()[:10]
           caps = [w for w in words if w and w[0].isupper()]
           if caps:
               episode_topic = ' '.join(caps[:3])
   ```

---

## 2) Zpřesněná pravidla (OPRAVENO)

### A) Anchor pravidlo (KRITICKÁ OPRAVA)

**PŮVODNÍ (ŠPATNĚ):**
```python
# Year alone was considered valid anchor ❌
if re.search(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', query):
    return True
```

**OPRAVENO (řádky 73-108 v query_guardrails.py):**
```python
def has_anchor(query: str) -> bool:
    """
    CRITICAL: Year alone is NOT sufficient anchor!
    
    Anchor = ONE of:
    1. Entity (proper noun): Person/Place/Event name (capitalized, 3+ chars)
    2. Multi-word capitalized phrase (2-4 words)
    3. Specific phrase from beat (quoted or compound)
    
    Year can SUPPLEMENT anchor but never BE the only anchor.
    """
    # Check for proper noun (entity: person/place/event, 3+ chars)
    if re.search(r'\b[A-Z][a-z]{2,}', query):
        return True
    
    # Check for multi-word capitalized phrase (2-4 words)
    if re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+', query):
        return True
    
    # Check for quoted phrase (specific reference)
    if re.search(r'"[^"]{3,}"', query):
        return True
    
    # Year ALONE is NOT valid anchor - if we only find year, reject
    has_year = bool(re.search(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', query))
    has_entity = bool(re.search(r'\b[A-Z][a-z]{2,}', query))
    
    # If query has year but no entity, it's NOT anchored
    if has_year and not has_entity:
        return False
    
    return False
```

**Unit test:**
```bash
cd backend && python3 test_query_guardrails_unit.py
```

**Výsledek:**
```
✅ PASS: '1812 retreat archival photograph' correctly rejected (year-only)
✅ PASS: 'Napoleon 1812 retreat archival photograph' correctly accepted (entity + year)
✅ PASS: '1812 winter conditions archival photograph' correctly rejected (year + generic)
```

---

### B) Media intent token

**Implementace:** Whitelist + mapování na shot_type (řádky 61-99)

```python
MEDIA_INTENT_TOKENS = {
    'photo', 'photograph', 'photography',
    'archival', 'archive', 'archived',
    'newspaper', 'newsreel',
    'map', 'maps', 'mapping',
    'document', 'documents', 'documentation',
    'report', 'reports', 'reporting',
    # ... (volitelné tokeny jako engraving, manuscript)
}

def add_media_intent_token(query: str, shot_type: Optional[str] = None) -> str:
    """
    Add appropriate media intent token based on shot type.
    
    Preference:
    - map shot → map
    - document shot → document/report
    - general → archival photo
    """
    if shot_type:
        shot_lower = shot_type.lower()
        if 'map' in shot_lower:
            return f"{query} map"
        elif 'document' in shot_lower:
            return f"{query} document"
        elif 'photo' in shot_lower or 'portrait' in shot_lower:
            return f"{query} photograph"
    
    # Default: archival photo
    return f"{query} archival photograph"
```

---

### C) Stoplist (KRITICKÁ OPRAVA)

**PŮVODNÍ (ŠPATNĚ):**
```python
# Simple check - blocked legitimate "Olympic Games" ❌
return any(noise in query_lower for noise in NOISE_STOPLIST)
```

**OPRAVENO (řádky 130-173):**
```python
# Legitimate historical contexts that override stoplist
LEGITIMATE_CONTEXTS = {
    'game': ['olympic', 'olympics', 'ancient', 'arena', 'gladiator', 'hunt', 'hunting'],
    'games': ['olympic', 'olympics', 'ancient', 'arena', 'gladiator'],
    'band': ['armband', 'headband', 'elastic', 'rubber'],
}

def has_noise_terms(query: str) -> bool:
    """
    Check context to avoid false positives!
    "Olympic Games" is legitimate, "games compilation" is noise.
    """
    query_lower = query.lower()
    
    for noise in NOISE_STOPLIST:
        if noise not in query_lower:
            continue
            
        # Found potential noise term - check if it's legitimate
        if noise in LEGITIMATE_CONTEXTS:
            # Check if ANY legitimate context word is present
            is_legitimate = False
            for context_word in LEGITIMATE_CONTEXTS[noise]:
                if context_word in query_lower:
                    is_legitimate = True
                    break
            
            if is_legitimate:
                # This is legitimate usage - skip this noise term
                continue
        
        # No legitimate context found - this IS noise
        return True
    
    return False
```

**Unit test:**
```
✅ PASS: 'Olympic Games Athens archival photograph' NOT blocked (legitimate context)
✅ PASS: 'Ancient Games Rome arena archival engraving' NOT blocked (ancient context)
✅ PASS: 'games compilation highlights' correctly blocked (noise)
✅ PASS: 'Napoleon video game footage' correctly blocked (video game)
```

**TODO:** Externalizovat do JSON config souboru (zatím hardcoded pro rychlý start).

---

## 3) Regeneration - Deterministická a omezená

### A) Max 2 pokusy - OVĚŘENO

**Implementace (řádky 553-582 v query_guardrails.py):**

```python
# Phase 3: Regenerate if needed (max attempts)
regen_attempt = 0
while len(valid_queries) < min_valid_queries and regen_attempt < max_regen_attempts:
    regen_attempt += 1
    needed = min_valid_queries - len(valid_queries)
    
    if verbose:
        print(f"   Regeneration attempt {regen_attempt}/{max_regen_attempts}: need {needed} more queries")
    
    for _ in range(needed):
        safe_query = generate_safe_query(beat_text, available_anchors, shot_type, episode_topic)
        
        # Avoid duplicates (case-insensitive)
        if safe_query.lower() not in [q.lower() for q in valid_queries]:
            valid_queries.append(safe_query)
            diagnostics['regenerated_count'] += 1
            if verbose:
                print(f"   + Generated: '{safe_query}'")

# Phase 4: Mark as low_coverage if still insufficient
if len(valid_queries) < min_valid_queries:
    diagnostics['low_coverage'] = True
    if verbose:
        print(f"   ⚠️  LOW COVERAGE: Only {len(valid_queries)}/{min_valid_queries} valid queries")
```

**Garance:**
1. ✅ Žádné vnořené retry (flat while loop)
2. ✅ `regen_attempt < max_regen_attempts` (strict bound)
3. ✅ Low_coverage flag je VIDITELNÝ (logged + stored in diagnostics)

**Unit test:**
```
✅ PASS: Marked as low_coverage (3/6)
Regenerated: 1 queries
✅ TEST PASSED: Regeneration limited to max attempts, low_coverage flag set

✅ TEST PASSED: No infinite loop detected (completed in 0.00s)
```

---

## 4) Testy - Napojení na CI

### A) Unit testy (nové)

**Soubor:** `backend/test_query_guardrails_unit.py`

**Spuštění:**
```bash
cd backend && python3 test_query_guardrails_unit.py
```

**Pokryté případy:**
1. ✅ Anchor-only-year fails
2. ✅ Stoplist "game" neblokuje "Olympic Games"
3. ✅ Map shot vždy obsahuje "map"
4. ✅ Max regen 2 pokusy, pak low_coverage flag
5. ✅ No infinite loops (stress test < 5s)

### B) Integration test fixture (TODO)

**Potřeba:**
- Fixture s reálným exportem (tts_ready_package)
- Spustit přes celý pipeline
- Ověřit že queries mají anchors

**Status:** Připraveno pro integraci do vašeho CI stylu.

---

## 5) Metriky (strukturované)

### A) Formát metrik

**Diagnostika per-scene (uloženo v `scene['_query_diagnostics']`):**

```python
{
    'original_count': 5,           # Queries generated
    'valid_count': 3,              # Immediately valid
    'invalid_count': 2,            # Failed validation
    'refined_count': 1,            # Fixed via refinement
    'regenerated_count': 1,        # Generated from template
    'final_count': 5,              # Total returned
    'low_coverage': False,         # True if < minimum
    'rejection_reasons': {         # Aggregated reasons
        'NO_ANCHOR': 1,
        'NO_MEDIA_INTENT': 1
    }
}
```

### B) Sběr metrik

**TODO:** Přidat strukturovaný event log:

```python
# Example event:
{
    "event": "QUERY_VALIDATION",
    "episode_id": "ep_123",
    "scene_id": "sc_0001",
    "timestamp": "2026-01-03T20:00:00Z",
    "metrics": {
        "valid_rate": 0.60,  # valid_count / original_count
        "low_coverage": False,
        "rejection_reasons": {"NO_ANCHOR": 2},
        "processing_time_ms": 5
    }
}
```

**Implementace:** Připraveno pro přidání do vašeho log aggregátoru.

---

## 6) Silent Fallback ODSTRANĚN

**PŮVODNÍ (NEBEZPEČNÉ):**
```python
if QUERY_GUARDRAILS_AVAILABLE:
    # Use guardrails
else:
    # Silent fallback to raw queries ❌
    scene["search_queries"] = raw_queries
```

**OPRAVENO (HARD FAIL):**

```python
# footage_director.py (řádky 3541-3547)
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError(
        "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded. "
        "Cannot proceed with query generation without validation. "
        "Check import errors at startup."
    )

# visual_planning_v3.py (řádky 520-525)
if not QUERY_GUARDRAILS_AVAILABLE:
    raise RuntimeError(
        "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded in visual_planning_v3. "
        "Cannot proceed with query generation without validation."
    )
```

**Startup log:**
```python
try:
    from query_guardrails import validate_and_fix_queries
    QUERY_GUARDRAILS_AVAILABLE = True
    print("✅ Query Guardrails úspěšně načteny")
except ImportError as e:
    print(f"❌ CRITICAL: Query Guardrails import failed: {e}")
    print("❌ Pipeline will FAIL on query generation without guardrails!")
    QUERY_GUARDRAILS_AVAILABLE = False
```

---

## Summary - Code Review Odpovědi

| Bod | Status | Poznámka |
|-----|--------|----------|
| 1A) footage_director místo | ✅ DONE | Řádky 3536-3572 |
| 1B) visual_planning_v3 místo | ✅ DONE | Řádky 518-531 |
| 1C) Tok dat dokumentován | ✅ DONE | Episode topic z tts_ready_package |
| 2A) Anchor pravidlo (year alone fails) | ✅ FIXED | Unit test passing |
| 2B) Media intent whitelist + mapping | ✅ DONE | Shot type → token |
| 2C) Stoplist s legitimate context | ✅ FIXED | Olympic Games passes |
| 3) Max 2 regen, deterministický | ✅ VERIFIED | Unit test passing |
| 4) Unit testy | ✅ DONE | 5 critical cases |
| 5) Metriky strukturované | 🟡 PREPARED | Schema ready, needs log aggregator |
| 6) Silent fallback removed | ✅ FIXED | Hard fail on missing import |

**Zbývá:**
- [ ] Externalize stoplist to JSON config
- [ ] Integration test fixture
- [ ] Metrics aggregation setup
- [ ] Reálný run na 10 epizodách

**Připraveno k review:** Všechny kritické body adresovány, unit testy passing.


