# Pre-FDA Sanitizer - Průvodce implementací

## 🎯 Účel

Pre-FDA Sanitizer je **deterministický (100% non-LLM)** krok, který odstraňuje abstraktní a generické výrazy z `keywords[]` a `search_queries[]` **PŘED** tím, než FDA (Footage Director Assistant) vyhodnotí shot_plan.

### Proč existuje?

FDA má hard-gate validaci, která kontroluje, zda:
- `keywords[]` neobsahují generické fillery (např. "strategic", "goal", "territory")
- `search_queries[]` jsou konkrétní a vizuálně ukotvené

**Problém:** LLM (i s dobrým promptem) občas používá abstraktní termíny, což vede k `FDA_GENERIC_FILLER_DETECTED` chybám.

**Řešení:** Pre-FDA Sanitizer **deterministicky** nahrazuje abstraktní termy jejich konkrétními vizuálními proxy **PŘED** FDA validací.

---

## 📊 Pipeline flow

```
TTS Formatting
    ↓
[LLM generuje shot_plan]
    ↓
Pre-FDA Sanitizer ← NOVÉ (deterministický, 100% non-LLM)
    ↓
validate_and_fix_shot_plan (soft checks)
    ↓
validate_shot_plan_hard_gate (HARD GATE)
    ↓
Uložení do project metadata
```

---

## 🔧 Implementace

### 1. Blacklist (single source of truth)

Pre-FDA Sanitizer má globální blacklist zakázaných výrazů:

```python
BLACKLISTED_ABSTRACT_TERMS = [
    # Abstraktní strategické/analytické
    "strategic", "strategy", "goal", "intention", "policy", 
    "ambition", "dominance", "control", "territory", "peace",
    "influence", "power", "importance", "significance",
    
    # Generické fillery
    "history", "events", "situation", "conflict", "background",
    "context", "footage", "montage",
    
    # Další abstraktní
    "impact", "support", "pressure", "consequence", "outcome",
    "turning point", "tide", "war effort", "production", "industry",
]
```

### 2. Visual Proxy Mapping

Každý blacklisted term má **povinnou** náhradu:

```python
VISUAL_PROXY_MAP = {
    # Abstraktní → konkrétní vizuální objekt
    "strategic": "archival_documents",
    "goal": "official_correspondence",
    "territory": "marked_maps",
    "peace": "treaty_documents",
    "influence": "diplomatic_correspondence",
    # ... atd.
}
```

**Pravidla pro náhrady:**
- ✅ MUSÍ být konkrétní vizuální objekt
- ✅ MUSÍ být kompatibilní s archive.org
- ✅ NESMÍ zavádět nové fakty
- ❌ NESMÍ být další abstraktní termín

### 3. Sanitizační algoritmus

```python
def sanitize_shot_plan(shot_plan):
    """
    1. Projde každou scénu v shot_plan.scenes[]
    2. Pro každý keyword v keywords[]:
       - Normalizuj (lowercase, trim)
       - Pokud odpovídá blacklistu → nahraď podle VISUAL_PROXY_MAP
       - Zachovej pozici v seznamu
    3. Pro každou query v search_queries[]:
       - Stejný proces jako keywords
    4. (Volitelně) Pro narration_summary:
       - Stejný proces
    5. HARD CHECK: znovu zkontroluj, zda nezůstaly blacklisted termy
       - Pokud ano → raise RuntimeError("FDA_SANITIZER_FAILED")
    """
```

**ŽÁDNÉ:**
- ❌ Fallbacky
- ❌ Silent opravy
- ❌ Heuristiky
- ❌ LLM calls

**POUZE:**
- ✅ Deterministické string matching
- ✅ Pevné mapování (VISUAL_PROXY_MAP)
- ✅ FATAL errors při jakékoli anomálii

---

## 🚨 Error handling (vždy FATAL)

Každá z těchto chyb **MUSÍ** zastavit pipeline:

### `FDA_SANITIZER_UNMAPPED`
```json
{
  "error": "FDA_SANITIZER_UNMAPPED",
  "token": "strategic",
  "reason": "blacklisted term nemá mapování v VISUAL_PROXY_MAP"
}
```

### `FDA_SANITIZER_EMPTY`
```json
{
  "error": "FDA_SANITIZER_EMPTY",
  "scene_id": "sc_0001",
  "reason": "Po sanitizaci zůstal prázdný seznam keywords"
}
```

### `FDA_SANITIZER_FAILED`
```json
{
  "error": "FDA_SANITIZER_FAILED",
  "scene_id": "sc_0001",
  "token": "strategic",
  "reason": "Po sanitizaci zůstal blacklisted term v keywords"
}
```

### `FDA_SANITIZER_UNAVAILABLE`
```json
{
  "error": "FDA_SANITIZER_UNAVAILABLE",
  "reason": "pre_fda_sanitizer.py není dostupný (import failed)"
}
```

**Pipeline se MUSÍ zastavit:**
- `footage_director` = ERROR
- `asset_resolver` = IDLE
- `metadata.shot_plan` se NESMÍ uložit

---

## 📝 Logging (grep-friendly)

