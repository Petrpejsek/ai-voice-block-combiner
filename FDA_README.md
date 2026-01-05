# Footage Director Assistant (FDA) - Dokumentace

## 🎯 Přehled

**Footage Director Assistant (FDA)** je 6. krok v script pipeline, který generuje `shot_plan` JSON ze `tts_ready_package` bez externích API volání.

### Klíčové vlastnosti

✅ **Čistě deterministický** - žádné LLM, žádné externí API  
✅ **Žádné stahování** - nepoužívá Archive.org, Pexels, YouTube  
✅ **Žádné renderování** - negeneruje video, pouze plánuje  
✅ **Stabilní schema** - pevná struktura s allowlisty  
✅ **Integrace do pipeline** - automaticky běží po TTS Formatting  

---

## 📂 Umístění v projektu

```
backend/
├── footage_director.py       # FDA core funkce
├── script_pipeline.py         # Integrace jako 6. krok
├── app.py                     # API endpoint /api/fda/generate
└── test_fda.py               # Test suite
```

---

## 🔄 Pipeline Flow

```
1. Research          (LLM)
2. Narrative         (LLM)
3. Validation        (LLM)
4. Composer          (deterministický)
5. TTS Formatting    (LLM)
6. 🆕 Footage Director (deterministický) ← NOVÝ KROK
```

### Vstup → Výstup

```
tts_ready_package.narration_blocks[] 
    → shot_plan (uložen do script_state.json)
```

---

## 📋 Výstupní formát: `shot_plan`

### Top-level struktura

```json
{
  "version": "fda_v1",
  "source": "tts_ready_package",
  "generated_at": "2025-12-27T...",
  "assumptions": {
    "words_per_minute": 150,
    "target_scene_duration_sec": 27,
    "max_blocks_per_scene": 6
  },
  "scenes": [...],
  "total_scenes": 3,
  "total_duration_sec": 69
}
```

### Struktura scény

Každá scéna má **vždy všechny tyto klíče** (žádné vynechávání):

```json
{
  "scene_id": "sc_0001",
  "start_sec": 0,
  "end_sec": 26,
  "narration_block_ids": ["b_0001", "b_0002", "b_0003", "b_0004"],
  "narration_summary": "Caligula began his reign with high popularity...",
  "emotion": "hope",
  "keywords": ["caligula", "reign", "popularity", "memory", "father", ...],
  "shot_strategy": {
    "shot_types": ["archival_documents", "maps_context"],
    "clip_length_sec_range": [4, 7],
    "cut_rhythm": "medium",
    "source_preference": ["archive_org"]
  },
  "search_queries": ["caligula", "began", "reign", "caligula began", ...]
}
```

---

## 🔒 Allowlists (MVP pevné hodnoty)

### `shot_types` (pouze tyto)

```python
"historical_battle_footage"
"troop_movement"
"leaders_speeches"
"civilian_life"
"destruction_aftermath"
"industry_war_effort"
"maps_context"
"archival_documents"
"atmosphere_transition"
```

### `emotion` (pouze enum)

```python
"neutral"
"tension"
"tragedy"
"hope"
"victory"
"mystery"
```

### `cut_rhythm` (pouze enum)

```python
"slow"    # 5-8s per clip
"medium"  # 4-7s per clip
"fast"    # 3-5s per clip
```

---

## 🎲 Jak FDA vytváří scény (MVP pravidla)

### Deterministický algoritmus

1. **Vezmi narration_blocks[] v pořadí**
2. **Sestav scény** tak, aby jedna scéna odpovídala:
   - **20-35 sekundám** odhadované řeči, NEBO
   - **3-8 blokům** (podle toho, co nastane dřív)
3. **Odhad času:**
   - Spočti slova v `text_tts`
   - Použij `words_per_minute` (default 150 WPM)
   - Přepočet na sekundy
4. **start_sec/end_sec musí navazovat** (žádné díry, žádné překryvy)

### Příklad

```
10 bloků → 3 scény:
- Scéna 1: bloky 1-4 (26s)
- Scéna 2: bloky 5-7 (23s)
- Scéna 3: bloky 8-10 (20s)
Celkem: 69s
```

---

## 🔌 API Endpoint

### `POST /api/fda/generate`

**Standalone endpoint** pro testování FDA mimo hlavní pipeline.

#### Request

