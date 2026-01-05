# Video Visual Pipeline – Architecture Snapshot

**Datum:** 3. ledna 2025  
**Účel:** Kompletní popis současné pipeline pro generování vizuálů (thumbnails, footage selection, B-roll)  
**Stav:** Production-ready (FDA v2.7 + AAR v14 + Visual Assistant + Compilation Builder v3)

---

## Executive Summary

Pipeline transformuje TTS naraci na finální video kombinací:
- **LLM plánování** (Footage Director Assistant) → scény + search queries
- **Multi-source search** (Archive Asset Resolver) → archive.org, Wikimedia, Europeana, Pexels, Pixabay
- **LLM Vision evaluace** (Visual Assistant) → deduplication + quality ranking
- **Video kompilace** (Compilation Builder) → download + FFmpeg assembly

**Architektura:** Episode-first pool mode (10-20× rychlejší než per-scene)  
**Výstup:** MP4 video s voiceover, Ken Burns efekty, automatické titulky

---

## Input Data

### Co přichází z upstreamu

1. **TTS Ready Package** (`script_state.json` → `tts_ready_package`)
   - `narration_blocks[]` – jednotky narativního textu
     - `block_id` (string): unikátní identifikátor
     - `text_tts` (string): text pro TTS syntézu
     - `claim_ids[]` (array): zpětné odkazy na fact-checking claims
     - `duration_sec` (float): odhadovaná délka čtení (150 WPM)
   
2. **Episode Metadata**
   - `episode_topic` (string): hlavní téma epizody (např. "Nikola Tesla")
   - `language` (string): jazyk narrace (např. "en-US")
   - `target_minutes` (float): cílová délka epizody
   - `channel_profile` (string): "documentary" | "educational" | "news"

3. **User Preferences** (optional)
   - `max_videos` (int): limit videí v episode pool (default: 8)
   - `max_images` (int): limit obrázků v episode pool (default: 15)
   - `enable_visual_assistant` (bool): automatická LLM evaluace (default: true)

### Formát vstupních dat

```json
{
  "episode_id": "ep_abc123",
  "episode_topic": "Nikola Tesla wireless power experiments",
  "language": "en-US",
  "tts_ready_package": {
    "narration_blocks": [
      {
        "block_id": "b_0001",
        "text_tts": "In 1891, Tesla demonstrated wireless power transmission in Colorado Springs.",
        "claim_ids": ["claim_x1", "claim_x2"],
        "duration_sec": 4.8
      }
    ]
  }
}
```

---

## Pipeline Kroky

### Krok 1: Footage Director Assistant (FDA v2.7)

**Modul:** `backend/footage_director.py`  
**Input:** `tts_ready_package` (narration blocks)  
**Output:** `shot_plan` (JSON struktura s scénami)

#### Co dělá
- Groupuje narration blocky do **scenes** (20-35 sec, max 8 bloků)
- Pro každou scénu generuje:
  - `narration_summary` (1 věta, EN, gramaticky správná)
  - `keywords[]` (PŘESNĚ 8 concrete noun phrases, 2-5 slov)
  - `emotion` (neutral/tension/tragedy/hope/victory/mystery)
  - `shot_types[]` (enums: maps_context, archival_documents, troop_movement, atd.)
  - `search_queries[]` (3-8 queries pro AAR)
  - `clip_length_sec_range` ([min, max] pro cut timing)
  - `cut_rhythm` (slow/medium/fast)

#### Vstup/Výstup
- **Input structure:** `{narration_blocks: [{block_id, text_tts, ...}]}`
- **Output structure:** `{shot_plan: {version: "fda_v2.7", scenes: [{scene_id, keywords, search_queries, ...}]}}`

#### Hard-fail podmínky
- LLM vrátí non-JSON odpověď → `FDA_HARD_FAIL`
- `shot_plan.version != "fda_v2.7"` → force coerce to v2.7
- keywords obsahují zakázaná slova (verbs, adjectives) → Pre-FDA Sanitizer fix
- search_queries bez temporal anchors → deterministický fallback generátor