### PASS
```json
{"timestamp":"2025-12-28T12:34:56Z","status":"FDA_SANITIZER_PASS","scenes_processed":8,"total_replacements":3,"scene_details":[{"scene_id":"sc_0001","replacements":["strategic→archival_documents","peace→treaty_documents"]}]}
```

### FAIL
```json
{"timestamp":"2025-12-28T12:34:56Z","status":"FDA_SANITIZER_FAIL","error":"FDA_SANITIZER_UNMAPPED: Token 'strategic' obsahuje blacklisted term 'strategic', ale nemá definovanou náhradu v VISUAL_PROXY_MAP."}
```

**Pravidla:**
- ✅ Jeden řádek JSON (grep-friendly)
- ✅ Compact format (bez whitespace)
- ✅ Obsahuje timestamp, status, diagnostic data
- ✅ Použitelné v `grep "FDA_SANITIZER_"` nebo `jq`

---

## 🔍 Rozsah působnosti (EXAKTNÍ)

### MUSÍ projít sanitizací:
- ✅ `keywords[]` (každá scéna)
- ✅ `search_queries[]` (každá scéna)
- ✅ `narration_summary` (pokud existuje)

### NESMÍ se dotýkat:
- ❌ `text_tts` (narační text - NIKDY neměníme)
- ❌ `narration_blocks` (struktura bloků)
- ❌ `claim_ids` (odkazy na claims)
- ❌ Časování (`start_sec`, `end_sec`, `duration`)
- ❌ Struktury scén (`scene_id`, `narration_block_ids`)

---

## ✅ Definition of Done

### Před merge do main:

1. **FDA už NIKDY nepadne na zakázané termy**
   ```bash
   # Test: žádná z těchto chyb by neměla existovat po sanitizeru
   grep "FDA_GENERIC_FILLER_DETECTED.*strategic" backend_server.log
   grep "FDA_GENERIC_FILLER_DETECTED.*goal" backend_server.log
   grep "FDA_GENERIC_FILLER_DETECTED.*territory" backend_server.log
   grep "FDA_GENERIC_FILLER_DETECTED.*peace" backend_server.log
   ```

2. **FDA hard-gate zůstává beze změny**
   - Hard-gate kontroly jsou stále aktivní (poslední obrana)
   - Ale díky sanitizeru by neměly nikdy selhat

3. **Význam narace zůstává zachován**
   - "strategic goal" → "official_correspondence" (význam: dokumentované cíle)
   - "territory control" → "marked_maps border_maps" (význam: vizuální reprezentace území)

4. **Žádné fallbacky**
   - Každá chyba je FATAL
   - Pipeline se zastaví s jasným error kódem

5. **Jeden canonical flow**
   - TTS → Sanitizer → FDA → Validation → Save
   - Žádné alternativní cesty
   - Žádné "pokud selže A, zkus B"

---

## 🧪 Testing

### Unit test

```python
# backend/test_pre_fda_sanitizer.py

def test_sanitize_keywords():
    keywords = ["strategic", "Napoleon", "Moscow", "goal"]
    sanitized, replacements = sanitize_keywords(keywords, "sc_0001")
    
    assert "strategic" not in sanitized
    assert "goal" not in sanitized
    assert "Napoleon" in sanitized  # Konkrétní termíny zůstávají
    assert "Moscow" in sanitized
    assert "archival_documents" in sanitized
    assert "official_correspondence" in sanitized
    assert len(replacements) == 2  # strategic, goal


def test_sanitize_blacklisted_term_without_mapping():
    # Pokud přidáme nový blacklisted term bez mapování → FATAL
    keywords = ["unknown_blacklisted_term"]
    
    with pytest.raises(RuntimeError, match="FDA_SANITIZER_UNMAPPED"):
        sanitize_keywords(keywords, "sc_0001")
```

### Integration test

```bash
# Spusť FDA na reálném projektu, který dříve padal na "strategic"
cd backend
python3 test_fda_with_sanitizer.py

# Očekávaný výsledek:
# ✅ FDA_SANITIZER_PASS
# ✅ FDA_GENERIC_FILLER_DETECTED: 0 errors
# ✅ Shot plan uložen
```

---

## 📚 Další dokumentace

- **FDA hlavní dokumentace:** `FDA_README.md`
- **FDA Troubleshooting:** `FDA_TROUBLESHOOTING.md`
- **FDA LLM Migration:** `FDA_LLM_MIGRATION.md`

---

## 🔧 Maintenance

### Přidání nového blacklisted term:

1. Přidej do `BLACKLISTED_ABSTRACT_TERMS` v `pre_fda_sanitizer.py`
2. Přidej mapování do `VISUAL_PROXY_MAP`
3. Spusť testy: `pytest backend/test_pre_fda_sanitizer.py`
4. Aktualizuj tuto dokumentaci

### Odstranění blacklisted term:

1. Odstraň z `BLACKLISTED_ABSTRACT_TERMS`
2. Odstraň z `VISUAL_PROXY_MAP`
3. Spusť testy
4. Aktualizuj dokumentaci

### Změna náhrady:

1. Uprav `VISUAL_PROXY_MAP`
2. Spusť testy (ověř, že FDA nepadá)
3. Ověř, že význam narace zůstává zachován

---

**Poslední aktualizace:** 2025-12-28  
**Verze:** 1.0  
**Autor:** FDA Pipeline Team



