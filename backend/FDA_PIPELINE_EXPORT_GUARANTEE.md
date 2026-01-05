# FDA Pipeline Export Guarantee

## 🎯 Cíl

Zajistit, že pipeline ukládá a exportuje **POUZE POST-PROCESSED** shot plan, nikdy raw LLM output.

## 📋 Implementace

### 1. Rozlišení objektů v `_run_footage_director`

```python
# ❌ PŘED: Nerozlišené objekty
raw_output = run_llm(...)  # Raw LLM
fixed = fix(raw_output)    # Fixed
state["shot_plan"] = fixed  # Ukládá fixed, ale není jasné co to je

# ✅ PO: Jasné rozlišení
llm_draft = run_fda_llm(...)           # Raw LLM draft (může být špatně)
final_shot_plan = llm_draft            # Už post-processed (apply_deterministic_generators_v27 uvnitř)
validate_fda_hard_v27(final_shot_plan) # Hard validation
state["shot_plan"] = final_shot_plan   # Ukládá POUZE final
```

### 2. Dva módy FDA

**v3 mode (default):**
- LLM: `run_sceneplan_llm` → ScenePlan v3
- Compiler: `compile_shotplan_v3` → ShotPlan v3 (deterministic)
- Validator: `validate_shotplan_v3_minimal`
- Output: `{"shot_plan": {"version": "shotplan_v3", ...}}`

**v2.7 mode (opt-in via config):**
- LLM: `run_fda_llm` → raw draft
- Post-processor: `apply_deterministic_generators_v27` (uvnitř run_fda_llm)
- Validator: `validate_fda_hard_v27`
- Output: `{"shot_plan": {"version": "fda_v2.7", "source": "tts_ready_package", ...}}`

### 3. Hard Assertion před uložením

**Location:** `script_pipeline.py:_run_footage_director` (před `state["shot_plan"] = fixed_wrapper`)

**Kontroly (FAIL-STOP):**

```python
# 1. Verze
if use_v27_mode and sp_version != "fda_v2.7":
    raise RuntimeError(f"FDA_VERSION_MISMATCH")

# 2. Source
if use_v27_mode and sp_source != "tts_ready_package":
    raise RuntimeError(f"FDA_SOURCE_MISMATCH")

# 3. Žádné extra top-level keys (v2.7)
allowed_keys = {"version", "source", "assumptions", "scenes"}
extra_keys = set(sp.keys()) - allowed_keys
if use_v27_mode and extra_keys:
    raise RuntimeError(f"FDA_EXTRA_FIELDS: {list(extra_keys)}")

# 4. source_preference je list (v2.7)
for scene in scenes:
    source_pref = scene["shot_strategy"]["source_preference"]
    if not isinstance(source_pref, list):
        raise RuntimeError(f"FDA_INVALID_SOURCE_PREF: must be list")
    if source_pref != ["archive_org"]:
        raise RuntimeError(f"FDA_INVALID_SOURCE_PREF: must be ['archive_org']")
```

### 4. Logging

**FDA_FINAL_PLAN_SAVED** (1 řádek):
```
FDA_FINAL_PLAN_SAVED { version=fda_v2.7, scene_count=5, episode_id=ep_abc123, mode=v2.7, post_processed=True }
```

**FDA_LLM_DRAFT_IGNORED** (pokud existuje draft):
```
📝 FDA_LLM_DRAFT_IGNORED {reason: 'no_api_key'}
```

nebo

```python
print(f"📝 FDA v2.7: Got LLM draft (will be post-processed)")
```

## 🔒 Garantovaný Export

### Endpoint: `/api/script/state/<episode_id>`

**Response:**
```json
{
  "success": true,
  "data": {
    "shot_plan": {
      "shot_plan": {
        "version": "fda_v2.7",              // ✅ VŽDY fda_v2.7 (v2.7 mode)
        "source": "tts_ready_package",      // ✅ VŽDY tts_ready_package
        "assumptions": {...},
        "scenes": [
          {
            "scene_id": "sc_0001",
            "shot_strategy": {
              "source_preference": ["archive_org"],  // ✅ VŽDY list
              "shot_types": ["archival_documents"]
            },
            "search_queries": [...]         // ✅ Post-processed (5 queries, clean)
          }
        ]
      }
    },
    "metadata": {
      "shot_plan": { /* stejné jako výše */ }
    }
  }
}
```

### ❌ V exportu NIKDY neuvidíme:

