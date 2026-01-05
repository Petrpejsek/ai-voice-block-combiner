# FDA Sanitizer Soft Fix - Dokumentace

## 🎯 Problém

**Původní chování:**
- Když FDA vygeneroval zakázané slovo (např. "troop movement") v `keywords` nebo `search_queries`, sanitizer spadl s `FDA_SANITIZER_FAILED`
- Uživatel musel episode točit dokola, protože každé spuštění mohlo vygenerovat jiné zakázané termy
- Logický rozpor: `shot_type: troop_movement` (enum) je validní, ale "troop movement" v keywords způsobilo fail

**Důsledek:**
- Nekonečný loop chyb při generování "Napoleon in Moscow" a podobných vojenských témat
- Frustrace uživatele - nemožnost dokončit episode

---

## ✅ Řešení

### A) Hard Fail → Soft Sanitize (KRITICKÁ ZMĚNA)

**Soubor:** `backend/pre_fda_sanitizer.py`

**Změna chování:**
```python
# PŘED (hard fail):
if _is_blacklisted(keyword):
    raise RuntimeError(f"FDA_SANITIZER_FAILED: ...")

# PO (soft sanitize):
if _is_blacklisted(keyword):
    removed_terms.append(keyword)
    cleaned = _remove_blacklisted_words(keyword)
    if cleaned and not _is_blacklisted(cleaned):
        final_sanitized.append(cleaned)
    else:
        # DELETE, bude nahrazeno fallbackem
        pass
```

**Výsledek:**
- Sanitizer **NIKDY** nespadne kvůli blacklisted termům
- Místo error → **WARNING log** s detaily
- Zakázané termy jsou odstraněny/nahrazeny automaticky

---

### B) Logický rozpor: "troop movement" vyřešen

**Problém:**
- `shot_types: ["troop_movement"]` (enum) je validní
- Ale "troop movement" v keywords způsobovalo fail

**Řešení:**
1. **"troop movement" ZŮSTÁVÁ v blacklistu** (pro keywords/queries)
2. **Sanitizer kontroluje POUZE keywords/queries**, NIKDY shot_types
3. **Visual proxy:** "troop movement" → "soldiers marching" (konkrétní vizuální objekt)

**Výsledek:**
```json
{
  "keywords": ["soldiers marching"],  // ✅ Nahrazeno visual proxy
  "shot_types": ["troop_movement"]    // ✅ Enum zůstal beze změny
}
```

---

### C) FDA Prompt - Explicitní zákaz shot type names

**Soubor:** `backend/footage_director.py`

**Přidáno do promptu:**
```
- **CRITICAL: NEVER include shot type names in keywords/search_queries 
  (e.g., "troop movement", "battle footage", "archival documents")**
- **Keywords are OBJECTS ONLY: map, letter, manuscript, palace, 
  city street, engraving, soldiers, wagons, roads**
```

**Výsledek:**
- FDA dostává jasnou instrukci: shot type names ≠ keywords
- Prevence problému u zdroje (LLM generování)

---

### D) Fallback Queries - Zajištění min 3-6 queries

**Funkce:** `_enforce_query_mix()` v `pre_fda_sanitizer.py`

**Chování:**
- Pokud jsou všechny queries smazány → automaticky doplní fallback queries
- **Garantuje:** min 1 broad + 2 object/action queries (celkem 3-6)
- Fallbacky jsou deterministické podle `shot_types`

**Příklad:**
```python
# Input: všechny queries blacklisted
search_queries: ["strategic importance", "military campaign"]

# Output: fallbacky podle shot_types
search_queries: [
  "archival military map",      # broad query
  "border map marked",           # object query 1
  "front lines map"              # object query 2
]
```

---

## 📊 Testování

### Unit testy (prošly ✅)

**Test 1:** Keywords s "troop movement"
- Input: `["Napoleon", "Moscow", "troop movement"]`
- Output: `["Napoleon", "Moscow", "soldiers marching"]`
- ✅ PASS: "troop movement" nahrazeno visual proxy

**Test 2:** Všechny queries blacklisted
- Input: `["strategic importance", "military campaign", "battle tactics"]`
- Output: 4 fallback queries (min 3 splněno)
- ✅ PASS: Fallbacky doplněny, žádné blacklisted termy

