# 📐 ARCHITECTURE ANALYSIS - Complete Flow, Contracts & Integration Points

**Cíl:** Kompletní soupis architektury pro návrh perfektní architektury s 2 AI asistenty (Query Director + Curator) a source packem.

**Datum:** 2025-01-05  
**Analyzováno:** 100% současné codebase

---

## 🔍 1) SOUČASNÝ END-TO-END FLOW

### **Pipeline Overview**

Pipeline má 8 hlavních kroků od tématu po finální video:

```
USER INPUT (topic)
   ↓
1. RESEARCH ASSISTANT (LLM) → research.json
   ↓
2. NARRATIVE ASSISTANT (LLM) → draft_script.json
   ↓
3. VALIDATOR ASSISTANT (LLM) → validation_result.json
   ↓
4. COMPOSER (deterministic) → tts_ready_package.json
   ↓
5. VOICEOVER GENERATION (ElevenLabs TTS) → *.mp3 files
   ↓
6. FOOTAGE DIRECTOR (FDA - LLM) → shot_plan.json
   ↓
7. ARCHIVE ASSET RESOLVER (AAR - search) → archive_manifest.json
   ↓
8. COMPILATION BUILDER (CB - FFmpeg) → final.mp4
```

---

### **KROK 1: RESEARCH ASSISTANT** ⚡ **TADY VZNIKÁ TÉMA**

**Soubor:** `backend/script_pipeline.py`  
**Funkce:** `_step_research()`  
**Volající:** `/api/script/generate` endpoint v `app.py`

**Flow:**
```
INPUT: 
  - topic (string, user input)
  - language (string)
  - target_minutes (int)
  - channel_profile (string)

TRANSFORMACE:
  1. Sestaví prompt pro Research Assistant (LLM)
  2. Volá LLM (OpenAI/OpenRouter) s promptem
  3. Parse JSON response
  4. Validace struktury

OUTPUT (research_report.json):
  {
    "topic": "Napoleon in Moscow: The 1812 Occupation",
    "language": "en",
    "timeline": [{"period": "1812", "event": "..."}],
    "claims": [{"claim_id": "c_001", "text": "...", "importance": "high"}],
    "entities": [{"name": "Napoleon", "type": "person"}],
    "open_questions": ["..."]
  }

ULOŽENÍ: projects/<episode_id>/script_state.json → metadata.research_report
```

**Kde se ukládá:**
- Primárně: `script_state.json` (persistent state)
- Format: JSON object v `metadata.research_report`

**❌ PROBLÉM:** 
- Žádná kontrola "coverage" (mapy/lidi/dokumenty/místa nejsou systematicky mapovány)
- Entities jsou jen seznam, není typologie (geography, artifacts, events)

---

### **KROK 2: NARRATIVE ASSISTANT**

**Soubor:** `backend/script_pipeline.py`  
**Funkce:** `_step_narrative()`  
**Volající:** Script pipeline (následuje po Research)

**Flow:**
```
INPUT:
  - research_report (z kroku 1)
  - channel_profile
  - patch_instructions (optional)

TRANSFORMACE:
  1. Sestaví prompt s research_report + creative guidelines
  2. Volá LLM pro narrative structuring
  3. Parse JSON response
  4. Validace chapter/block structure

OUTPUT (draft_script.json):
  {
    "title_candidates": ["..."],
    "hook": "In 1812...",
    "chapters": [
      {
        "chapter_id": "ch_01",
        "title": "Aims of the Invasion",
        "narration_blocks": [
          {
            "block_id": "b_0001",
            "text": "In eighteen twelve, Napoleon led...",
            "claim_ids": ["c_001"]
          }
        ]
      }
    ]
  }

ULOŽENÍ: script_state.json → metadata.draft_script
```

**❌ PROBLÉM:**
- Žádný explicitní "visual intent" per block/chapter
- Není guidance pro AAR (co potřebujeme vizuálně)

---

### **KROK 3: VALIDATOR ASSISTANT**

**Soubor:** `backend/script_pipeline.py`  
**Funkce:** `_step_validation()`

**Flow:**
```
INPUT:
  - research_report
  - draft_script

TRANSFORMACE:
  1. Cross-check fact claims vs narrative
  2. Validace claim_ids integrity
  3. LLM verification of accuracy

OUTPUT (validation_result.json):
  {
    "status": "PASS" | "FAIL",
    "issues": [...],
    "approved_script": {...}
  }

ULOŽENÍ: script_state.json → metadata.validation_result
```

---

### **KROK 4: COMPOSER (DETERMINISTIC)**

**Soubor:** `backend/script_pipeline.py`  
**Funkce:** `_deterministic_compose()`

**Flow:**
```
INPUT:
  - research_report
  - draft_script
  - validation_result

TRANSFORMACE (PURE DETERMINISTIC, NO LLM):
  1. Merge validated script into final structure
  2. Flatten narration_blocks across chapters
  3. Add TTS guidelines
  4. Title selection (deterministic)

OUTPUT (tts_ready_package.json):
  {
    "episode_id": "ep_024286848837",
    "language": "en",
    "selected_title": "Napoleon in Moscow: The 1812 Occupation",
    "chapters": [...],
    "narration_blocks": [
      {
        "block_id": "b_0001",
        "claim_ids": ["c_001"],
        "text_tts": "In eighteen twelve, Napoleon led..."
      }
    ],
    "tts_guidelines": {
      "voice_style": "documentary_narrator",
      "pace_wpm_hint": 160
    }
  }

ULOŽENÍ: script_state.json → metadata.tts_ready_package
```

---

### **KROK 5: VOICEOVER GENERATION (TTS)**

**Soubor:** `backend/app.py`  
**Endpoint:** `/api/generate-voiceover/<episode_id>`  
**Funkce:** Integrace s ElevenLabs nebo Google TTS

**Flow:**
```
INPUT:
  - tts_ready_package (z kroku 4)
  - ElevenLabs API key

TRANSFORMACE:
  1. Extract narration_blocks[] z package
  2. Pro každý block:
     - Volá ElevenLabs TTS API s text_tts
     - Získá audio (MP3 base64)
     - Save to projects/<episode_id>/voiceover/<block_id>.mp3
  3. Pause insertion mezi bloky (600ms default)

OUTPUT:
  - MP3 soubory v projects/<episode_id>/voiceover/
  - Metadata o vygenerovaných souborech

ULOŽENÍ: 
  - Fyzické MP3: projects/<episode_id>/voiceover/Narrator_0001.mp3
  - Metadata: script_state.json → voiceover_status
```

**❌ PROBLÉM:**
- TTS generace je izolovaná od vizuální planning - není synchronizace

---

### **KROK 6: FOOTAGE DIRECTOR (FDA)** ⚡ **TADY VZNIKAJÍ QUERIES**

**Soubor:** `backend/footage_director.py`  
**Funkce:** `run_fda_llm()`  
**Volající:** `/api/video/footage-director-llm/<episode_id>` endpoint

