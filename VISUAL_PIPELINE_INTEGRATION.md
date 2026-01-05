# Visual Pipeline Integration - Dokumentace

## 🎯 Přehled

Integrace **Query Director + Visual Curator + Source Pack Builder** do vizuální pipeline pro maximální kvalitu výstupního videa bez kompromisů.

## 📋 Architektura

### Nová Pipeline Sekvence

```
FDA → Query Director → AAR v2 → Visual Curator → Source Pack Builder → CB v2
 ↓         ↓              ↓            ↓                  ↓               ↓
shot_   query_     aar_raw_    visual_        source_           video.mp4
plan    director    results     curator         pack
.json   _output     .json       _output         .json
        .json                   .json
```

### Kontrakty (Artifacts)

#### 1. `query_director_output.json`

```json
{
  "version": "query_director_v1",
  "episode_id": "ep_xxx",
  "coverage_requirements": {
    "required_visual_types": {
      "map": {"min_assets": 2, "reason": "..."},
      "document": {"min_assets": 3, "reason": "..."}
    },
    "diversity_targets": {...}
  },
  "strategic_queries": [
    {
      "query_id": "q_001",
      "query": "Napoleon 1812 archival map public domain",
      "priority": 9,
      "visual_type": "map",
      "intended_scenes": ["sc_0001", "sc_0002"],
      "reasoning": "Used by 2 scene(s), visual_type=map"
    }
  ],
  "dedupe_report": {
    "total_raw_queries": 30,
    "duplicates_removed": 22,
    "strategic_queries": 8,
    "deduplication_rate": 0.733
  },
  "coverage_plan": {...}
}
```

#### 2. `aar_raw_results.json`

```json
{
  "version": "aar_v2_raw_results",
  "episode_id": "ep_xxx",
  "queries": [...],
  "results_by_query": [
    {
      "query_id": "q_001",
      "query": "Napoleon 1812 archival map",
      "results": [
        {
          "archive_item_id": "item_001",
          "asset_url": "https://archive.org/details/item_001",
          "title": "Map of Napoleon's Campaign",
          "media_type": "image",
          "topic_relevance_score": 0.85,
          "visual_type": "map",
          "query_source_id": "q_001"
        }
      ]
    }
  ],
  "summary": {
    "total_queries": 8,
    "successful_queries": 7,
    "total_candidates": 45
  }
}
```

#### 3. `visual_curator_output.json`

```json
{
  "version": "visual_curator_v1",
  "episode_id": "ep_xxx",
  "curated_assets": [
    {
      "archive_item_id": "item_001",
      "asset_url": "...",
      "global_rank": 1,
      "global_score": 0.85,
      "visual_type": "map",
      "recommended_scenes": ["sc_0001"],
      "reasoning": "Visual type 'map' matches 1 scene(s)"
    }
  ],
  "dedupe_report": {
    "total_candidates": 45,
    "unique_assets": 28,
    "duplicates_removed": 17,
    "deduplication_rate": 0.378
  },
  "coverage_balance": {
    "by_visual_type": {
      "map": 5,
      "document": 8,
      "portrait": 6
    },
    "coverage_status": "adequate"
  },
  "deficits": []
}
```

#### 4. `source_pack.json`

```json
{
  "version": "source_pack_v1",
  "episode_id": "ep_xxx",
  "episode_asset_pool": [...],
  "scene_assignments": [
    {
      "scene_id": "sc_0001",
      "start_sec": 0,
      "end_sec": 10,
      "primary_assets": [
        {
          "asset_id": "asset_0001",
          "archive_item_id": "item_001",
          "role": "primary",
          "global_rank": 1
        }
      ],
      "secondary_assets": [...],
      "texture_assets": [...],
      "total_assets": 3,
      "has_deficit": false
    }
  ],
  "coverage_summary": {
    "total_pool_assets": 28,
    "total_assigned_assets": 22,
    "usage_rate": 0.786
  },
  "fallback_pools": {
    "texture_pool": [...],
    "emergency_pool": [...]
  }
}
```

## 🔧 Implementované Moduly

### 1. Query Director (`query_director.py`)

**Účel:** Strategický plánovač vizuálních dotazů

**Klíčové funkce:**
- Cross-scene deduplikace queries (eliminuje redundanci)
- Prioritizace podle visual_type (map=9, document=8, ...)
- Coverage requirements generation
- Query count guardrail (≤ 8 queries per episode)

**API:**
```python
from query_director import run_query_director

output, path = run_query_director(
    shot_plan=shot_plan,
    episode_id="ep_xxx",
    output_path="query_director_output.json",
    verbose=True
)
```

