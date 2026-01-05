# Archive Downloader + Compiler Pipeline - Dokumentace

## 🎯 Přehled

Tato feature rozšiřuje FDA (Footage Director Assistant) o **exekuční balíček**:

1. **FDA** (Footage Director) → generuje shot_plan s compile_plan a search queries
2. **AAR** (Archive Asset Resolver) → převádí queries na konkrétní archive.org assety
3. **CB** (Compilation Builder) → stahuje assety a kompiluje finální video

**Output:** `episode_compilation.mp4` (56s/1min dle targetu)

---

## 📊 Architektura

### Nové moduly

```
backend/
├── footage_director.py          # ✅ UPDATED: rozšířen schema (assets[], compile_plan)
├── archive_asset_resolver.py    # ✅ NEW: AAR modul
├── compilation_builder.py       # ✅ NEW: CB modul
├── script_pipeline.py           # ✅ UPDATED: integrace AAR + CB
└── test_archive_pipeline.py     # ✅ NEW: integrační test
```

### Pipeline flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Research → 2. Narrative → 3. Validation → 4. Composer  │
│  5. TTS Format                                              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  6. FDA (Footage Director)                                  │
│     Input:  tts_ready_package                               │
│     Output: shot_plan (with assets[], compile_plan)         │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  7. AAR (Archive Asset Resolver)                            │
│     Input:  shot_plan.search_queries[]                      │
│     Output: fda_package (enriched shot_plan with real URLs) │
│     - Search archive.org API                                │
│     - Resolve concrete item IDs + URLs                      │
│     - Cache results (7 days)                                │
│     - Throttling: 2 req/s                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  8. CB (Compilation Builder)                                │
│     Input:  fda_package                                     │
│     Output: episode_compilation.mp4                         │
│     - Download assets (cache v projects/<id>/assets/)       │
│     - Create subclips (FFmpeg)                              │
│     - Concatenate timeline                                  │
│     - Export final video                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Změny v FDA (footage_director.py)

### Nový schema výstupu

FDA nyní vrací **rozšířený** shot_plan:

```json
{
  "scenes": [
    {
      "scene_id": "sc_0001",
      "start_sec": 0,
      "end_sec": 25,
      "narration_block_ids": ["b_0001", "b_0002"],
      "narration_summary": "Brief summary",
      "emotion": "neutral",
      "keywords": ["word1", "word2", ...],
      "shot_strategy": { ... },
      "search_queries": ["query1", "query2", ...],
      
      // ✅ NOVÉ: assets[] (placeholder při FDA, naplní AAR)
      "assets": [
        {
          "provider": "archive_org",
          "query_used": "World War 2 footage",
          "archive_item_id": "placeholder_collection_1940",
          "asset_url": "https://archive.org/details/...",
          "media_type": "video",
          "priority": 1,
          "use_as": "primary_broll",
          "recommended_subclips": [
            {
              "in_sec": 0,
              "out_sec": 5,
              "reason": "Shows relevant content"
            }
          ],
          "safety_tags": ["no_gore", "implied_only"]
        }
      ]
    }
  ],
  
  // ✅ NOVÉ: compile_plan na root level
  "compile_plan": {
    "target_fps": 30,
    "resolution": "1920x1080",
    "music": "none",
    "transitions_allowed": ["hard_cut", "fade"],
    "max_clip_repeat_sec": 0,
    "caption_style": "none"
  }
}
```

### Validace

`validate_and_fix_shot_plan()` rozšířena o validaci:

- `compile_plan` (required na root)
- `assets[]` strukturu pro každou scene
- Povinné klíče: `provider`, `media_type`, `priority`, `use_as`, `safety_tags`

---

## 🔍 Archive Asset Resolver (AAR)

### Funkce

```python
from archive_asset_resolver import resolve_shot_plan_assets

enriched_plan, metadata = resolve_shot_plan_assets(
    shot_plan,
    cache_dir="./cache",
    throttle_delay_sec=0.5
)
```

### Implementační detaily

**Search API:**
- URL: `https://archive.org/advancedsearch.php`
- Preferuje: `prelinger`, `opensource_movies` collections
- Sort: `downloads desc` (populární první)

**Cache:**
- Lokace: `projects/<episode_id>/archive_cache/`
- Format: `archive_search_<hash>.json`
- TTL: 7 dní (pro MVP není implementováno, ale příprava je)

**Throttling:**
- Default: 0.5s delay = 2 req/s
- Konfigurovatelné přes parametr

**Fallback:**
- Pokud search nenajde dost assetů (min 3), generuje fallback
- Fallback má `priority: 3`, `use_as: "transition"`
- Pro production by měl být fallback content předpřipravený

### Výstup

Každá scene dostane 3-8 assetů:

- **priority 1:** Top 2 assets (nejvíc downloads)
- **priority 2:** Backup 3 assety
- **priority 3:** Emergency fallback

---

## 🎬 Compilation Builder (CB)

### Funkce

```python
from compilation_builder import build_episode_compilation

output_video, metadata = build_episode_compilation(
    fda_package,
    episode_id="ep_001",
    storage_dir="./storage",
    output_dir="./output"
)
```

### Implementační detaily

**Download:**
- Metadata API: `https://archive.org/metadata/<item_id>`
- Preferuje: MP4 format
- Cache: `projects/<episode_id>/assets/asset_<hash>.mp4`

**Subclip:**
- FFmpeg command: `-ss <in> -t <duration> -c:v libx264 -preset fast`
- Timeout: 5 minut per clip

**Concatenation:**
- FFmpeg concat demuxer
- Target FPS/resolution z compile_plan
- Output: `episode_<id>_compilation_<timestamp>.mp4`

**Error handling:**
- Pokud asset download selže → skip scene
- Pokud žádné klipy → vrátí None + error metadata
- Timeout protection na všech subprocess calls