**Flow:**
```
INPUT:
  - tts_ready_package (obsahuje narration_blocks[])
  - episode_id

TRANSFORMACE:
  1. Extract narration_blocks
  2. Sestaví mega-prompt pro LLM (GPT-4o-mini):
     - Požaduje scene-by-scene shot planning
     - Shot types (enum): historical_battle_footage, maps_context, archival_documents, etc.
  3. LLM vrátí ScenePlan v3 (kreativní JSON)
  4. DETERMINISTICKÁ KOMPILACE do ShotPlan v3:
     - visual_planning_v3.py → compile_scene_plan_to_shot_plan()
     - Generuje search_queries[] deterministicky z narration + entities
     - Generuje keywords[] z narration text

OUTPUT (shot_plan.json):
  {
    "version": "fda_v2.7",
    "episode_topic": "Napoleon in Moscow",
    "scenes": [
      {
        "scene_id": "s_0001",
        "block_id": "b_0001",
        "narration_summary": "Napoleon led Grande Armée into Russia.",
        "narration_summary_original": "...",
        "emotion": "neutral",
        "cut_rhythm": "slow",
        "duration_seconds": 18.5,
        "keywords": ["Napoleon", "Grande Armée", "1812", "Russia"],
        "search_queries": [
          {
            "query": "Napoleon 1812 archival map public domain",
            "reasoning": "Geographic context"
          },
          {
            "query": "Grande Armée historical engraving public domain",
            "reasoning": "Troop movement"
          }
        ],
        "shots": [
          {
            "shot_id": "shot_0001",
            "shot_type": "maps_context",
            "duration_seconds": 8.0,
            "keywords": ["Napoleon", "Russia", "1812"],
            "search_queries": ["Napoleon 1812 Russia map archival"]
          }
        ]
      }
    ]
  }

ULOŽENÍ: script_state.json → metadata.shot_plan
```

**❗ KDE SE GENERUJÍ QUERIES:**

1. **LLM fáze (footage_director.py):**
   - Prompt v `_prompt_footage_director()` (řádek ~2232)
   - LLM dostává narration_blocks a musí vrátit scenes[] s search_queries
   - Format: `{"query": "...", "reasoning": "..."}`

2. **Deterministická kompilace (visual_planning_v3.py):**
   - Funkce `_queries_for_scene()` (řádek 454-513)
   - Generuje queries z:
     - `_scene_anchor_tokens()` → extrahuje entity/year z narration
     - Shot types → ovlivňuje priority (maps_context → map queries first)
     - Base object templates: `["archival", "map"]`, `["historical", "engraving"]`, atd.
   - Garantovaný output: **5 queries per scene**

3. **Query Guardrails (query_guardrails.py):**
   - Funkce `validate_and_fix_queries()` je volána v `visual_planning_v3.py`
   - Validuje queries proti pravidlům (concrete nouns, no verbs, no adjectives)
   - Fixes běžné chyby (treaty → treaty document, capital → city of X)

**❌ PROBLÉM - "NUDA VZNIKÁ TADY":**

✅ **Existuje:**
- Query generation z narration text
- Deterministické template-based queries
- Keyword extraction z narration

❌ **CHYBÍ:**
1. **Žádná kontrola "coverage":**
   - Není tracking "už máme mapu Ruska?" → duplicitní generic queries
   - Není tracking "už máme portrét Napoleona?" → redundance
   - Není balance check (80% maps, 0% people portraits)

2. **Žádný dedupe queries:**
   - Scene 1: "Napoleon 1812 archival map"
   - Scene 2: "Napoleon 1812 archival map" 
   - Scene 3: "Napoleon 1812 archival map"
   - → STEJNÝ query 3x, protože není global memory

3. **Žádný ranker:**
   - Všechny queries jsou considered equal priority
   - Není scoring "které query je strategicky nejdůležitější?"
   - Shot_type enum neurčuje priority beyond template order

4. **Query je generické (málo kontextu scén):**
   - Template `["archival", "map"]` + anchor → "Napoleon 1812 archival map"
   - Nereflektuje scene-specific visual intent:
     - Scene o Battle of Borodino → nespecifikuje "battle", jen "Napoleon 1812"
     - Scene o Moscow fires → nespecifikuje "fire/destruction", jen "Moscow 1812"

**KONKRÉTNÍ PŘÍKLAD NUDY:**

```json
// Scene 1 (b_0001): "Napoleon led Grande Armée into Russia"
{
  "search_queries": [
    "Napoleon 1812 archival map public domain archive",
    "Napoleon 1812 historical engraving public domain archive",
    "Napoleon portrait photograph public domain archive"
  ]
}

// Scene 2 (b_0002): "Battle of Borodino, Russian army withdrew"
{
  "search_queries": [
    "Borodino 1812 archival map public domain archive",    // STEJNÝ typ jako scene 1
    "Borodino 1812 historical engraving public domain archive",
    "Alexander portrait photograph public domain archive"
  ]
}

// Scene 3 (b_0003): "Moscow largely deserted"
{
  "search_queries": [
    "Moscow 1812 archival map public domain archive",       // STEJNÝ typ jako scene 1
    "Moscow 1812 historical engraving public domain archive",
    "Moscow portrait photograph public domain archive"
  ]
}
```

**Důsledek:**
- 80% queries jsou variace na "X 1812 archival map/engraving"
- Žádná diverzita (documents, letters, battle scenes, civilian life)
- Finder vrátí 200 map variants, 0 human stories

---

### **KROK 7: ARCHIVE ASSET RESOLVER (AAR)** ⚡ **TADY SE PROVÁDÍ SEARCH**

**Soubor:** `backend/archive_asset_resolver.py`  
**Funkce:** `resolve_shot_plan_assets()`  
**Volající:** `/api/video/resolve-assets/<episode_id>` endpoint

**Flow:**
```
INPUT:
  - shot_plan (z kroku 6)
  - Multi-source searcher (Archive.org, Wikimedia, Europeana)

TRANSFORMACE:
  1. Extract všechny search_queries z shot_plan.scenes[].search_queries[]
  2. Pro každý query:
     a) Normalize query (_normalize_query_for_archive_search)
        - Remove low-signal tokens ("archive scan", "original print")
        - Convert spoken years ("eighteen twelve" → "1812")
     b) Search multi-source:
        - Archive.org Metadata API
        - Wikimedia Commons API
        - Europeana API (optional)
     c) Filter results:
        - License check (public domain / CC-BY)
        - Mediatype check (image/video only)
        - Quality check (resolution, black frames)
     d) LLM TOPIC RELEVANCE VALIDATION (NEW v14):
        - Volá GPT-4o-mini/Vision
        - Validuje: "Is this about Napoleon 1812?" vs "Is this about Tesla Zimbabwe?"
        - Rejects off-topic contamination
     e) Dedupe by visual similarity (optional)
  3. Rank results per query:
     - Relevance score (metadata match)
     - Quality score (resolution, completeness)
     - License priority (public domain > CC-BY > CC-BY-SA)
  4. Select top N assets per scene:
     - Scene duration ÷ asset duration = required count
     - Fallback: global queries if scene has insufficient assets
  5. Generate recommended_subclips[] per asset:
     - Start/end timestamps
     - Duration hints

OUTPUT (archive_manifest.json):
  {
    "version": "aar_v14",
    "episode_id": "ep_024286848837",
    "episode_topic": "Napoleon in Moscow",
    "cache_version": "v14_topic_relevance",
    "global_queries": [
      "Napoleon 1812 Russia campaign historical",
      "French invasion Russia 1812 archival"
    ],
    "scenes": [
      {
        "scene_id": "s_0001",
        "block_id": "b_0001",
        "assets": [
          {
            "asset_id": "asset_0001",
            "archive_item_id": "archive_org:LaLiberationdeParis1944",
            "title": "Napoleon Campaign Map 1812",
            "description": "...",
            "url": "https://archive.org/download/...",
            "thumbnail_url": "...",
            "duration_seconds": 120.5,
            "license": "Public Domain",
            "mediatype": "movies",
            "format": "MPEG4",
            "query_used": "Napoleon 1812 archival map",
            "relevance_score": 0.85,
            "recommended_subclips": [
              {"start": 10.0, "end": 18.0, "duration": 8.0, "reason": "Map overview"}
            ]
          }
        ]
      }
    ],
    "diagnostics": {
      "total_queries": 15,
      "successful_searches": 14,
      "failed_searches": 1,
      "total_assets_found": 127,
      "scenes_with_assets": 7,
      "scenes_without_assets": 0
    }
  }

ULOŽENÍ:
  - JSON: projects/<episode_id>/archive_manifest.json
  - Cache: projects/<episode_id>/archive_cache/*.json (per-query cache)
```