```bash
curl -X POST http://localhost:50000/api/fda/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tts_ready_package": {
      "narration_blocks": [
        {
          "block_id": "b_0001",
          "text_tts": "Caligula began his reign...",
          "claim_ids": ["c_001"]
        }
      ]
    }
  }'
```

#### Response (Success)

```json
{
  "success": true,
  "shot_plan": { ... },
  "summary": {
    "total_scenes": 3,
    "total_duration_sec": 69,
    "version": "fda_v1"
  }
}
```

#### Response (Error)

```json
{
  "success": false,
  "error": "FDA_INPUT_MISSING: narration_blocks[] not found"
}
```

### Alternativní vstupní formáty

```json
// 1) Přímé narration_blocks
{ "narration_blocks": [...] }

// 2) Celý script_state
{ "script_state": { "tts_ready_package": {...} } }

// 3) tts_ready_package
{ "tts_ready_package": {...} }
```

---

## 🚀 Jak spustit lokálně

### 1. Test suite

```bash
cd backend
python3 test_fda.py
```

**Výstup:**
```
✅ Shot plan obsahuje 3 scén, celková délka 69s
✅ Všech 3 scén má správnou strukturu
✅ Všechny hodnoty jsou z povolených allowlistů
✅ Časová osa je kontinuální: 0s → 69s bez děr a překryvů
🎉 ACCEPTANCE CRITERIA: PASS
```

### 2. API endpoint test

```bash
# Spusť backend (pokud neběží)
cd backend
python3 app.py

# V jiném terminálu:
curl -X POST http://localhost:50000/api/fda/generate \
  -H "Content-Type: application/json" \
  -d @test_fda_fixture.json
```

### 3. Integrace v pipeline

```bash
# FDA automaticky běží po TTS Formatting
curl -X POST http://localhost:50000/api/script/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "dark hours of caligula",
    "language": "en",
    "target_minutes": 3
  }'

# Ověř výsledek
curl http://localhost:50000/api/script/state/<episode_id>
```

---

## ✅ Acceptance Criteria

### [1/3] Shot plan se uloží do script_state ✅

- `script_state.json` obsahuje klíč `shot_plan`
- Automaticky běží po TTS Formatting
- Perzistentní v `projects/<episode_id>/script_state.json`

### [2/3] Žádné externí API ✅

❌ Žádné volání Archive.org API  
❌ Žádné stahování videí  
❌ Žádný rendering / ffmpeg / moviepy změny  
❌ Žádné úpravy TTS textů nebo scénáře  
❌ Žádné "vyber konkrétní klip URL"  
❌ Žádné nové shot_types mimo allowlist  

### [3/3] Stabilní schema ✅

✅ Všechny scény mají povinné klíče  
✅ `shot_types` jen z allowlistu  
✅ `emotion` jen z allowlistu  
✅ `cut_rhythm` jen z allowlistu  
✅ `start_sec/end_sec` navazují (žádné díry, žádné překryvy)  
✅ `keywords`: 5-12 slov  
✅ `search_queries`: 3-8 dotazů  

---

## 📊 Ukázka reálného shot_plan JSON

### Fixture: 10 bloků → 3 scény

