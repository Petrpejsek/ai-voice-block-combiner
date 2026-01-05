# ✅ FDA přepsán na LLM-assisted - Delivery Report

## 🎯 Změna

**Před:** FDA byl čistě **deterministický** (keyword-based heuristika)  
**Po:** FDA je **LLM-assisted** s deterministickou validací

---

## 📊 Co se změnilo

### 1️⃣ Core modul: `backend/footage_director.py` (přepsán)

#### Nové funkce:
- ✅ `_prompt_footage_director()` - vytvoří prompt pro LLM
- ✅ `run_fda_llm()` - hlavní LLM-assisted entry point
- ✅ `validate_and_fix_shot_plan()` - deterministická validace + auto-fix
- ✅ `_build_narration_summary()` - helper pro prompt building

#### Odstraněné funkce:
- ❌ `determine_emotion()` - nahrazeno LLM rozhodnutím
- ❌ `extract_keywords_from_text()` - nahrazeno LLM
- ❌ `select_shot_types()` - nahrazeno LLM
- ❌ `generate_search_queries()` - nahrazeno LLM
- ❌ `generate_shot_plan()` - nahrazeno LLM call

#### Zachované:
- ✅ `estimate_speech_duration_seconds()` - pro prompt building
- ✅ `ALLOWED_*` allowlisty - pro validaci
- ✅ `_now_iso()` - pro timestamping

### 2️⃣ Pipeline: `backend/script_pipeline.py`

**Změny:**
```python
# Import
from footage_director import run_fda_llm  # místo run_fda

# Config
"footage_director_config": _default_step_config("footage_director")
# Default: provider=openai, model=gpt-4o-mini, temperature=0.2

# Raw output
"footage_director_raw_output": None  # ukládá LLM response + validace

# Helper funkce
def _run_footage_director(..., provider_api_keys, ...):
    # Volá run_fda_llm() místo deterministického run_fda()
    shot_plan, raw_text, metadata = run_fda_llm(...)
```

### 3️⃣ API endpoint: `backend/app.py`

**Změny:**
```python
POST /api/fda/generate

# Nové parametry (optional):
{
  "tts_ready_package": {...},
  "provider": "openai",         # NEW
  "model": "gpt-4o-mini",        # NEW
  "temperature": 0.2             # NEW
}

# Response obsahuje:
{
  "success": true,
  "shot_plan": {...},
  "summary": {
    ...
    "auto_fixed": false  # NEW - pokud validace opravila chyby
  }
}
```

### 4️⃣ UI: `frontend/src/components/VideoProductionPipeline.js`

**Změny:**
```
Před: 6) Footage Director (Deterministický)
Po:   6) Footage Director (LLM-assisted)

Popis:
- "LLM asistent který generuje shot_plan"
- "Používá LLM pro kreativní rozhodnutí + deterministickou validaci"
- LLM Config: gpt-4o-mini, temp 0.2
- Validace: allowlisty, kontinuita, auto-fix
```

---

## 🔍 Jak to funguje

### Flow:

```
1. Vstup: tts_ready_package.narration_blocks[]

2. LLM Prompt:
   - Přehled narration bloků (text + timing)
   - Schema s povinnými klíči
   - STRICT RULES (allowlisty, kontinuita)
   - Příklady

3. LLM Call:
   - Model: gpt-4o-mini (default)
   - Temperature: 0.2 (low = konzistentní)
   - Timeout: 600s

4. LLM Response → shot_plan_raw

5. Deterministická validace:
   ✓ Allowlisty (shot_types, emotion, cut_rhythm)
   ✓ Časová kontinuita (žádné díry/překryvy)
   ✓ Všechny bloky použity přesně jednou
   ✓ Keywords count (5-12)
   ✓ Search queries count (3-8)

6. Auto-fix (pokud enabled):
   - Invalid emotion → "neutral"
   - Invalid shot_types → filtruj nebo "archival_documents"
   - Invalid cut_rhythm → "medium"
   - Časové díry → oprav start_sec
   - Keywords/queries count → doplň nebo zkrať

7. Výstup: shot_plan + validation_errors[]

8. Ulož do script_state.json
```

---

## ✅ Acceptance Criteria

### [1/3] LLM-assisted ✅
- FDA používá LLM (gpt-4o-mini) pro kreativní rozhodnutí
- Model: `gpt-4o-mini` (default), temp: `0.2`
- Stejný pattern jako ostatní asistenti (config, API keys)

### [2/3] Deterministická validace ✅
- Allowlisty: `ALLOWED_SHOT_TYPES`, `ALLOWED_EMOTIONS`, `ALLOWED_CUT_RHYTHMS`
- Časová kontinuita: žádné díry, žádné překryvy
- Každý block použit přesně jednou
- Auto-fix neplatných hodnot (default enabled)

### [3/3] Shot_plan uložen ✅
- `script_state.shot_plan = { ... }`
- `script_state.footage_director_raw_output = { LLM response + validace }`