**KDE SE PROVÁDÍ SEARCH:**

1. **Multi-source search (video_sources.py):**
   - `MultiSourceVideoSearcher.search(query, max_results=50)`
   - Paralelní search napříč sources:
     - Archive.org: `https://archive.org/advancedsearch.php`
     - Wikimedia: `https://commons.wikimedia.org/w/api.php`
     - Europeana: `https://api.europeana.eu/record/v2/search.json`

2. **Search parameters:**
   - Max results per query: 50 (default)
   - Timeout: 30s per source
   - Retry: 3 attempts with exponential backoff

3. **Ranking logic (`_rank_and_select_candidates`):**
   ```python
   score = (
       relevance_weight * relevance_score +    # 0.4 - metadata match to query
       quality_weight * quality_score +        # 0.3 - resolution/completeness
       license_weight * license_score          # 0.3 - license priority
   )
   ```

**❌ PROBLÉM - "NUDA VZNIKÁ TADY":**

✅ **Existuje:**
- Multi-source search (3+ providers)
- License filtering (public domain only)
- Topic relevance validation (LLM-based, v14)
- Quality checks (black frames, resolution)

❌ **CHYBÍ:**

1. **Žádný dedupe PŘED search:**
   - AAR dostává 35 queries, z toho 15 jsou duplicitní
   - Každý duplicitní query = zbytečný API call + processing time
   - Není pre-search dedupe na query level

2. **Žádný "coverage" tracker:**
   - AAR nemá představu "episode balance"
   - Nepočítá: "už mám 20 map, 2 portréty, 0 dokumentů"
   - Nepoužívá coverage data k prioritizaci queries

3. **Žádný visual dedupe CROSS-SCENE:**
   - Scene 1 najde map variant A
   - Scene 3 najde map variant A (same item, different query)
   - → Duplikát v manifestu, protože není global asset registry

4. **Ranking je per-query izolovaný:**
   - Top 5 pro query "Napoleon map" vs top 5 pro query "Moscow map"
   - Není global ranking "best 50 assets for whole episode"
   - Není strategická selekce (balance coverage priorities)

**KONKRÉTNÍ PŘÍKLAD NUDY:**

```json
// AAR výsledek pro episode "Napoleon in Moscow"
{
  "scenes": [
    {
      "scene_id": "s_0001",  // "Napoleon led Grande Armée"
      "assets": [
        {"title": "Russia Map 1812", "query_used": "Napoleon 1812 map"},
        {"title": "Europe Map 1812", "query_used": "Napoleon 1812 map"},
        {"title": "Campaign Map Variant", "query_used": "Grande Armée map"}
      ]
    },
    {
      "scene_id": "s_0002",  // "Battle of Borodino"
      "assets": [
        {"title": "Russia Map 1812", "query_used": "Borodino 1812 map"},      // DUPLICIT!
        {"title": "Battle Map Generic", "query_used": "Borodino map"}
      ]
    },
    {
      "scene_id": "s_0003",  // "Moscow deserted"
      "assets": [
        {"title": "Russia Map 1812", "query_used": "Moscow 1812 map"},        // DUPLICIT!
        {"title": "City Map Generic", "query_used": "Moscow map"}
      ]
    }
  ]
}
```

**Důsledek:**
- 8/10 assets jsou map varianty (80% redundance)
- Není visual diverzity (portraits, documents, battle scenes)
- Viewer fatigue: "další mapa zase?"

---

### **KROK 8: COMPILATION BUILDER (CB)** 

**Soubor:** `backend/compilation_builder.py`  
**Funkce:** `build_episode_compilation()`  
**Volající:** `/api/video/compile/<episode_id>` endpoint

**Flow:**
```
INPUT:
  - archive_manifest.json (z kroku 7)
  - Voiceover MP3 files (z kroku 5)

TRANSFORMACE:
  1. Download assets z URLs v manifestu:
     - Cache check (už staženo?)
     - Download s retry (exponential backoff)
     - Save to projects/<episode_id>/archive_cache/
  2. Extract subclips podle recommended_subclips[]:
     - FFmpeg extract: -ss <start> -to <end>
     - Save to temp/subclip_*.mp4
  3. Video stream validation (has_video_stream check):
     - Ffprobe verification each clip has visual content
     - Reject black screen clips
  4. Timeline assembly:
     - Combine subclips podle scene order
     - Sync with voiceover MP3s (audio timeline)
     - Add transitions (optional)
  5. Final render:
     - FFmpeg concat protocol
     - Audio normalization
     - Export to output/final_<episode_id>.mp4

OUTPUT:
  - Final video: output/final_ep_024286848837.mp4
  - Metadata: compilation_report.json

ULOŽENÍ:
  - Video: output/final_*.mp4
  - Report: projects/<episode_id>/compilation_report.json
```

**❌ PROBLÉM:**
- CB je "dumb executor" - pouze sestavuje to, co dostane
- Žádná inteligence o visual flow/pacing
- Není fallback logika pokud asset sucks (black frames, wrong content)

---

## 📦 2) KONTRAKTY / ARTEFAKTY CO SE POUŽÍVAJÍ

### **Klíčové JSON Artifacts v Pipeline**

| Artifact | Generátor | Čtená kým | Schema keys | Lokace |
|----------|-----------|-----------|-------------|--------|
| **research_report.json** | Research Assistant (LLM) | Narrative, Validator, Composer | `topic, language, timeline[], claims[], entities[]` | `script_state.json → metadata.research_report` |
| **draft_script.json** | Narrative Assistant (LLM) | Validator, Composer | `title_candidates[], hook, chapters[], narration_blocks[]` | `script_state.json → metadata.draft_script` |
| **validation_result.json** | Validator Assistant (LLM) | Composer | `status, issues[], approved_script` | `script_state.json → metadata.validation_result` |
| **tts_ready_package.json** | Composer (deterministic) | TTS Generator, FDA | `episode_id, language, selected_title, narration_blocks[], chapters[]` | `script_state.json → metadata.tts_ready_package` |
| **shot_plan.json** | FDA (LLM + deterministic) | AAR, CB | `version, episode_topic, scenes[].search_queries[], shots[]` | `script_state.json → metadata.shot_plan` |
| **archive_manifest.json** | AAR (search + LLM validation) | CB | `episode_id, scenes[].assets[], diagnostics` | `projects/<episode_id>/archive_manifest.json` |
| **compilation_report.json** | CB (FFmpeg) | User/Analytics | `video_path, duration, scenes[], errors[]` | `projects/<episode_id>/compilation_report.json` |