```json
{
  "version": "fda_v1",
  "source": "tts_ready_package",
  "generated_at": "2025-12-27T12:34:56.789Z",
  "assumptions": {
    "words_per_minute": 150,
    "target_scene_duration_sec": 27,
    "max_blocks_per_scene": 6
  },
  "scenes": [
    {
      "scene_id": "sc_0001",
      "start_sec": 0,
      "end_sec": 26,
      "narration_block_ids": ["b_0001", "b_0002", "b_0003", "b_0004"],
      "narration_summary": "Caligula began his reign with high popularity due to the memory of his father Germanicus.",
      "emotion": "hope",
      "keywords": [
        "caligula", "began", "reign", "high", "popularity",
        "memory", "father", "germanicus", "initial", "approval"
      ],
      "shot_strategy": {
        "shot_types": ["archival_documents", "maps_context"],
        "clip_length_sec_range": [4, 7],
        "cut_rhythm": "medium",
        "source_preference": ["archive_org"]
      },
      "search_queries": [
        "caligula", "began", "reign", "caligula began",
        "peaceful caligula", "caligula footage", "caligula reign"
      ]
    },
    {
      "scene_id": "sc_0002",
      "start_sec": 26,
      "end_sec": 49,
      "narration_block_ids": ["b_0005", "b_0006", "b_0007"],
      "narration_summary": "Caligula rapidly depleted the treasury surplus left by Tiberius on lavish spectacles and building projects.",
      "emotion": "tension",
      "keywords": [
        "caligula", "rapidly", "depleted", "treasury", "surplus",
        "tiberius", "lavish", "spectacles", "building", "projects"
      ],
      "shot_strategy": {
        "shot_types": ["destruction_aftermath", "industry_war_effort"],
        "clip_length_sec_range": [3, 5],
        "cut_rhythm": "fast",
        "source_preference": ["archive_org"]
      },
      "search_queries": [
        "caligula", "rapidly", "depleted", "caligula rapidly",
        "dramatic caligula", "caligula footage", "caligula depleted"
      ]
    },
    {
      "scene_id": "sc_0003",
      "start_sec": 49,
      "end_sec": 69,
      "narration_block_ids": ["b_0008", "b_0009", "b_0010"],
      "narration_summary": "He broke Roman precedent by demanding to be worshipped as a living deity, including plans to place his statue in the Temple of Jerusalem.",
      "emotion": "tragedy",
      "keywords": [
        "broke", "roman", "precedent", "demanding", "worshipped",
        "living", "deity", "including", "plans", "place"
      ],
      "shot_strategy": {
        "shot_types": ["leaders_speeches", "archival_documents"],
        "clip_length_sec_range": [5, 8],
        "cut_rhythm": "slow",
        "source_preference": ["archive_org"]
      },
      "search_queries": [
        "broke", "roman", "precedent", "broke roman",
        "destruction broke", "broke footage", "broke precedent"
      ]
    }
  ],
  "total_scenes": 3,
  "total_duration_sec": 69
}
```

---

## 🔍 Logování a error handling

### Success log

```python
print(f"✅ FDA: Vygenerován shot_plan s {shot_plan.get('total_scenes', 0)} scénami, celková délka {shot_plan.get('total_duration_sec', 0)}s")
```

### Error codes

| Error Code | Význam | HTTP Status |
|------------|--------|-------------|
| `FDA_INPUT_MISSING` | Chybí `narration_blocks[]` nebo `tts_ready_package` | 400 |
| `FDA_VALIDATION_FAILED` | shot_plan neprošel validací (allowlist porušení, časové díry) | 422 |

### Příklad error response

```json
{
  "success": false,
  "error": "FDA_INPUT_MISSING: narration_blocks[] not found in tts_ready_package"
}
```

---

## 🛠️ Implementační detaily

### Kde přesně to přidal (soubor(y), název funkcí/stepů)

#### 1. `backend/footage_director.py` (nový soubor)

**Hlavní funkce:**
- `generate_shot_plan()` - generuje shot_plan z narration_blocks
- `run_fda()` - pipeline entry point (přijímá script_state)
- `run_fda_standalone()` - standalone entry point (přijímá tts_ready_package)
- `validate_shot_plan()` - validace výstupu
- Helper funkce: `estimate_speech_duration_seconds()`, `determine_emotion()`, `extract_keywords_from_text()`, atd.

#### 2. `backend/script_pipeline.py` (modifikace)

**Přidané funkce:**
- `_run_footage_director()` - helper pro spuštění FDA kroku (řádek 823)

**Modifikovaná místa:**
- `_make_initial_state()` - přidán `"footage_director": step("footage_director")` do `steps` (řádek 267)
- `_make_initial_state()` - přidán `"shot_plan": None` do state (řádek 268)
- `_run_pipeline()` - přidáno volání FDA po TTS Formatting (řádek 1158-1162)
- `retry_step_async()` - přidána podpora `"footage_director"` (řádek 1174)
- `_run_pipeline_from_step()` - přidáno volání FDA v retry path (5 míst: řádky 1589, 1741, 1825, 1859, 1877)

#### 3. `backend/app.py` (modifikace)

**Přidaný endpoint:**
- `POST /api/fda/generate` (řádek 2001-2075)
  - Standalone endpoint pro testování FDA
  - Tolerance pro různé vstupní formáty
  - Error handling s FDA_* error codes

#### 4. `backend/test_fda.py` (nový soubor)