#### Co se cachuje
- **Místo:** `projects/<episode_id>/script_state.json`
- **Klíč:** `fda_package.shot_plan`
- **TTL:** Persistent (neexpiruje, vazba na episode_id)

---

### Krok 2: Pre-FDA Sanitizer (deterministická jazyková disciplína)

**Modul:** `backend/pre_fda_sanitizer.py`  
**Input:** `shot_plan` z FDA  
**Output:** Sanitized `shot_plan`

#### Co dělá
- **Keywords cleaning:** odstraní forbidden words (articles, verbs, conjunctions)
- **Search queries fix:** zajistí temporal anchors (rok, éra, proper noun)
- **Query mix guard:** min 1 broad query + min 2 specific queries
- **Fallback injection:** pokud LLM selže, použije deterministický generátor

#### Vstup/Výstup
- **Input:** Raw FDA output (může obsahovat "the", "upon", "soon", verbs)
- **Output:** Sanitized shot_plan (čisté noun phrases, anchored queries)

#### Hard-fail podmínky
- Žádné – vždy produkuje validní output (worst-case: deterministický fallback)

#### Co se loguje
- **Místo:** `script_state.json` → `fda_package.sanitization_log`
- **Obsah:** Seznam replacements (original → sanitized), fallback použití

---

### Krok 3: FDA Output Validator (schema enforcement)

**Modul:** `backend/footage_director.py` → `validate_fda_hard_v27()`  
**Input:** Sanitized shot_plan  
**Output:** Validated shot_plan (projde nebo hard-fail)

#### Co dělá
- Schema check: povinná pole, správné typy
- Enum validation: shot_types, emotion, cut_rhythm
- Timing validation: contiguous scenes, integer times, min 2 sec duration
- Order validation: narration_block_ids bez duplikátů, v pořadí

#### Hard-fail podmínky
- Missing scene_id / narration_block_ids → `FDA_VALIDATION_FAIL`
- Timing overlaps nebo gaps → `FDA_VALIDATION_FAIL`
- Duplicitní block_ids → `FDA_VALIDATION_FAIL`

#### Co se loguje
- **Místo:** `script_state.json` → `fda_validation_result`
- **Obsah:** Pass/fail status, error details, violations list

---

### Krok 4: Archive Asset Resolver – Episode Pool Mode (AAR v14)

**Modul:** `backend/archive_asset_resolver.py` → `resolve_episode_pool()`  
**Input:** Validated shot_plan + episode_topic  
**Output:** `archive_manifest.json` s episode_pool

#### Co dělá
- Generuje **episode-level queries** (mix z top keywords, entities, temporal anchors)
- Multi-source search:
  - **Archive.org** (movies/movingimage + image search + texts/maps)
  - **Wikimedia Commons** (video files + images)
  - **Europeana** (cultural heritage, optional API key)
  - **Pexels** (stock video, optional API key)
  - **Pixabay** (stock video/images, optional API key)
- **LLM Topic Relevance Validation** (GPT-4o-mini):
  - Filtruje off-topic kandidáty (např. Zimbabwe news v Tesla epizodě)
  - Threshold: videos ≥0.40, images ≥0.10
- **Media cascade:** video stage → image stage → document/map stage
- **Deduplication:** Groupuje duplicitní item_ids (stejný asset, různé queries)

#### Vstup/Výstup
- **Input:** `{shot_plan: {scenes: [...]}}, episode_topic: "string"`
- **Output:** `{episode_pool: {videos: [...], images: [...], queries_used: [...]}}`

#### Hard-fail podmínky
- Všechny zdroje nedostupné (network fail) → warning, pokračuje s prázdným poolem
- Cache directory write fail → non-critical, jen hlásí warning

#### Co se cachuje
- **Místo:** `projects/<episode_id>/archive_cache/`
- **Klíč:** `archive_search_v14_<pass>_<query_hash>.json`
- **TTL:** Implicitně 7 dní (lze rozšířit env var)
- **Obsah:** Raw search results (item_id, title, license, thumbnail_url, downloads, ...)