---

### **KONTRAKT 1: research_report.json**

**Generuje:** Research Assistant (LLM) v `script_pipeline.py::_step_research()`  
**Čte:** Narrative Assistant, Validator, Composer  
**Schema:**

```json
{
  "topic": "string - hlavní téma epizody",
  "language": "string - ISO code (en, cs)",
  "timeline": [
    {
      "period": "string - časové období",
      "event": "string - událost"
    }
  ],
  "claims": [
    {
      "claim_id": "string - unique ID (c_001, c_002...)",
      "text": "string - verifiable fact",
      "importance": "string - high|medium|low"
    }
  ],
  "entities": [
    {
      "name": "string - entity name",
      "type": "string - person|place|organization|event|other"
    }
  ],
  "open_questions": ["string - research gaps (optional)"]
}
```

**Zásadní klíče:**
- `claims[]` - backbone faktografické integrity
- `entities[]` - použito pro anchor extraction v FDA
- `timeline[]` - chronologický kontext (není využito v AAR!)

**Kde se zapisuje:** `projects/<episode_id>/script_state.json` → `metadata.research_report`  
**Kde se čte:** Narrative prompt, Validator cross-check, Composer integrity check

---

### **KONTRAKT 2: tts_ready_package.json**

**Generuje:** Composer (deterministic) v `script_pipeline.py::_deterministic_compose()`  
**Čte:** TTS Generator, FDA  
**Schema:**

```json
{
  "episode_id": "string - ep_XXXXX",
  "language": "string - en|cs",
  "selected_title": "string - chosen title",
  "fact_validation_status": "string - PASS|FAIL",
  "chapters": [
    {
      "chapter_id": "string - ch_01",
      "title": "string - chapter title",
      "narration_blocks": [
        {
          "block_id": "string - b_0001",
          "claim_ids": ["string - reference to research claims"],
          "text_tts": "string - TTS-ready narration text"
        }
      ]
    }
  ],
  "narration_blocks": [
    {
      "block_id": "string - b_0001",
      "claim_ids": ["string"],
      "text_tts": "string"
    }
  ],
  "tts_guidelines": {
    "voice_style": "string - documentary_narrator",
    "pace_wpm_hint": "int - 150-180",
    "pause_style": "string - punctuation"
  },
  "metadata": {
    "target_minutes": "int - optional",
    "channel_profile": "string - optional"
  }
}
```

**Zásadní klíče:**
- `narration_blocks[]` - flat list for TTS (přes všechny kapitoly)
- `block_id` - unique identifier for sync (TTS → FDA → AAR → CB)
- `text_tts` - finální narration text (post-validation)

**Kde se zapisuje:** `script_state.json → metadata.tts_ready_package`  
**Kde se čte:**
- TTS Generator: extract `narration_blocks[].text_tts` → generate MP3s
- FDA: input pro scene-by-scene shot planning

---

### **KONTRAKT 3: shot_plan.json** ⚡ **ZÁSADNÍ PRO VISUAL PIPELINE**

**Generuje:** FDA (LLM + visual_planning_v3 deterministic compiler)  
**Čte:** AAR, CB  
**Schema:**

```json
{
  "version": "string - fda_v2.7",
  "episode_topic": "string - Napoleon in Moscow",
  "scenes": [
    {
      "scene_id": "string - s_0001",
      "block_id": "string - b_0001 (ref to narration_blocks)",
      "narration_summary": "string - short summary (deterministic first sentence)",
      "narration_summary_original": "string - full text_tts",
      "emotion": "string - neutral|tension|tragedy|hope|victory|mystery",
      "cut_rhythm": "string - slow|medium|fast",
      "duration_seconds": "float - estimated speech duration",
      "keywords": ["string - extracted entities/nouns"],
      "search_queries": [
        {
          "query": "string - search query for AAR",
          "reasoning": "string - why this query"
        }
      ],
      "shots": [
        {
          "shot_id": "string - shot_0001",
          "shot_type": "string - historical_battle_footage|maps_context|archival_documents|...",
          "duration_seconds": "float",
          "keywords": ["string"],
          "search_queries": ["string - shot-level queries"]
        }
      ]
    }
  ]
}
```

**Zásadní klíče:**
- `scenes[].search_queries[]` - **PRIMARY INPUT pro AAR search**
- `scenes[].keywords[]` - fallback anchors pro query refinement
- `shots[].shot_type` - enum určující visual intent (battle, map, document...)

**Kde se zapisuje:** `script_state.json → metadata.shot_plan`  
**Kde se čte:**
- AAR: extract all `scenes[].search_queries[].query` → search archives
- CB: timeline assembly podle `scenes[]` order

---

### **KONTRAKT 4: archive_manifest.json** ⚡ **OUTPUT AAR**

**Generuje:** AAR v `archive_asset_resolver.py::resolve_shot_plan_assets()`  
**Čte:** CB  
**Schema:**

```json
{
  "version": "string - aar_v14",
  "episode_id": "string",
  "episode_topic": "string",
  "cache_version": "string - v14_topic_relevance",
  "global_queries": ["string - fallback queries"],
  "scenes": [
    {
      "scene_id": "string - s_0001",
      "block_id": "string - b_0001",
      "assets": [
        {
          "asset_id": "string - asset_0001",
          "archive_item_id": "string - archive_org:XXXXX or wikimedia:XXXXX",
          "title": "string",
          "description": "string",
          "url": "string - download URL",
          "thumbnail_url": "string",
          "duration_seconds": "float",
          "license": "string - Public Domain|CC-BY|CC-BY-SA",
          "mediatype": "string - movies|images",
          "format": "string - MPEG4|JPEG",
          "query_used": "string - which query found this",
          "relevance_score": "float - 0.0-1.0",
          "recommended_subclips": [
            {
              "start": "float - seconds",
              "end": "float - seconds",
              "duration": "float",
              "reason": "string - why this subclip"
            }
          ]
        }
      ]
    }
  ],
  "diagnostics": {
    "total_queries": "int",
    "successful_searches": "int",
    "failed_searches": "int",
    "total_assets_found": "int",
    "scenes_with_assets": "int",
    "scenes_without_assets": "int"
  }
}
```

**Zásadní klíče:**
- `scenes[].assets[]` - konkrétní archive items per scene
- `assets[].recommended_subclips[]` - časové rozsahy pro CB extract
- `diagnostics` - health check (kolik queries failed, kolik scén bez assets)

**Kde se zapisuje:** `projects/<episode_id>/archive_manifest.json`  
**Kde se čte:** CB → download URLs, extract subclips

---