**Test 3:** shot_type troop_movement
- Input: `shot_types: ["troop_movement"]`
- Output: `shot_types: ["troop_movement"]` (beze změny)
- ✅ PASS: Enum zachován

---

### E2E test - Napoleon in Moscow (prošel ✅)

**Scénář:** 4 scény s 12+ blacklisted termy v inputu

**Výsledek:**
- ✅ Sanitizace proběhla BEZ chyby
- ✅ 25 replacements (všechny blacklisted termy odstraněny/nahrazeny)
- ✅ Všechny scény mají 3-6 queries
- ✅ shot_type `troop_movement` zachován
- ✅ **NIKDY nespadl s FDA_SANITIZER_FAILED**

---

## 🔍 Změněné soubory

### 1. `backend/pre_fda_sanitizer.py`

**Změny:**
- ✅ SOFT CHECK místo HARD CHECK v `sanitize_keywords()`
- ✅ SOFT CHECK místo HARD CHECK v `sanitize_search_queries()`
- ✅ WARNING log místo RuntimeError
- ✅ Přidány "tactics", "tactical" do blacklistu
- ✅ Visual proxy: "troop movement" → "soldiers marching"
- ✅ Fix: return `final_sanitized` místo `sanitized` (kritický bug!)

**Nové logy:**
```json
FDA_SANITIZE_WARNING: {
  "scene_id": "sc_0001",
  "removed_terms": ["troop movement", "strategic importance"],
  "removed_from": "keywords",
  "before_count": 6,
  "after_count": 5
}
```

---

### 2. `backend/footage_director.py`

**Změny:**
- ✅ Přidán explicitní zákaz shot type names v keywords (FDA prompt)
- ✅ Příklad: "retreat" → infer "soldiers / wagons / roads" (NOT "troop movement")
- ✅ Poznámka u `EXPLICIT_FORBIDDEN_KEYWORDS`: "troop movement" není v listu (je to validní shot_type)

---

## 🚀 Výsledek

### Před fixem:
```
❌ FDA_SANITIZER_FAILED: Po sanitizaci zůstal blacklisted term 'troop movement' v keywords
→ Episode FAIL → Uživatel točí dokola
```

### Po fixu:
```
⚠️  FDA_SANITIZE_WARNING: {"removed_terms": ["troop movement"], "removed_from": "keywords"}
✅ FDA_SANITIZER_PASS
→ Episode pokračuje → Žádný loop
```

---

## 📝 Pravidla pro budoucnost

### ✅ DO:
- Blacklisted termy v keywords/queries → **soft sanitize** (WARNING)
- shot_types enum → **vždy validní**, nikdy nekontrolovat
- Fallback queries → **vždy zajistit min 3-6 queries**
- Visual proxy → **konkrétní objekty** (soldiers, wagons, map)

### ❌ DON'T:
- NIKDY neházet RuntimeError kvůli blacklisted termům v keywords/queries
- NIKDY nekontrolovat shot_types proti blacklistu
- NIKDY nechat prázdný seznam queries (min 3 required)
- NIKDY používat shot type names jako keywords ("troop movement" → "soldiers")

---

## 🔧 Jak testovat

### Quick test:
```bash
cd backend
python3 -c "
from pre_fda_sanitizer import sanitize_shot_plan
plan = {
  'scenes': [{
    'scene_id': 'test',
    'keywords': ['troop movement', 'strategic importance'],
    'search_queries': ['military campaign'],
    'shot_strategy': {'shot_types': ['troop_movement']}
  }]
}
result, log = sanitize_shot_plan(plan)
print('✅ PASS' if log['status'] == 'FDA_SANITIZER_PASS' else '❌ FAIL')
"
```

### Očekávaný výstup:
```
FDA_SANITIZE_WARNING: {...}
✅ PASS
```

---

## 📚 Související dokumenty

- `PRE_FDA_SANITIZER_ARCHITECTURE.md` - Architektura sanitizéru
- `FDA_README.md` - Celková FDA dokumentace
- `FDA_TROUBLESHOOTING.md` - Troubleshooting guide

---

**Datum:** 2025-12-29  
**Status:** ✅ COMPLETE  
**Testováno:** Unit tests + E2E test (Napoleon in Moscow)  
**Kompatibilita:** Zpětně kompatibilní, žádné breaking changes