---

### Krok 5: Visual Assistant – LLM Vision Deduplication + Quality Ranking

**Modul:** `backend/visual_assistant.py` → `deduplicate_and_rank_pool_candidates()`  
**Input:** Episode pool candidates (videos + images s thumbnail_url)  
**Output:** Ranked unique candidates s `llm_quality_score` a `llm_analysis`

#### Co dělá
- **Fáze 1: Visual Deduplication**
  - LLM Vision API analyzuje thumbnaily batch (max 30 najednou)
  - Groupuje vizuálně podobné/duplicitní (stejný záběr, různé URLs)
  - Z každé group vybere best quality (nejvyšší relevance × quality)

- **Fáze 2: Quality Ranking**
  - Pro každý unique kandidát hodnotí:
    - `relevance_score` (0.0–1.0): semantic match k episode_topic
    - `has_text_overlay` (bool): detekuje titulky, UI, watermarks
    - `quality_issues[]` (strings): "Low resolution", "Wrong era", "Subtitles visible"
    - `recommendation` ("use" | "skip" | "fallback")
  - Finální score: `relevance × quality × suitability`

#### Vstup/Výstup
- **Input:** `[{archive_item_id, thumbnail_url, title, description, source, ...}]`
- **Output:** `[{...původní fields, llm_quality_score: 0.82, llm_analysis: {...}}]`

#### Hard-fail podmínky
- OpenAI/OpenRouter API klíč chybí → fallback na script-based scoring
- Vision API timeout → kandidát dostane fallback score 0.2 (lowest priority)
- Rate limit (429) → retry s exponential backoff

#### Co se loguje
- **Místo:** `archive_manifest.json` → `episode_pool.llm_vision_log`
- **Obsah:** API calls count, groups count, duplicates removed, top scores

---

### Krok 6: Asset Selection – Top N per Type

**Modul:** `backend/archive_asset_resolver.py` → `resolve_episode_pool()` (post-LLM phase)  
**Input:** Ranked candidates s llm_quality_score  
**Output:** Selected pool (max_videos=8, max_images=15)

#### Co dělá
- **Topic relevance gate:**
  - Videos: `topic_relevance ≥ 0.40` (strict)
  - Images: `topic_relevance ≥ 0.10` (relaxed)
- **Quality soft threshold:** `llm_quality_score ≥ 0.40` (fallback k lower pokud empty)
- **Selection policy:**
  - Prefer (relevant ∩ high-quality)
  - Fallback to relevant (lower quality) pokud empty
  - Never select off-topic, i když high quality

#### Vstup/Výstup
- **Input:** `unique_ranked: {videos: [...], images: [...]}`
- **Output:** `selected_ranked: {videos: [top 8], images: [top 15]}`

#### Hard-fail podmínky
- Pool úplně prázdný (0 videos, 0 images) → pokračuje s local safety pack

#### Co se ukládá
- **Místo:** `archive_manifest.json` → `episode_pool.selected_ranked`
- **Klíč:** per-episode (není globální cache)

---

### Krok 7: Per-Beat Asset Assignment

**Modul:** `backend/aar_step_by_step.py` → `llm_quality_check()` (UI flow) nebo automatic per-beat distribution  
**Input:** Selected pool + beats (individual narration_block_ids)  
**Output:** `archive_manifest.json` s `beats[].asset_candidates[]`

#### Co dělá
- Pro každý beat (narration block):
  - Vybere 3-5 top kandidátů z pool podle:
    - Semantic similarity (keywords match)
    - Media type preference (video > image pro delší beaty)
    - Diversity (avoid consecutive repeats)
  - Přiřadí priority: "use" > "fallback" > "skip"
  - User může manuálně override (UI checkboxes)