## ❌ 3) NAJDI PŘESNĚ "KDE DNES VZNIKÁ NUDA"

### **Systematická analýza nuda-bodů:**

| # | Component | Chybí | Proto se děje |
|---|-----------|-------|---------------|
| 1 | **Research Assistant** | Není coverage tracking (map/people/documents/places) | Research vrací flat list entities bez typologie → FDA nemá guidance co prioritize |
| 2 | **FDA Query Generation** | Není dedupe queries | Stejný query ("Napoleon 1812 map") se generuje 10x pro různé scény → redundantní search |
| 3 | **FDA Query Generation** | Není coverage balance check | Template-based queries generují 80% map variants, 0% human portraits/documents |
| 4 | **FDA Query Generation** | Generické queries (málo scene-specific context) | "Napoleon 1812 map" místo "Napoleon 1812 Moscow occupation civilian evacuation" → generic results |
| 5 | **AAR Search** | Není pre-search dedupe | AAR dostává 35 queries, z toho 15 duplicitních → zbytečné API calls |
| 6 | **AAR Ranking** | Per-query ranking (not global) | Top 5 for "map" + top 5 for "engraving" bez global "best 50 for episode" → local optima |
| 7 | **AAR Asset Selection** | Není cross-scene visual dedupe | Scene 1 a Scene 3 dostanou same asset (different query) → duplicate visuals in final video |
| 8 | **AAR Asset Selection** | Není coverage tracker (episode-level) | Není "už mám 20 map, 2 portraits, 0 documents" awareness → unbalanced manifest |
| 9 | **CB Assembly** | "Dumb executor" bez visual flow intelligence | Sestaví co dostane, i kdyby to bylo 10 map variants in row → viewer fatigue |

---

### **KONKRÉTNÍ BODY: "CHYBÍ X, PROTO SE DĚJE Y"**

#### **1. CHYBÍ: Coverage Typing in Research**

**Kde:** `script_pipeline.py::_step_research()`  
**Co chybí:** Research entities nemají typologie pro visual needs

```json
// SOUČASNÝ OUTPUT:
{
  "entities": [
    {"name": "Napoleon", "type": "person"},
    {"name": "Moscow", "type": "place"},
    {"name": "Grande Armée", "type": "organization"}
  ]
}

// MĚLO BY BÝT (pro FDA guidance):
{
  "entities": [
    {"name": "Napoleon", "type": "person", "visual_need": "portrait|battle_scene"},
    {"name": "Moscow", "type": "place", "visual_need": "map|cityscape|documents"},
    {"name": "Grande Armée", "type": "organization", "visual_need": "troop_movement|engraving"}
  ],
  "visual_coverage_requirements": {
    "maps": 3,          // need 3 unique maps
    "portraits": 2,     // need 2 portraits (Napoleon, Alexander)
    "documents": 2,     // need 2 documents (treaty, letters)
    "battle_scenes": 1,
    "civilian_life": 1
  }
}
```

**Proto se děje:** FDA nemá guidance → generuje template-based queries bez balance awareness

---

#### **2. CHYBÍ: Query Dedupe in FDA**

**Kde:** `footage_director.py::run_fda_llm()` + `visual_planning_v3.py::_queries_for_scene()`  
**Co chybí:** Global query registry před emission

```python
# SOUČASNÝ KÓD (visual_planning_v3.py, line 454-513):
def _queries_for_scene(text, focus_entities, shot_types):
    # Generuje 5 queries per scene
    # ŽÁDNÝ CHECK jestli query už byl použit v previous scénách
    return queries  # může obsahovat duplicity cross-scene

# MĚLO BY BÝT:
_global_query_registry = set()  # tracks už použité queries

def _queries_for_scene_dedupe(text, focus_entities, shot_types, used_queries):
    candidates = _generate_query_candidates(text, focus_entities, shot_types, count=10)
    
    # Dedupe against already used queries
    unique = []
    for q in candidates:
        if q not in used_queries:
            unique.append(q)
            used_queries.add(q)
        if len(unique) >= 5:
            break
    
    # Fallback: pokud není 5 unique, generate alternates
    while len(unique) < 5:
        alternate = _generate_alternate_query(text, focus_entities, avoid=used_queries)
        unique.append(alternate)
        used_queries.add(alternate)
    
    return unique
```

**Proto se děje:** Duplicitní queries → redundantní API calls v AAR → same results 3x

---

#### **3. CHYBÍ: Coverage Balance Check in FDA**

**Kde:** `visual_planning_v3.py::compile_scene_plan_to_shot_plan()`  
**Co chybí:** Episode-level coverage tracker pro query generation

```python
# MĚLO BY BÝT:
class EpisodeCoverageTracker:
    def __init__(self, target_coverage):
        self.target = target_coverage  # {"maps": 3, "portraits": 2, "documents": 2}
        self.current = {"maps": 0, "portraits": 0, "documents": 0}
    
    def needs_more(self, visual_type):
        return self.current.get(visual_type, 0) < self.target.get(visual_type, 0)
    
    def increment(self, visual_type):
        self.current[visual_type] = self.current.get(visual_type, 0) + 1
    
    def get_priority_types(self):
        # Vrátí typy sorted by deficit
        deficit = []
        for vtype, target_count in self.target.items():
            current_count = self.current.get(vtype, 0)
            if current_count < target_count:
                deficit.append((vtype, target_count - current_count))
        return sorted(deficit, key=lambda x: x[1], reverse=True)

# Použití při query generation:
def _queries_for_scene_with_coverage(text, entities, shot_types, coverage_tracker):
    priority_types = coverage_tracker.get_priority_types()
    
    # Generate queries PRIORITIZING deficitní types
    queries = []
    for visual_type, deficit in priority_types:
        if deficit > 0:
            query = _generate_typed_query(text, entities, visual_type)
            queries.append(query)
            coverage_tracker.increment(visual_type)
    
    return queries
```

**Proto se děje:** Template-based queries ignorují episode balance → 80% maps, 0% diversity

---

#### **4. CHYBÍ: Scene-Specific Context in Queries**

**Kde:** `visual_planning_v3.py::_queries_for_scene()` line 492-506  
**Co chybí:** Query context beyond entity + year

```python
# SOUČASNÝ KÓD:
# Template: ["archival", "map"] + entity + year → "Napoleon 1812 archival map"

# MĚLO BY BÝT (inject scene intent):
def _build_contextual_query(text, entity, year, visual_type, shot_type):
    """
    Build query with scene-specific context, not just template.
    """
    # Extract action/event from narration
    action_keywords = extract_action_context(text)  
    # e.g., "Battle of Borodino" → action: "battle"
    # e.g., "Moscow fires broke out" → action: "fire", "destruction"
    
    if visual_type == "map":
        if "battle" in action_keywords:
            return f"{entity} {year} battle map tactical"
        elif "retreat" in action_keywords:
            return f"{entity} {year} retreat route map"
        else:
            return f"{entity} {year} campaign map"
    
    elif visual_type == "engraving":
        if "battle" in action_keywords:
            return f"{entity} {year} battle scene engraving"
        elif "civilian" in action_keywords:
            return f"{entity} {year} civilian life engraving"
        else:
            return f"{entity} {year} historical engraving"

# EXAMPLE OUTPUT:
# Scene "Battle of Borodino" → "Napoleon 1812 battle map tactical"
# Scene "Moscow fires" → "Moscow 1812 fire destruction aftermath"
# místo generic "Napoleon 1812 archival map" 10x
```