---

## 🚀 Jak testovat

### Test 1: Jednostavný LLM test

```bash
cd /Users/petrliesner/podcasts/backend

# Nastav API key
export OPENAI_API_KEY=sk-...

# Spusť test
python3 test_fda_llm.py
```

**Očekávaný výstup:**
```
✅ LLM call úspěšný: 2 scén
   Model: gpt-4o-mini, Temp: 0.2
   Auto-fixed: False
✅ Validace prošla: allowlisty OK, kontinuita OK
🎉 ACCEPTANCE CRITERIA: PASS
```

### Test 2: API endpoint

```bash
# Terminal 1: Backend
cd /Users/petrliesner/podcasts/backend
export OPENAI_API_KEY=sk-...
python3 app.py

# Terminal 2: Test
curl -X POST http://localhost:50000/api/fda/generate \
  -H "Content-Type: application/json" \
  -d '{
    "narration_blocks": [
      {"block_id": "b_01", "text_tts": "Test text 1.", "claim_ids": []},
      {"block_id": "b_02", "text_tts": "Test text 2.", "claim_ids": []}
    ],
    "model": "gpt-4o-mini",
    "temperature": 0.2
  }'
```

### Test 3: Kompletní pipeline

```bash
# Vygeneruj nový script (FDA automaticky běží s LLM)
curl -X POST http://localhost:50000/api/script/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "test llm fda",
    "language": "en",
    "target_minutes": 2,
    "openai_api_key": "sk-..."
  }'

# Response: {"success": true, "episode_id": "ep_..."}

# Ověř shot_plan
curl http://localhost:50000/api/script/state/ep_... | jq '.shot_plan'
```

---

## 📝 LLM Prompt (ukázka)

```
You are a Footage Director Assistant. Your task is to create a shot_plan...

INPUT:
- Narration blocks (text + timing)

OUTPUT: JSON object matching this EXACT schema:
{
  "scenes": [
    {
      "scene_id": "sc_0001",
      "start_sec": 0,
      "end_sec": 25,
      "narration_block_ids": ["b_0001", "b_0002"],
      "emotion": "neutral",
      "keywords": ["word1", "word2", ...],
      "shot_strategy": {
        "shot_types": ["archival_documents"],
        "clip_length_sec_range": [4, 7],
        "cut_rhythm": "medium"
      },
      "search_queries": ["query1", "query2", ...]
    }
  ]
}

STRICT RULES:
- emotion: ONLY one of: neutral, tension, tragedy, hope, victory, mystery
- shot_types: ONLY from: historical_battle_footage, troop_movement, ...
- cut_rhythm: ONLY one of: slow, medium, fast
- start_sec/end_sec: continuous (no gaps, no overlaps)

NARRATION BLOCKS (5 total, ~60s):
b_0001 (~10s): Caligula began his reign...
b_0002 (~15s): Ancient historians identify...
...
```

---

## 🔧 Konfigurace

### V script_state.json:

```json
{
  "footage_director_config": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "prompt_template": null
  }
}
```

### V API callu:

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.2
}
```

---

## 🎯 Výhody LLM-assisted

### Před (deterministický):
❌ Keyword-based heuristika  
❌ Rigidní pravidla  
❌ Omezená kreativita  
❌ Nemohl pochopit kontext  

### Po (LLM-assisted):
✅ Kreativní rozhodnutí (emotion, keywords, queries)  
✅ Kontextové porozumění narration  
✅ Přírodní groupování scén  
✅ Lepší search queries  
✅ + Stabilita díky deterministické validaci  

---

## 📂 Soubory změněny

1. **`backend/footage_director.py`** - přepsán na LLM-assisted
2. **`backend/script_pipeline.py`** - aktualizován pro LLM call
3. **`backend/app.py`** - endpoint podporuje LLM config
4. **`frontend/src/components/VideoProductionPipeline.js`** - UI aktualizováno
5. **`backend/test_fda_llm.py`** - nový test pro LLM verzi

---

## ⚠️ Breaking Changes

### API:
- `run_fda()` → `run_fda_llm()` (nová signatura)
- `run_fda_standalone()` nyní vyžaduje `provider_api_keys` parametr

### Pipeline:
- FDA config vyžadován (default: gpt-4o-mini, temp 0.2)
- API key potřeba pro běh

---

## 🚦 Restart potřeba

```bash
# Backend
kill $(lsof -ti:50000)
cd /Users/petrliesner/podcasts/backend
export OPENAI_API_KEY=sk-...
python3 app.py

# Frontend
kill $(lsof -ti:4000)
cd /Users/petrliesner/podcasts/frontend
PORT=4000 npm start
```

---

**Status:** ✅ Hotovo  
**Verze:** FDA v1_llm  
**LLM:** gpt-4o-mini @ 0.2 temp  
**Validace:** Deterministická + auto-fix