### 2. AAR v2 (`aar_v2.py`)

**Účel:** Raw search nad strategickými queries

**Klíčové funkce:**
- Čte `query_director_output.json` místo scene queries
- Multi-source search (Archive.org + Wikimedia + Europeana)
- Topic relevance validation (AAR v14 feature)
- Ukládá RAW results (bez selection)

**API:**
```python
from aar_v2 import run_aar_v2_search

output, path = run_aar_v2_search(
    query_director_output=qd_output,
    episode_id="ep_xxx",
    cache_dir="./cache",
    output_path="aar_raw_results.json",
    episode_topic="Napoleon 1812",
    verbose=True
)
```

### 3. Visual Curator (`visual_curator.py`)

**Účel:** Výběr nejlepších a nejrozmanitějších assetů

**Klíčové funkce:**
- Quality filtering (low-quality rejection)
- Perceptual dedupe (fingerprint-based)
- Ranking (relevance × 0.6 + quality × 0.4)
- Coverage balance analysis
- Deficit reporting

**API:**
```python
from visual_curator import run_visual_curator

output, path = run_visual_curator(
    aar_raw_results=aar_results,
    shot_plan=shot_plan,
    coverage_requirements=coverage_req,
    episode_id="ep_xxx",
    output_path="visual_curator_output.json",
    verbose=True
)
```

### 4. Source Pack Builder (`source_pack_builder.py`)

**Účel:** Deterministické sestavení source pack pro CB

**Klíčové funkce:**
- Asset → Scene assignment (primary/secondary/texture)
- Cross-scene dedupe enforcement (hard fail if violated)
- Fallback pools pro deficit scény
- Min 2 assets per scene guarantee

**API:**
```python
from source_pack_builder import run_source_pack_builder

output, path = run_source_pack_builder(
    visual_curator_output=vc_output,
    shot_plan=shot_plan,
    episode_id="ep_xxx",
    output_path="source_pack.json",
    min_assets_per_scene=2,
    verbose=True
)
```

### 5. CB v2 (`cb_v2.py`)

**Účel:** Compilation Builder s Source Pack podporou

**Klíčové funkce:**
- Čte `source_pack.json` (primary path)
- Konverze → `archive_manifest.json` (legacy compatibility)
- Fallback na `archive_manifest.json` pokud source pack chybí

**API:**
```python
from cb_v2 import build_compilation_from_source_pack

output_video, metadata = build_compilation_from_source_pack(
    source_pack_path="source_pack.json",
    shot_plan_path="script_state.json",
    episode_id="ep_xxx",
    storage_dir="./assets",
    output_dir="./output",
    verbose=True
)
```

### 6. Visual Pipeline Orchestrator (`visual_pipeline_orchestrator.py`)

**Účel:** Orchestrace celé visual pipeline

**API:**
```python
from visual_pipeline_orchestrator import run_full_visual_pipeline

run_full_visual_pipeline(
    state=script_state,
    episode_id="ep_xxx",
    store=project_store,
    cache_dir="./cache",
    storage_dir="./assets",
    output_dir="./output",
    episode_topic="Napoleon 1812",
    verbose=True
)
```

## 🛡️ Quality Guardrails

### Query Director
- ✅ Query count limit: ≤ 8 strategic queries
- ✅ Map temptation guard: ≤ 20% map queries
- ✅ Duplicate query rate: < 10%

### Visual Curator
- ✅ Low-quality rejection (relevance < 0.2, quality < 0.3)
- ✅ Fingerprint-based dedupe
- ✅ Coverage balance enforcement
- ✅ Deficit reporting

### Source Pack Builder
- ✅ Cross-scene duplicate detection (hard fail)
- ✅ Min 1 asset per scene (critical)
- ✅ Recommended 2+ assets per scene (warning)

## 🧪 Testing

### Test Fixtures

```python
from test_visual_pipeline_acceptance import (
    NAPOLEON_1812_FIXTURE,  # Map temptation test
    MOSCOW_FIRE_FIXTURE,    # Destruction/documents test
)
```

### E2E Test Runner

```bash
# Quick test (bez AAR, používá mock data)
python backend/test_e2e_visual_pipeline.py --fixture napoleon

# Full test (s AAR, vyžaduje network + API keys)
python backend/test_e2e_visual_pipeline.py --fixture moscow --full

# Custom output dir
python backend/test_e2e_visual_pipeline.py --fixture napoleon --output-dir /tmp/test_output
```

### Akceptační Kritéria