**Proto se děje:** Generic queries → generic results → nuda

---

#### **5. CHYBÍ: Pre-Search Dedupe in AAR**

**Kde:** `archive_asset_resolver.py::resolve_shot_plan_assets()`  
**Co chybí:** Query normalization + dedupe před multi-source search

```python
# SOUČASNÝ KÓD:
# Pro každý scene.search_queries[]: search immediately (no global dedupe)

# MĚLO BY BÝT:
def resolve_shot_plan_assets_with_dedupe(shot_plan, ...):
    # 1. Extract ALL queries from all scenes
    all_queries = []
    for scene in shot_plan["scenes"]:
        for sq in scene.get("search_queries", []):
            all_queries.append({
                "query": sq["query"],
                "scene_id": scene["scene_id"],
                "reasoning": sq.get("reasoning", "")
            })
    
    # 2. Normalize + dedupe queries
    unique_queries = {}
    for q in all_queries:
        normalized = normalize_query(q["query"])
        if normalized not in unique_queries:
            unique_queries[normalized] = {
                "query": q["query"],
                "scene_ids": [q["scene_id"]],
                "reasoning": q["reasoning"]
            }
        else:
            # Merge scene_ids for shared query
            unique_queries[normalized]["scene_ids"].append(q["scene_id"])
    
    print(f"Dedupe: {len(all_queries)} queries → {len(unique_queries)} unique")
    
    # 3. Search ONLY unique queries
    search_results = {}
    for norm_q, meta in unique_queries.items():
        results = multi_source_search(meta["query"])
        search_results[norm_q] = results
    
    # 4. Distribute results zpět do scén
    for scene in shot_plan["scenes"]:
        scene_assets = []
        for sq in scene.get("search_queries", []):
            norm = normalize_query(sq["query"])
            if norm in search_results:
                scene_assets.extend(search_results[norm])
        # Dedupe assets per scene (by archive_item_id)
        scene["assets"] = dedupe_assets_by_id(scene_assets)
```

**Proto se děje:** 35 queries → 15 duplicitních → waste API calls + processing time

---

#### **6. CHYBÍ: Global Ranking (Not Per-Query)**

**Kde:** `archive_asset_resolver.py::_rank_and_select_candidates()`  
**Co chybí:** Episode-level ranking across all found assets

```python
# SOUČASNÝ KÓD:
# Per-query ranking: top 5 for each query independently

# MĚLO BY BÝT:
def global_ranking_for_episode(all_assets, episode_context, coverage_tracker):
    """
    Rank ALL assets found across all queries, then select strategically.
    
    Scoring factors:
    - Relevance to episode topic (LLM score)
    - Quality (resolution, completeness)
    - Coverage priority (balance types)
    - Visual uniqueness (avoid similar assets)
    """
    scored_assets = []
    for asset in all_assets:
        score = (
            asset["relevance_score"] * 0.3 +
            asset["quality_score"] * 0.2 +
            coverage_priority_score(asset, coverage_tracker) * 0.3 +
            uniqueness_score(asset, scored_assets) * 0.2
        )
        scored_assets.append({**asset, "global_score": score})
    
    # Sort by global score
    ranked = sorted(scored_assets, key=lambda x: x["global_score"], reverse=True)
    
    # Select top N ensuring coverage balance
    selected = []
    for asset in ranked:
        if len(selected) >= target_count:
            break
        # Check coverage balance
        asset_type = infer_visual_type(asset)
        if coverage_tracker.can_add(asset_type):
            selected.append(asset)
            coverage_tracker.increment(asset_type)
    
    return selected

def coverage_priority_score(asset, coverage_tracker):
    """
    Higher score if asset type is under-represented.
    """
    asset_type = infer_visual_type(asset)
    deficit = coverage_tracker.deficit(asset_type)
    return min(1.0, deficit / 3.0)  # normalize 0-1
```

**Proto se děje:** Local optima per query → unbalanced final selection

---

#### **7. CHYBÍ: Cross-Scene Visual Dedupe**

**Kde:** `archive_asset_resolver.py::resolve_shot_plan_assets()`  
**Co chybí:** Global asset registry to prevent duplicates across scenes

```python
# SOUČASNÝ KÓD:
# Scene 1 gets assets independently
# Scene 2 gets assets independently
# → Same asset can appear in both (different queries)

# MĚLO BY BÝT:
_global_asset_registry = {}  # {archive_item_id: [scene_ids]}

def assign_assets_to_scenes_with_dedupe(scenes, all_ranked_assets):
    """
    Assign assets to scenes while preventing cross-scene duplicates.
    """
    for scene in scenes:
        scene_assets = []
        needed_duration = scene["duration_seconds"]
        covered_duration = 0
        
        for asset in all_ranked_assets:
            aid = asset["archive_item_id"]
            
            # Skip if already used in another scene
            if aid in _global_asset_registry:
                continue
            
            # Check if asset matches scene context
            if matches_scene(asset, scene):
                scene_assets.append(asset)
                _global_asset_registry[aid] = scene["scene_id"]
                covered_duration += asset["duration_seconds"]
                
                if covered_duration >= needed_duration:
                    break
        
        scene["assets"] = scene_assets
```

**Proto se děje:** Same asset in multiple scenes → visual repetition → nuda

---

#### **8. CHYBÍ: Episode-Level Coverage Tracker in AAR**

**Kde:** `archive_asset_resolver.py::resolve_shot_plan_assets()`  
**Co chybí:** Awareness of episode balance during asset selection

```python
# MĚLO BY BÝT:
class AAR_CoverageTracker:
    def __init__(self, target_coverage):
        self.target = target_coverage  # from Research/FDA
        self.current = {vtype: 0 for vtype in target_coverage.keys()}
        self.assigned_assets = []
    
    def infer_type(self, asset):
        """Classify asset into visual type (map/portrait/document/...)"""
        title_lower = asset["title"].lower()
        desc_lower = asset["description"].lower()
        
        if "map" in title_lower or "carte" in desc_lower:
            return "maps"
        elif "portrait" in title_lower or "photograph" in desc_lower:
            return "portraits"
        elif "document" in title_lower or "letter" in desc_lower:
            return "documents"
        elif "battle" in title_lower or "combat" in desc_lower:
            return "battle_scenes"
        else:
            return "other"
    
    def can_add(self, visual_type):
        """Check if we still need more of this type"""
        current = self.current.get(visual_type, 0)
        target = self.target.get(visual_type, float('inf'))
        return current < target
    
    def add_asset(self, asset):
        vtype = self.infer_type(asset)
        self.current[vtype] = self.current.get(vtype, 0) + 1
        self.assigned_assets.append(asset)
    
    def get_balance_report(self):
        return {
            vtype: {
                "target": self.target.get(vtype, 0),
                "current": self.current.get(vtype, 0),
                "deficit": self.target.get(vtype, 0) - self.current.get(vtype, 0)
            }
            for vtype in self.target.keys()
        }

# Usage during asset selection:
coverage = AAR_CoverageTracker(episode_coverage_requirements)
for asset in ranked_assets:
    vtype = coverage.infer_type(asset)
    if coverage.can_add(vtype):
        assign_to_scene(asset, scene)
        coverage.add_asset(asset)

print(f"Coverage balance: {coverage.get_balance_report()}")
```