#### Vstup/Výstup
- **Input:** `{beats: [{block_id, text, keywords, duration_sec}], pool: {videos, images}}`
- **Output:** `{beats: [{..., asset_candidates: [archive_item_id_1, archive_item_id_2, ...]}]}`

#### Hard-fail podmínky
- Beat bez kandidátů → fallback na local_safety_pack (repo-level `images/` dir)

#### Co se ukládá
- **Místo:** `archive_manifest.json` → `beats[]` (per-beat level)
- **Struktur:** `asset_candidates: [id1, id2, id3]` (ordered by priority)

---

### Krok 8: Compilation Builder – Download + FFmpeg Assembly (CB v3)

**Modul:** `backend/compilation_builder.py` → `build_compilation()`  
**Input:** `archive_manifest.json` s per-beat asset assignments  
**Output:** Final MP4 video (`output/episode_<id>_compilation_<timestamp>.mp4`)

#### Co dělá
- **Download assets:**
  - Persistent cache: `projects/<episode_id>/assets/`
  - Cache key: `<archive_item_id>.mp4` nebo `.jpg`
  - Download sources:
    - Archive.org: `/download/<item_id>/<item_id>.mp4` nebo metadata API
    - Wikimedia: direct media URL z API
    - Pexels/Pixabay: CDN direct URLs
    - Local safety pack: `images/<filename>` (fallback)
  - Size limit: 150MB per asset (skip huge files)
  - Duration limit: max 30 min per video (prevent full-length movies)

- **Quality checks (post-download):**
  - `ffprobe` resolution check (min 960×540)
  - Video stream validation (has_video=true)
  - Frame sampling (3 points): blackish/caption/UI detection
  - Reject criteria:
    - No video stream → hard reject
    - YouTube-like UI detected → hard reject
    - >60% frames blackish → hard reject
    - >70% frames with captions → hard reject

- **Subclip extraction:**
  - Per beat: calculate target_duration (TTS duration)
  - Pro každý asset: vybere usable segments (non-blackish)
  - FFmpeg extract: `-ss <in> -to <out> -c copy` (fast, no re-encode)
  - Ken Burns effect pro images: zoom/pan 2-11 sec

- **FFmpeg concat:**
  - Concat list: `file 'subclip_001.mp4'\nfile 'subclip_002.mp4'\n...`
  - Audio track: combined voiceover MP3 (z TTS)
  - Subtitles: auto-generated SRT (z narration_blocks)
  - Output: `-c:v libx264 -preset medium -crf 23 -c:a aac final.mp4`

#### Vstup/Výstup
- **Input:** `archive_manifest.json` (full structure)
- **Output:** `{output_path: "output/episode_<id>.mp4", clips_metadata: [...], scenes_metadata: [...]}`

#### Hard-fail podmínky
- **Zero clips created → CRITICAL FAIL** (NO BLACK FALLBACKS policy)
  - Error: `CB_CRITICAL_NO_VISUAL_ASSETS`
  - Compilation fails → user musí retry s jinými queries
- FFmpeg not installed → `CB_FFMPEG_MISSING`
- Všechny downloads failují → `CB_NO_DOWNLOADABLE_ASSETS`

#### Co se ukládá
- **Download cache:** `projects/<episode_id>/assets/<item_id>.mp4`
- **Subclips:** `projects/<episode_id>/storage/subclip_*.mp4` (temporary)
- **Final video:** `output/episode_<id>_compilation_<timestamp>.mp4`
- **Metadata:** `script_state.json` → `compilation_video_path`, `compilation_metadata`

---

## Výstup Pipeline

### Co přesně vzniká

1. **Episode Pool** (`archive_manifest.json` → `episode_pool`)
   - `videos[]`: Top 8 videí (unique, ranked)
   - `images[]`: Top 15 obrázků (unique, ranked)
   - `queries_used[]`: Queries použité pro search
   - `stats`: Total found, duplicates removed, LLM analyzed
   - `llm_vision_log`: Visual Assistant metrics