**Test suite:**
- 9 testů pokrývajících všechny acceptance criteria
- Fixture s 10 narration bloky
- Validace struktury, allowlistů, časové kontinuity

---

## 🚦 Jak to spustit (příkazy po řádcích)

### 1. Základní test

```bash
cd /Users/petrliesner/podcasts/backend
python3 test_fda.py
```

### 2. Standalone API test

```bash
# Terminal 1: Spusť backend (pokud neběží)
cd /Users/petrliesner/podcasts/backend
python3 app.py

# Terminal 2: Test API
curl -X POST http://localhost:50000/api/fda/generate \
  -H "Content-Type: application/json" \
  -d '{
    "narration_blocks": [
      {"block_id": "b_0001", "text_tts": "Test text here.", "claim_ids": []}
    ]
  }'
```

### 3. Kompletní pipeline test

```bash
# Vygeneruj nový script (FDA automaticky běží jako 6. krok)
curl -X POST http://localhost:50000/api/script/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "dark hours of caligula",
    "language": "en",
    "target_minutes": 3,
    "openai_api_key": "sk-..."
  }'

# Response obsahuje episode_id, např. "ep_abc123def456"

# Ověř, že shot_plan byl vygenerován
curl http://localhost:50000/api/script/state/ep_abc123def456 | jq '.shot_plan'
```

### 4. Retry pouze FDA kroku

```bash
curl -X POST http://localhost:50000/api/script/retry-step \
  -H "Content-Type: application/json" \
  -d '{
    "episode_id": "ep_abc123def456",
    "step_key": "footage_director"
  }'
```

---

## ✅ Potvrzení acceptance criteria

### ✅ 1) shot_plan se uloží do script_state

**Evidence:**
```bash
$ cat projects/ep_abc123def456/script_state.json | jq '.shot_plan'
{
  "version": "fda_v1",
  "source": "tts_ready_package",
  "scenes": [...]
}
```

### ✅ 2) žádné externí API

**Code evidence:**
```python
# footage_director.py neimportuje requests, urllib, nebo jakýkoli HTTP client
# Žádné volání archive.org, pexels.com, youtube.com
# Pouze čistý Python - text processing, JSON generation
```

### ✅ 3) stabilní schema

**Test evidence:**
```bash
$ python3 test_fda.py
✅ Všech 3 scén má správnou strukturu
✅ Všechny hodnoty jsou z povolených allowlistů
✅ Časová osa je kontinuální: 0s → 69s bez děr a překryvů
🎉 ACCEPTANCE CRITERIA: PASS
```

---

## 📝 Co dál (Future enhancements)

FDA je MVP a může být v budoucnu rozšířen o:

1. **Dynamické allowlisty** - konfigurovatelné shot_types per projekt
2. **Pokročilá keyword extrakce** - NLP místo regex
3. **Integrace s claim_ids** - mapování claims → doporučené footage typy
4. **Multi-language support** - stopwords pro češtinu, němčinu, atd.
5. **Shot_plan validation API** - `/api/fda/validate` endpoint

---

## 🐛 Troubleshooting

### Problem: "FDA_INPUT_MISSING: narration_blocks[] not found"

**Příčina:** `tts_ready_package` neobsahuje `narration_blocks[]` nebo `tts_segments[]`

**Řešení:**
```python
# Zkontroluj strukturu tts_ready_package
print(json.dumps(script_state["tts_ready_package"], indent=2))
```

### Problem: "FDA_VALIDATION_FAILED: shot_type 'xyz' není v allowlistu"

**Příčina:** Snaha použít custom shot_type mimo allowlist

**Řešení:** Použij pouze povolené shot_types z `ALLOWED_SHOT_TYPES`

### Problem: Shot_plan má "díry" v časové ose

**Příčina:** Bug v `generate_shot_plan()` nebo nesprávný vstup

**Řešení:**
```bash
# Spusť validaci
python3 -c "
from footage_director import validate_shot_plan
import json
with open('shot_plan.json') as f:
    sp = json.load(f)
print(validate_shot_plan(sp))
"
```

---

## 📞 Kontakt a podpora

Pro otázky nebo bug reporty vytvořte issue s tagem `[FDA]`.

---

**Poslední aktualizace:** 2025-12-27  
**Verze FDA:** v1  
**Kompatibilita:** Python 3.8+, žádné externí dependencies