**Proto se děje:** Není tracking → 80% maps, 0% portraits → nuda

---

## 🔧 4) INTEGRAČNÍ BOD PRO 2 AI ASISTENTY

### **Návrh: Query Director + Visual Curator**

---

### **AI ASISTENT #1: QUERY DIRECTOR** 
**⚡ Zapojení: PŘED scrapers (mezi FDA a AAR)**

#### **ROLE:**
Transformuje raw FDA queries → strategické, coverage-aware queries

#### **VSTUP (co dostane):**

```json
{
  "episode_context": {
    "episode_id": "ep_024286848837",
    "episode_topic": "Napoleon in Moscow: The 1812 Occupation",
    "target_duration_minutes": 8,
    "research_entities": [
      {"name": "Napoleon", "type": "person"},
      {"name": "Moscow", "type": "place"},
      {"name": "Grande Armée", "type": "organization"}
    ]
  },
  "coverage_requirements": {
    "maps": 3,
    "portraits": 2,
    "documents": 2,
    "battle_scenes": 1,
    "civilian_life": 1
  },
  "raw_queries_by_scene": [
    {
      "scene_id": "s_0001",
      "block_id": "b_0001",
      "narration_summary": "Napoleon led Grande Armée into Russia...",
      "fda_queries": [
        "Napoleon 1812 archival map public domain",
        "Grande Armée historical engraving public domain"
      ]
    },
    {
      "scene_id": "s_0002",
      "block_id": "b_0002",
      "narration_summary": "Battle of Borodino, Russian army withdrew...",
      "fda_queries": [
        "Borodino 1812 archival map public domain",
        "Alexander portrait public domain"
      ]
    }
  ]
}
```

#### **VÝSTUP (co musí vrátit):**

```json
{
  "query_director_version": "v1.0",
  "episode_id": "ep_024286848837",
  "strategic_queries": [
    {
      "query_id": "qd_001",
      "query": "Napoleon Bonaparte 1812 portrait official Louvre",
      "priority": "critical",
      "visual_type": "portraits",
      "reasoning": "Episode needs Napoleon portrait - highest priority",
      "intended_scenes": ["s_0001", "s_0005"],
      "estimated_results": 50
    },
    {
      "query_id": "qd_002",
      "query": "Grande Armée 1812 Russia invasion campaign map tactical",
      "priority": "high",
      "visual_type": "maps",
      "reasoning": "Primary geographic context for invasion narrative",
      "intended_scenes": ["s_0001", "s_0002"],
      "estimated_results": 30
    },
    {
      "query_id": "qd_003",
      "query": "Tsar Alexander I Russia 1812 portrait official",
      "priority": "high",
      "visual_type": "portraits",
      "reasoning": "Main antagonist - needed for diplomatic context",
      "intended_scenes": ["s_0004", "s_0006"],
      "estimated_results": 40
    },
    {
      "query_id": "qd_004",
      "query": "Moscow 1812 fire destruction aftermath engraving",
      "priority": "medium",
      "visual_type": "battle_scenes",
      "reasoning": "Scene-specific: Moscow fires chapter needs destruction visuals",
      "intended_scenes": ["s_0003"],
      "estimated_results": 25
    },
    {
      "query_id": "qd_005",
      "query": "French Russian treaty document 1807 Tilsit handwritten",
      "priority": "medium",
      "visual_type": "documents",
      "reasoning": "Coverage balance: need document visuals for variety",
      "intended_scenes": ["s_0001"],
      "estimated_results": 15
    }
  ],
  "dedupe_report": {
    "input_queries_count": 14,
    "deduplicated_queries_count": 9,
    "strategic_queries_count": 5,
    "coverage_balanced": true
  },
  "coverage_plan": {
    "maps": {"target": 3, "queries": 1},
    "portraits": {"target": 2, "queries": 2},
    "documents": {"target": 2, "queries": 1},
    "battle_scenes": {"target": 1, "queries": 1},
    "civilian_life": {"target": 1, "queries": 0}
  }
}
```

#### **DO JAKÉHO ARTEFAKTU SE ULOŽÍ:**

**Nový artefakt:** `projects/<episode_id>/query_director_output.json`

Struktura:
```json
{
  "version": "qd_v1.0",
  "generated_at": "2025-01-05T12:00:00Z",
  "episode_id": "ep_024286848837",
  "strategic_queries": [...],
  "coverage_plan": {...},
  "metadata": {
    "input_source": "fda_v2.7_shot_plan",
    "llm_provider": "openrouter",
    "llm_model": "anthropic/claude-3.5-sonnet",
    "processing_time_seconds": 15.3
  }
}
```

**Integrační flow:**
```
FDA → shot_plan.json
  ↓
Query Director (NEW!) → query_director_output.json
  ↓
AAR (modified to read query_director_output.json instead of shot_plan queries)
```

---

### **AI ASISTENT #2: VISUAL CURATOR**
**⚡ Zapojení: PO fetchi, PŘED shotplanem (mezi AAR search results a manifest finalization)**

#### **ROLE:**
Rank, dedupe, select nejlepší assets z raw search results

#### **VSTUP (co dostane):**

```json
{
  "episode_context": {
    "episode_id": "ep_024286848837",
    "episode_topic": "Napoleon in Moscow: The 1812 Occupation",
    "total_duration_seconds": 480,
    "coverage_requirements": {
      "maps": 3,
      "portraits": 2,
      "documents": 2,
      "battle_scenes": 1
    }
  },
  "raw_search_results": [
    {
      "query_id": "qd_001",
      "query": "Napoleon Bonaparte 1812 portrait",
      "results_count": 50,
      "results": [
        {
          "asset_id": "aar_raw_001",
          "archive_item_id": "archive_org:NapoleonPortrait1812",
          "title": "Napoleon Bonaparte - Official Portrait 1812",
          "description": "Oil painting by Jacques-Louis David...",
          "url": "https://archive.org/download/...",
          "thumbnail_url": "https://archive.org/services/img/...",
          "duration_seconds": 0,  // image
          "license": "Public Domain",
          "mediatype": "image",
          "format": "JPEG",
          "resolution": "3000x4000",
          "file_size_mb": 2.5,
          "query_used": "Napoleon Bonaparte 1812 portrait"
        }
        // ... 49 more results
      ]
    },
    {
      "query_id": "qd_002",
      "query": "Grande Armée 1812 Russia campaign map",
      "results_count": 30,
      "results": [...]
    }
    // ... more query results
  ],
  "scenes": [
    {
      "scene_id": "s_0001",
      "block_id": "b_0001",
      "narration_summary": "Napoleon led Grande Armée into Russia...",
      "duration_seconds": 18.5,
      "emotion": "neutral",
      "intended_visual_types": ["maps", "portraits"]
    }
  ]
}
```

#### **VÝSTUP (co musí vrátit):**