```python
from test_visual_pipeline_acceptance import run_acceptance_tests

report = run_acceptance_tests(
    episode_dir="/path/to/episode",
    verbose=True
)

# Report obsahuje:
# - Query count: strategic_queries <= 8
# - Duplicate queries: < 10%
# - Cross-scene duplicates: 0
# - Coverage balance: portraits + documents
# - Source pack validation
# - Diversity metrics
```

## 📊 Metriky

Acceptance report vypíše:

```
ACCEPTANCE TEST REPORT
======================================================================
✓ PASS   | Query Count                    | Query count: 7/8 ✓
✓ PASS   | Duplicate Queries              | Duplicate query rate: 3.5% (<10% required) ✓
✓ PASS   | Cross-Scene Duplicates         | Cross-scene duplicate assets: 0 (0 required) ✓
✓ PASS   | Coverage Balance               | Coverage: Both portraits and documents adequate ✓
✓ PASS   | Source Pack Exists             | Source Pack: Exists and valid ✓
======================================================================
SUMMARY: 5/5 tests passed (100%)

METRICS:
  - Diversity: 4 visual types
  - Query deduplication: 73.3%
  - Asset deduplication: 37.8%
  - Assets used: 22/28
  - Usage rate: 78.6%
======================================================================
```

## 🔄 Integrace do Existující Pipeline

### Option 1: Použít orchestrator přímo

```python
from visual_pipeline_orchestrator import run_full_visual_pipeline

# Po FDA:
run_full_visual_pipeline(
    state=state,
    episode_id=episode_id,
    store=store,
    cache_dir=cache_dir,
    storage_dir=storage_dir,
    output_dir=output_dir,
    episode_topic=topic,
    verbose=True
)
```

### Option 2: Použít individual step runners

```python
from visual_pipeline_orchestrator import (
    run_query_director_step,
    run_aar_v2_step,
    run_visual_curator_step,
    run_source_pack_builder_step,
    run_cb_v2_step,
)

# Po FDA:
run_query_director_step(state, episode_id, store, verbose=True)
run_aar_v2_step(state, episode_id, store, cache_dir, episode_topic=topic, verbose=True)
run_visual_curator_step(state, episode_id, store, verbose=True)
run_source_pack_builder_step(state, episode_id, store, verbose=True)
run_cb_v2_step(state, episode_id, store, storage_dir, output_dir, verbose=True)
```

### Option 3: Legacy Compatibility Mode

CB v2 automaticky fallbackuje na `archive_manifest.json` pokud `source_pack.json` neexistuje.

```python
# Existující kód zůstává funkční:
from compilation_builder import build_episode_compilation

output_video, metadata = build_episode_compilation(
    manifest_path="archive_manifest.json",  # Legacy path
    episode_id=episode_id,
    storage_dir=storage_dir,
    output_dir=output_dir
)
```

## 📦 Výstupní Soubory

Po úspěšném běhu pipeline najdete v `projects/<episode_id>/`:

```
projects/
└── <episode_id>/
    ├── script_state.json            # Hlavní state (obsahuje shot_plan)
    ├── query_director_output.json   # Strategic queries + coverage plan
    ├── aar_raw_results.json         # Raw search results (všichni kandidáti)
    ├── visual_curator_output.json   # Curated assets + coverage report
    ├── source_pack.json             # Final source pack pro CB
    ├── archive_manifest.json        # (Legacy - pokud se použije)
    └── aar_cache/                   # Search cache (7 dní TTL)
```

## 🚨 Troubleshooting

### Query Director chyby

```
❌ QD_TOO_MANY_QUERIES: Strategic queries count (12) exceeds recommended limit (8)
```
**Fix:** FDA generuje příliš mnoho unique queries. Zkontroluj `shot_plan.scenes[].search_queries[]`.

### Visual Curator warnings

```
⚠️ Coverage: Portraits deficient (documents OK)
```
**Fix:** AAR nenašel dost portrait assetů. Zkontroluj strategic queries priority.

### Source Pack Builder critical errors

```
❌ SP_CROSS_SCENE_DUPLICATE: Asset asset_0001 used in multiple scenes: ['sc_0001', 'sc_0002']
```
**Fix:** Bug v assignment logic - asset se použil víckrát. Hard fail, opravit builder.

### CB v2 fallback

```
⚠️ Falling back to archive_manifest.json (legacy pipeline)
```
**Info:** Source pack není dostupný, CB používá legacy path. Pipeline funguje, ale bez nových guardrails.

## 📄 Licence

MIT - Součást podcasts repository.

## 👥 Autoři

Cursor AI + Petr Liesner (2025)