2. **Per-Beat Assets** (`archive_manifest.json` → `beats[]`)
   - Pro každý `narration_block_id`:
     - `asset_candidates[]`: 3-5 kandidátů (ordered by priority)
     - `selected_asset`: finální volba (user nebo auto)
     - `assignment_reason`: "llm_quality" | "manual" | "fallback"

3. **Downloaded Media** (`projects/<episode_id>/assets/`)
   - Cache: `<archive_item_id>.mp4`, `<archive_item_id>.jpg`
   - Persistent across re-runs

4. **Final Video** (`output/episode_<id>_compilation_<timestamp>.mp4`)
   - Resolution: 1280×720 nebo 1920×1080 (podle source assets)
   - Audio: AAC 128kbps (combined voiceover)
   - Subtitles: Burned-in SRT (optional, env var controlled)
   - Duration: Matches TTS narration length (± 2%)

5. **Compilation Metadata** (`script_state.json` → `compilation_metadata`)
   - `clips_count`: Počet subclipů
   - `scenes_count`: Počet scén
   - `coverage_percent`: Visual coverage (clips/beats × 100)
   - `fallback_count`: Local safety pack usage
   - `clips_metadata[]`: Per-clip details (asset_id, in/out times, duration)

### Napojení na downstream

- **YouTube Export:** `compilation_video_path` → direct upload
- **Render API:** `compilation_metadata` → player timeline
- **Analytics:** `archive_manifest.json` → source attribution, license tracking

---

## Diagnostika & Monitoring

### Key Metrics

1. **FDA stage:**
   - `fda_llm_call_duration_sec`: LLM response time
   - `fda_sanitization_replacements`: Kolik keywords/queries fixnuto

2. **AAR stage:**
   - `aar_episode_queries_count`: Kolik queries vygenerováno
   - `aar_search_results_total`: Total candidates found
   - `aar_duplicates_removed`: Dedup effectiveness
   - `aar_topic_rejected`: Off-topic filtering count

3. **Visual Assistant stage:**
   - `va_api_calls_count`: LLM Vision API calls
   - `va_duplicates_grouped`: Visual dedup groups
   - `va_avg_relevance_score`: Mean score per-type
   - `va_skip_count`: Kolik označeno "skip"

4. **CB stage:**
   - `cb_downloads_attempted`: Asset download attempts
   - `cb_downloads_cached`: Cache hit rate
   - `cb_quality_rejects`: Post-download rejects
   - `cb_clips_created`: Final subclips count
   - `cb_visual_coverage_percent`: Coverage (min 50% required)

### Logs & Telemetry

- **Location:** `script_state.json` → `pipeline_log[]`
- **Format:** `[{timestamp, step, event, data}]`
- **Retention:** Per-episode (deleted with episode cleanup)

---

## Known Limitations & Edge Cases

1. **Archive.org rate limits:**
   - Symptom: HTTP 429 responses
   - Mitigation: Exponential backoff, cache extended to 30 days

2. **LLM Vision API failures:**
   - Symptom: Timeout, rate limit, JSON parse error
   - Mitigation: Fallback score 0.2, skip kandidát v selection

3. **Zero search results:**
   - Symptom: Pool prázdný (queries příliš specific / niche topic)
   - Mitigation: Local safety pack (repo-level `images/`)

4. **Off-topic contamination:**
   - Symptom: Zimbabwe news v Tesla epizodě
   - Solution: LLM Topic Relevance Validator (AAR v14+)

5. **Black screen clips (historical):**
   - Symptom: Videos with no video stream / mostly black frames
   - Solution: CB v3 hard-rejects (NO BLACK FALLBACKS policy)

---

## Version History

- **FDA v2.7:** Version lock enforcement, deterministic fallback queries
- **AAR v14:** LLM Topic Relevance Validation, episode-first pool mode
- **Visual Assistant v1:** LLM Vision deduplication + quality ranking
- **CB v3:** NO BLACK FALLBACKS policy, Ken Burns effects pro images

**Current stable:** FDA v2.7 + AAR v14 + VA v1 + CB v3 (Jan 2025)