```json
{
  "visual_curator_version": "v1.0",
  "episode_id": "ep_024286848837",
  "curated_assets": [
    {
      "asset_id": "curated_001",
      "archive_item_id": "archive_org:NapoleonPortrait1812",
      "title": "Napoleon Bonaparte - Official Portrait 1812",
      "description": "Oil painting by Jacques-Louis David...",
      "url": "https://archive.org/download/...",
      "thumbnail_url": "...",
      "duration_seconds": 0,
      "license": "Public Domain",
      "mediatype": "image",
      "visual_type": "portraits",  // CLASSIFIED by Curator
      "global_rank": 1,
      "global_score": 0.95,
      "quality_assessment": {
        "resolution": "excellent",
        "composition": "professional",
        "relevance": "perfect",
        "uniqueness": "high"
      },
      "curator_reasoning": "Primary portrait of Napoleon - highest quality, official, perfectly matches episode topic",
      "recommended_scenes": ["s_0001", "s_0005"],
      "recommended_subclips": [
        {
          "start": 0,
          "duration": 8.0,
          "zoom_level": "medium_closeup",
          "reason": "Focus on Napoleon's face for intro"
        }
      ]
    },
    {
      "asset_id": "curated_002",
      "archive_item_id": "archive_org:RussiaCampaignMap1812",
      "title": "Grande Armée Russia Invasion Campaign Map 1812",
      "visual_type": "maps",
      "global_rank": 2,
      "global_score": 0.92,
      "quality_assessment": {
        "resolution": "excellent",
        "composition": "clear",
        "relevance": "excellent",
        "uniqueness": "high"
      },
      "curator_reasoning": "Primary geographic context - shows full invasion route, high quality scan",
      "recommended_scenes": ["s_0001", "s_0002"],
      "recommended_subclips": [...]
    }
    // ... top 15-20 curated assets (z 200+ raw results)
  ],
  "dedupe_report": {
    "input_assets_count": 237,
    "duplicates_removed": 52,
    "low_quality_rejected": 31,
    "off_topic_rejected": 18,
    "curated_assets_count": 20
  },
  "coverage_balance": {
    "maps": {"target": 3, "selected": 3, "status": "met"},
    "portraits": {"target": 2, "selected": 2, "status": "met"},
    "documents": {"target": 2, "selected": 2, "status": "met"},
    "battle_scenes": {"target": 1, "selected": 1, "status": "met"},
    "civilian_life": {"target": 1, "selected": 0, "status": "deficit"}
  },
  "quality_metrics": {
    "average_global_score": 0.87,
    "resolution_excellent_pct": 75,
    "relevance_excellent_pct": 85
  }
}
```

#### **DO JAKÉHO ARTEFAKTU SE ULOŽÍ:**

**Modifikace existujícího:** `projects/<episode_id>/archive_manifest.json`

Přidá sekce:
```json
{
  "version": "aar_v15_with_curator",
  "episode_id": "ep_024286848837",
  
  // EXISTING (AAR raw results):
  "raw_search_results": {
    "total_queries": 5,
    "total_results": 237,
    "results_by_query": [...]
  },
  
  // NEW (Visual Curator output):
  "curator_output": {
    "version": "vc_v1.0",
    "curated_at": "2025-01-05T12:05:00Z",
    "curated_assets": [...],  // from Curator output
    "dedupe_report": {...},
    "coverage_balance": {...},
    "quality_metrics": {...}
  },
  
  // MODIFIED (scény dostávají curated assets místo raw):
  "scenes": [
    {
      "scene_id": "s_0001",
      "block_id": "b_0001",
      "assets": [
        // Reference to curated_assets[] by asset_id
        {"asset_id": "curated_001", "usage": "primary"},
        {"asset_id": "curated_002", "usage": "secondary"}
      ]
    }
  ]
}
```

**Integrační flow:**
```
AAR search → raw_search_results (237 assets)
  ↓
Visual Curator (NEW!) → curated_assets (20 best)
  ↓
AAR manifest finalization → assign curated assets to scenes
  ↓
CB (reads manifest.scenes[].assets[] which now point to curated_assets)
```

---

## 📊 SROVNÁNÍ: PŘED vs. PO (s 2 AI asistenty)

### **PŘED (současný stav):**

| Fáze | Počet queries | Dedupe? | Coverage aware? | Ranking | Result |
|------|---------------|---------|-----------------|---------|--------|
| FDA | 35 queries (7 scén × 5 queries) | ❌ | ❌ | N/A | 15 duplicitních queries |
| AAR Search | 35 API calls | ❌ | ❌ | Per-query top 5 | 237 raw results |
| AAR Selection | N/A | ❌ cross-scene | ❌ | Local optima | 80% maps, 20% other |
| CB Assembly | N/A | N/A | N/A | N/A | 10 map variants in row → nuda |

**Problém:** Generické queries → redundantní results → unbalanced selection → nuda

---

### **PO (s Query Director + Visual Curator):**

| Fáze | Počet queries | Dedupe? | Coverage aware? | Ranking | Result |
|------|---------------|---------|-----------------|---------|--------|
| FDA | 35 raw queries | N/A | N/A | N/A | Raw creative output |
| **Query Director** | **5 strategic queries** | **✅** | **✅** | **Priority-based** | **Deduplicated + balanced** |
| AAR Search | **5 API calls** (7× efektivnější) | ✅ | ✅ | N/A | 200+ raw results |
| **Visual Curator** | **N/A** | **✅** | **✅** | **Global ranking** | **20 best assets, coverage balanced** |
| CB Assembly | N/A | ✅ | ✅ | N/A | Diverse visuals, no repetition |

**Výsledek:** Strategické queries → kvalitní results → balanced selection → NO nuda

---

## 🎯 SUMMARY: Klíčové body pro návrh

### **Současné flow problémy:**

1. **Research → FDA:** Žádná visual coverage guidance
2. **FDA query generation:** Template-based, generické, redundantní
3. **AAR search:** Plýtvá API calls na duplicitní queries
4. **AAR selection:** Per-query ranking, není global/coverage aware
5. **CB assembly:** Dumb executor, nemá control nad visual flow

### **Integrační body pro 2 AI asistenty:**

| Asistent | Zapojení | Vstup | Výstup | Artefakt |
|----------|----------|-------|--------|----------|
| **Query Director** | Mezi FDA a AAR | shot_plan.json (raw queries) + coverage_requirements | strategic_queries[] (deduplicated, coverage-aware) | query_director_output.json |
| **Visual Curator** | Mezi AAR search a manifest | raw_search_results[] (237 assets) + coverage_requirements | curated_assets[] (top 20, balanced) | archive_manifest.json (curator_output section) |

### **Source Pack připravení:**

Pro Query Director + Curator:
1. **Research entities** → ADD visual typing (`visual_need: "portrait|map|document"`)
2. **Coverage requirements** → NEW artifact (research_coverage_plan.json)
3. **AAR raw results** → SEPARATE from curated (keep both in manifest)
4. **Scene-asset assignment** → USE curated_assets[] (not raw results)

---

**KONEC ANALÝZY**

Tento dokument poskytuje 100% přesný snapshot současné architektury pro návrh Query Director + Visual Curator integrace.