1. **Nesprávné verze:**
   - ❌ `"version": "shotplan_v3"` (když use_v27_mode=true)
   - ❌ `"version": null`

2. **Extra fields:**
   - ❌ `"total_duration_sec": 120`
   - ❌ `"total_scenes": 5`
   - ❌ Jakýkoliv jiný top-level key mimo `{version, source, assumptions, scenes}`

3. **Špatný source:**
   - ❌ `"source": "llm_draft"`
   - ❌ `"source": null`

4. **String source_preference:**
   - ❌ `"source_preference": "archive_org"`  (string místo array)

5. **Raw LLM artifacts:**
   - ❌ Queries začínající "These", "The", "A"
   - ❌ Keywords s forbidden tokens (the, a, an)
   - ❌ Queries se 2 object types

## 🧪 Testování

### Manuální test

```bash
# 1. Nastavit v2.7 mode pro epizodu
# V footage_director_config:
{
  "use_v27_mode": true,
  "provider": "openai",
  "model": "gpt-4o-mini"
}

# 2. Spustit FDA krok
curl -X POST http://localhost:50000/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{"episode_id": "ep_xxx", "start_from": "footage_director"}'

# 3. Zkontrolovat export
curl http://localhost:50000/api/script/state/ep_xxx | jq '.data.shot_plan.shot_plan.version'
# Očekáváno: "fda_v2.7"

curl http://localhost:50000/api/script/state/ep_xxx | jq '.data.shot_plan.shot_plan.source'
# Očekáváno: "tts_ready_package"

curl http://localhost:50000/api/script/state/ep_xxx | jq '.data.shot_plan.shot_plan | keys'
# Očekáváno: ["assumptions", "scenes", "source", "version"]
# (ŽÁDNÉ extra keys)
```

### Automatický test

Viz `test_fda_pipeline_export_guarantee.py`

## 🔄 Aktivace v2.7 módu

### Globální konfigurace (pro všechny nové epizody)

```python
# backend/script_pipeline.py: _default_step_config
def _default_step_config(step_key: str) -> dict:
    if step_key == "footage_director":
        return {
            "provider": "openrouter",
            "model": "openai/gpt-4o-mini",
            "temperature": 0.2,
            "use_v27_mode": True,  # ✅ Aktivovat v2.7 mode
        }
```

### Per-episode konfigurace

```python
# Při vytváření epizody:
pipeline.start_pipeline_async(
    topic="...",
    language="cs",
    target_minutes=10,
    channel_profile="educational",
    provider_api_keys={...},
    footage_director_config={
        "use_v27_mode": True,  # ✅ Tato epizoda použije v2.7
    }
)
```

### API endpoint

```bash
# Aktualizovat config pro existující epizodu
curl -X POST http://localhost:50000/api/episodes/ep_xxx/footage_director_config \
  -H "Content-Type: application/json" \
  -d '{"use_v27_mode": true}'
```

## 📊 Monitoring

**Logy v pipeline:**

```
🔧 Applying deterministic generators to FDA output...
✅ Deterministic generators applied successfully
FDA_FINAL_PLAN_SAVED { version=fda_v2.7, scene_count=5, episode_id=ep_abc123, mode=v2.7, post_processed=True }
✅ FDA: Saved fda_v2.7 shot_plan with 5 scenes (mode: v2.7)
```

**Logy při hard assertion failure:**

```
❌ FDA v2.7 validation FAILED: FDA_VALIDATION_FAILED: {...}
RuntimeError: FDA_V27_VALIDATION_FAILED: Post-processed shot plan failed validation
```

## 🎯 Definition of Done

✅ **V exportu epizody (GET /api/script/state/<ep>) už NIKDY neuvidíme:**

1. ❌ `"version": "shotplan_v3"` (když use_v27_mode=true)
2. ❌ `"total_duration_sec": 120`
3. ❌ `"source_preference": "archive_org"` (string)

✅ **V exportu je VŽDY (v2.7 mode):**

1. ✅ `"version": "fda_v2.7"`
2. ✅ `"source": "tts_ready_package"`
3. ✅ `"source_preference": ["archive_org"]` (array)
4. ✅ Přesně keys: `{version, source, assumptions, scenes}`
5. ✅ Všechny queries clean (no "These", no double object types)

✅ **Golden contract testy + reálný běh to potvrzují**

---

**Last Updated:** December 2024  
**Maintainer:** FDA Pipeline Team  
**Status:** ✅ Implemented & Tested