---

## 🗂️ Storage struktura

```
projects/
└── ep_<episode_id>/
    ├── script_state.json           # Stav pipeline (obsahuje fda_package)
    ├── archive_cache/              # AAR search cache
    │   └── archive_search_*.json
    └── assets/                     # CB downloaded assets
        ├── asset_abc123.mp4
        ├── asset_def456.mp4
        └── scene_sc_0001_clip.mp4  # Subclips

output/
└── episode_<id>_compilation_<timestamp>.mp4
```

---

## 🧪 Testing

### Integrační test

```bash
cd backend
export OPENAI_API_KEY=sk-...
python3 test_archive_pipeline.py
```

**Test flow:**

1. Vytvoří sample TTS package (4 segmenty, ~20s)
2. Zavolá FDA → ověří shot_plan + compile_plan
3. Zavolá AAR → ověří assets jsou naplněné
4. Zavolá CB → ověří output video (může selhat s fallback assety)

**Expected output:**

```
======================================================================
📊 TEST SUMMARY
======================================================================
✅ FDA: Shot plan generated
✅ AAR: 12 assets resolved
✅ CB: Video compiled successfully
   Output: /tmp/.../episode_test_episode_001_compilation_20250727_123456.mp4

🎉 Integration test PASSED
```

---

## 📝 script_state.json změny

Nová pole v `script_state.json`:

```json
{
  "episode_id": "ep_...",
  "steps": {
    "footage_director": { ... },
    "asset_resolver": { "status": "DONE", ... },      // ✅ NOVÉ
    "compilation_builder": { "status": "DONE", ... }  // ✅ NOVÉ
  },
  "shot_plan": { ... },                    // FDA output
  "fda_package": { ... },                  // ✅ NOVÉ: AAR output (enriched shot_plan)
  "compilation_video_path": "output/...",  // ✅ NOVÉ: CB output path
  "asset_resolver_output": { ... },        // ✅ NOVÉ: AAR metadata
  "compilation_builder_output": { ... }    // ✅ NOVÉ: CB metadata
}
```

---

## 🔄 Retry support

Pipeline podporuje retry nových kroků:

```python
# Retry celé pipeline od asset_resolver
pipeline.retry_step_async(episode_id, "asset_resolver", provider_api_keys)

# Retry compilation (pokud download selhal)
pipeline.retry_step_async(episode_id, "compilation_builder", provider_api_keys)
```

---

## ⚠️ Známá omezení (MVP)

1. **Fallback content není reálný**
   - Pro production doporučujeme mít předpřipravené fallback klipy
   
2. **Cache expiration není implementována**
   - Archive.org search cache nemá TTL enforcement (jen placeholder)
   
3. **Žádná parallel downloads**
   - Assets se stahují sekvenčně (pro throttling)
   
4. **Žádné retry na asset level**
   - Pokud download selže, scene se přeskočí (neopakuje se)

5. **Hardcoded archive.org provider**
   - Budoucí: podpora Pexels, YouTube, vlastních media

---

## 🚀 Použití v produkci

### Spuštění pipeline

Pipeline automaticky běží při `start_pipeline_async()`:

```python
episode_id = pipeline.start_pipeline_async(
    topic="World War 2",
    language="en-US",
    target_minutes=1,
    channel_profile="documentary",
    provider_api_keys={"openai": "sk-..."}
)

# Počká na dokončení všech 8 kroků (včetně AAR + CB)
```

### Monitoring

```python
state = store.read_script_state(episode_id)

# Kontrola FDA
if state["steps"]["footage_director"]["status"] == "DONE":
    shot_plan = state["shot_plan"]

# Kontrola AAR
if state["steps"]["asset_resolver"]["status"] == "DONE":
    fda_package = state["fda_package"]
    total_assets = state["asset_resolver_output"]["total_assets_resolved"]

# Kontrola CB
if state["steps"]["compilation_builder"]["status"] == "DONE":
    video_path = state["compilation_video_path"]
    file_size = state["compilation_builder_output"]["output_size_bytes"]
```

---

## 📚 API Reference

### ArchiveAssetResolver

```python
class ArchiveAssetResolver:
    def __init__(self, cache_dir: str, throttle_delay_sec: float = 0.5)
    
    def search_archive_org(self, query: str, max_results: int = 10) -> List[Dict]
    
    def resolve_scene_assets(
        self,
        scene: Dict,
        min_assets_per_scene: int = 3,
        max_assets_per_scene: int = 8
    ) -> List[Dict]
```

### CompilationBuilder

```python
class CompilationBuilder:
    def __init__(self, storage_dir: str, output_dir: str)
    
    def download_asset(self, asset: Dict) -> Optional[str]
    
    def create_subclip(
        self,
        source_file: str,
        in_sec: float,
        out_sec: float,
        output_file: str
    ) -> bool
    
    def concatenate_clips(
        self,
        clip_files: List[str],
        output_file: str,
        target_fps: int = 30,
        resolution: str = "1920x1080"
    ) -> bool
    
    def build_compilation(
        self,
        fda_package: Dict,
        episode_id: str,
        target_duration_sec: Optional[float] = None
    ) -> Tuple[Optional[str], Dict]
```

---

## 🎉 Hotovo!

Pipeline je nyní kompletní:

✅ FDA generuje shot_plan + compile_plan + assets schema  
✅ AAR resolvuje archive.org assety s cache + throttling  
✅ CB stahuje + kompiluje finální video  
✅ Integrace do script_pipeline  
✅ Retry support  
✅ Integrační test

**Next steps:**

- Spustit test: `python3 backend/test_archive_pipeline.py`
- Testovat na reálném projektu
- Přidat UI pro monitoring AAR/CB kroků



