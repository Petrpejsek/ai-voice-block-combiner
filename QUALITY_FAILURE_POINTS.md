# Quality Failure Points – Video Visual Pipeline Diagnostika

**Datum:** 3. ledna 2025  
**Účel:** Top 10 míst kde dochází k degradaci kvality vizuálů  
**Status:** Production diagnostika z FDA v2.7 + AAR v14 + Visual Assistant + CB v3

---

## 1. Off-Topic Search Results (AAR)

### Symptomy
- Zimbabwe news v Tesla epizodě
- Modern Ukraine conflict footage v Napoleon 1812 epizodě
- Generic "wireless power" stock footage místo historických dokumentů

### Pravděpodobná příčina
- Search queries bez temporal anchors (rok, éra, proper noun)
- Archive.org vrací relevantní metadata match, ale obsah je off-topic
- FDA vygeneruje příliš generic queries ("wireless power transmission")

### Metrika/Log
- **Location:** `archive_manifest.json` → `episode_pool.llm_topic_validation_log`
- **Metrics:**
  - `topic_rejected_count`: kolik kandidátů failnulo topic relevance gate
  - `avg_topic_relevance_score`: průměrné skóre (threshold: videos ≥0.40, images ≥0.10)
- **Log line:**
  ```json
  {
    "candidate_id": "archive:maxwell-chikumbutso-zimbabwe",
    "episode_topic": "Nikola Tesla",
    "topic_relevance": 0.12,
    "rejected_reason": "off_topic_low_relevance"
  }
  ```

### Fix Status
- ✅ **Implemented (AAR v14):** LLM Topic Relevance Validator
- ✅ **Implemented (FDA v2.7):** Temporal anchor enforcement v search queries

---

## 2. Duplicitní Assets (Stejný Záběr, Různé URLs)

### Symptomy
- Stejný archivní film stažený 5× pod různými item_ids
- Compilation má repetitivní vizuály (stejná mapa 3× za sebou)
- Episode pool: 30 images, ale vizuálně jen 8 unikátních

### Pravděpodobná příčina
- Archive.org má duplikáty (různé uploaders, mirror items)
- Wikimedia má multiple resolutions téhož souboru
- Script-based deduplication (hash item_id) nezachytí vizuální duplicity

### Metrika/Log
- **Location:** `archive_manifest.json` → `episode_pool.visual_deduplication_log`
- **Metrics:**
  - `duplicate_groups_found`: kolik skupin duplicitů
  - `duplicates_removed`: kolik assetů odstraněno (kept best quality per group)
  - `unique_after_dedup`: finální count unique assetů
- **Log line:**
  ```json
  {
    "group_id": "g_001",
    "similar_candidates": [
      "archive:prelinger-123",
      "archive:prelinger-456",
      "wikimedia:File:Same_footage.webm"
    ],
    "kept": "wikimedia:File:Same_footage.webm",
    "reason": "highest_quality_score"
  }
  ```

### Fix Status
- ✅ **Implemented (Visual Assistant v1):** LLM Vision deduplication
- ⚠️ **Partial:** Funguje pro top 30 candidates (runtime limit), neaplikuje se na celý pool

---

## 3. Low Semantic Match (Keyword Mismatch)

### Symptomy
- Query "Napoleon Moscow map 1812" → vrací generic Russia maps (20th century)
- Query "Tesla wireless power" → vrací mobile phone charging pads
- Narration o "surrender delegation" → footage je battle scenes

### Pravděpodobná příčina
- FDA keywords neodpovídají naraci (LLM halucinace)
- Search queries příliš broad (2 slova) nebo příliš specific (7+ slov)
- Archive.org full-text search matchuje irelevantní metadata fields

### Metrika/Log
- **Location:** `script_state.json` → `fda_package.sanitization_log`
- **Metrics:**
  - `keywords_replaced`: kolik keywords fixnuto (original → sanitized)
  - `queries_replaced`: kolik queries regenerováno (fallback použit)
- **Log line:**
  ```json
  {
    "scene_id": "sc_0005",
    "original_keywords": ["following", "the", "great", "arrival"],
    "sanitized_keywords": ["Moscow street", "delegation officials", "city gate", "map scan"],
    "replacement_count": 4
  }
  ```
- **Visual Assistant log:**
  ```json
  {
    "candidate_id": "archive:prelinger-789",
    "llm_analysis": {
      "relevance_score": 0.28,
      "reasoning": "Záběr vypadá jako osvobození (jiné období), kontexově nesedí na beat o vstupu vojsk 1940."
    }
  }
  ```

### Fix Status
- ✅ **Implemented (Pre-FDA Sanitizer):** Keyword cleaning, fallback generator
- ✅ **Implemented (Visual Assistant):** Per-candidate semantic relevance scoring
- ⚠️ **Improvement needed:** FDA prompt needs tighter "narration-first" enforcement

---

## 4. Text Overlay / Subtitles v Záběrech

### Symptomy
- Thumbnaily s velkými YouTube titulky ("AMAZING TESLA SECRETS!")
- Burned-in captions v archivním footage
- Watermarks, channel logos, UI overlays (player controls)

### Pravděpodobná příčina
- Source: YouTube re-uploads archivního footage (s added graphics)
- Archive.org: documentaries s embedded subtitles
- Wikimedia: educational videos s instructional overlays

### Metrika/Log
- **Location:** `archive_manifest.json` → `episode_pool.videos[].llm_analysis.quality_issues[]`
- **Metrics:**
  - `has_text_overlay`: bool per-candidate
  - `quality_issues`: ["Text overlay", "Subtitles visible", "YouTube UI visible"]
- **Log line:**
  ```json
  {
    "candidate_id": "archive:tesla-documentary-456",
    "llm_analysis": {
      "has_text_overlay": true,
      "quality_issues": ["Text overlay", "YouTube UI visible"],
      "recommendation": "skip",
      "reasoning": "Thumbnail obsahuje výrazné titulky a YouTube player UI, nevhodné pro čistý dokument."
    }
  }
  ```

### Fix Status
- ✅ **Implemented (Visual Assistant):** LLM Vision detekuje text overlays
- ✅ **Implemented (CB v3):** Post-download frame sampling detekuje caption-like overlays
- ⚠️ **Gap:** CB frame sampling je post-download (plýtvá bandwidth na rejects)

---

## 5. Wrong Era / Anachronism

### Symptomy
- Liberation 1944 footage v beat o Occupation 1940
- Modern HD documentary footage v historical topic
- Color footage pro 1800s topic (should be B&W/sepia)

### Pravděpodobná příčina
- Search query temporal anchor mismatch (query má "1812", ale metadata má "1944")
- Archive.org metadata nespolehlivá (date field = upload date, ne content date)
- LLM Vision doesn't always catch subtle era mismatches

### Metrika/Log
- **Location:** `archive_manifest.json` → `episode_pool.videos[].llm_analysis.quality_issues[]`
- **Metrics:**
  - `quality_issues`: ["Wrong era"]
  - `relevance_score`: typically <0.30 for era mismatches
- **Log line:**
  ```json
  {
    "candidate_id": "archive:liberation-1944-footage",
    "beat_context": "narration about 1940 occupation",
    "llm_analysis": {
      "quality_issues": ["Wrong era"],
      "relevance_score": 0.22,
      "recommendation": "skip",
      "reasoning": "Záběr vypadá jako osvobození 1944, beat je o vstupu vojsk 1940 (jiné období)."
    }
  }
  ```

### Fix Status
- ✅ **Implemented (Visual Assistant):** LLM Vision penalty for "Wrong era"
- ⚠️ **Improvement needed:** FDA prompt should extract dates from narration more reliably

---

## 6. Low Resolution / Blurry Assets

### Symptomy
- 320×240 video v 1080p compilation (pixelated upscale)
- Heavily compressed JPEGs (artifacts visible)
- Archive.org "access copy" místo "original" (lower quality)

### Pravděpodobná příčina
- Archive.org search API nevrací resolution metadata (musí fetchnout per-item)
- Wikimedia thumbnail URL místo full-res download URL
- CB downloads "access copy" (fast) místo "original" (slow, high-quality)

### Metrika/Log
- **Location:** `compilation_metadata.quality_rejects[]`
- **Metrics (CB stage):**
  - `reject_reason`: "low_resolution"
  - `media_info`: `{"width": 320, "height": 240}`
- **Threshold:** min 960×540 (enforced in CB v3)
- **Log line:**
  ```json
  {
    "asset_id": "archive:low-res-video-123",
    "reject_reason": "low_resolution",
    "media_info": {
      "width": 480,
      "height": 360,
      "has_video": true
    }
  }
  ```

### Fix Status
- ✅ **Implemented (CB v3):** Post-download resolution gate (min 960×540)
- ❌ **Gap:** CB discovers low-res AFTER download (wasted bandwidth)
- 🔧 **Improvement needed:** AAR should pre-check resolution via metadata API

---

## 7. Mostly Black / No Usable Frames

### Symptomy
- Video file downloads OK, ale při playback: 90% černá obrazovka
- Intro/outro black frames (10+ seconds)
- Film leader (countdown, color bars) in archival footage

### Pravděpodobná příčina
- Archive.org: full reel uploads (contains leader, blank sections)
- Poor encoding: missing keyframes → black sections
- CB subclip selection: náhodně vybere blackish segment

### Metrika/Log
- **Location:** `compilation_metadata.quality_rejects[]`
- **Metrics (CB stage):**
  - `reject_reason`: "mostly_black_frames"
  - `bad_votes`: `{"blackish": 3, "total": 3}` (100% samples black)
- **Threshold:** ≥60% samples blackish → reject
- **Log line:**
  ```json
  {
    "asset_id": "archive:film-reel-456",
    "reject_reason": "mostly_black_frames",
    "frame_samples": [
      {"t": 5.2, "class": {"is_blackish": true}},
      {"t": 15.8, "class": {"is_blackish": true}},
      {"t": 25.1, "class": {"is_blackish": true}}
    ],
    "bad_votes": {"blackish": 3, "total": 3}
  }
  ```

### Fix Status
- ✅ **Implemented (CB v3):** Frame sampling detects blackish frames
- ✅ **Implemented (CB v3):** Subclip selection avoids blackish segments
- ⚠️ **Gap:** Full-video blackish check happens post-download (wasted bandwidth)

---

## 8. Random B-Roll (Generic Stock Footage)

### Symptomy
- Generic "office meeting" stock footage v Napoleon episode
- Modern city timelapse v historical topic
- Pexels/Pixabay stock dominuje episode pool (místo archival)

### Pravděpodobná příčina
- AAR preferuje stock sources (Pexels/Pixabay) kvůli:
  - Higher thumbnail quality
  - Better metadata
  - Fast download speeds
- FDA queries jsou příliš generic ("power transmission", "conflict")
- Stock footage semantic match je weak (keywords match, ale context ne)

### Metrika/Log
- **Location:** `archive_manifest.json` → `episode_pool.source_distribution`
- **Metrics:**
  - `source_counts`: `{"pexels": 12, "archive_org": 3, "wikimedia": 0}`
  - Ideal: `archive_org` dominant pro historical topics
- **Log line:**
  ```json
  {
    "episode_topic": "Nikola Tesla 1891",
    "pool_videos": [
      {"source": "pexels", "title": "Modern power plant timelapse"},
      {"source": "pexels", "title": "Office worker typing"},
      {"source": "archive_org", "title": "Tesla Colorado Springs lab 1899"}
    ],
    "warning": "Stock sources dominating historical topic"
  }
  ```

### Fix Status
- ⚠️ **Improvement needed:** AAR should deprioritize stock for `channel_profile="documentary"`
- 🔧 **Workaround:** User can disable stock: `AAR_ENABLE_STOCK_SOURCES=0`

---

## 9. Opakující se Assets (Consecutive Repeats)

### Symptomy
- Stejná mapa použita 3× za sebou (různé beaty, stejný asset)
- Compilation vypadá repetitivně (visual monotony)
- User feedback: "Why is the same image repeating?"

### Pravděpodobná příčina
- Per-beat assignment: každý beat vybírá nezávisle z poolu
- Pool je malý (např. 2 videos + 5 images pro 20-beat episode)
- Diversity constraint není enforced

### Metrika/Log
- **Location:** `compilation_metadata.diversity_report`
- **Metrics:**
  - `unique_assets_used`: 8 (z 20 beats = 40% unique)
  - `max_consecutive_repeats`: 3
- **Log line:**
  ```json
  {
    "asset_id": "archive:napoleon-map-russia",
    "used_in_beats": ["b_0001", "b_0002", "b_0005", "b_0008"],
    "usage_count": 4,
    "max_consecutive": 2,
    "warning": "Asset repeated consecutively"
  }
  ```

### Fix Status
- ❌ **Not implemented:** Diversity constraint v per-beat assignment
- 🔧 **Workaround:** Zvýšit pool size: `AAR_POOL_MAX_VIDEOS=8`, `AAR_POOL_MAX_IMAGES=15`

---

## 10. Compilation Builder Fails (Zero Clips Created)

### Symptomy
- CB runs, downloads assets, ale finální video není vytvořeno
- Error: `CB_CRITICAL_NO_VISUAL_ASSETS`
- Logs: "0 clips created from 20 beats"

### Pravděpodobná příčina
- **Root cause chain:**
  1. All downloaded assets fail quality gates (low-res, no video stream, blackish)
  2. No fallback assets available (local safety pack missing/disabled)
  3. CB v3 policy: NO BLACK FALLBACKS → fail compilation

- **Why assets fail:**
  - Archive.org metadata lied (video stream missing)
  - Wikimedia returned audio-only files
  - Post-download checks too strict (min 960×540 + blackish + caption gates)

### Metrika/Log
- **Location:** `compilation_metadata.error`
- **Metrics:**
  - `total_beats`: 20
  - `clips_created`: 0
  - `quality_rejects`: 18 (90% reject rate)
- **Log line:**
  ```json
  {
    "error": "CB_CRITICAL_NO_VISUAL_ASSETS",
    "reason": "Zero visual clips were created. BLACK FALLBACKS ARE DISABLED.",
    "total_beats": 20,
    "clips_created": 0,
    "quality_rejects": [
      {"asset": "archive:video-1", "reason": "no_video_stream"},
      {"asset": "archive:video-2", "reason": "low_resolution"},
      {"asset": "wikimedia:File:X.webm", "reason": "mostly_black_frames"}
    ],
    "policy": "NO_BLACK_FALLBACKS",
    "debug_info": {
      "downloads_attempted": 18,
      "downloads_successful": 18,
      "post_download_rejects": 18
    }
  }
  ```

### Fix Status
- ✅ **Implemented (CB v3):** NO BLACK FALLBACKS policy (user request)
- ⚠️ **Tradeoff:** Higher fail rate, ale vyšší kvalita (žádné černé obrazovky)
- 🔧 **Mitigation:** Zvýšit pool size, povolit stock sources jako fallback

---

## Prioritizace Fixes

### Severity Scoring

| Issue | Frequency | User Impact | Fix Complexity | Priority |
|-------|-----------|-------------|----------------|----------|
| 1. Off-topic results | 🔴 High (20% pool) | 🔴 Critical (unusable) | ✅ Fixed (AAR v14) | ✅ Done |
| 2. Duplicates | 🟡 Medium (15% pool) | 🟡 Medium (annoying) | ✅ Fixed (VA v1) | ✅ Done |
| 3. Low semantic match | 🔴 High (30% candidates) | 🔴 High (relevance) | ⚠️ Partial (FDA prompt) | 🔧 High |
| 4. Text overlays | 🟡 Medium (25% archive.org) | 🟡 Medium (unprofessional) | ✅ Fixed (VA + CB) | ✅ Done |
| 5. Wrong era | 🟡 Medium (10% candidates) | 🔴 High (factual error) | ⚠️ Partial (VA detects) | 🔧 Medium |
| 6. Low resolution | 🟢 Low (5% post-v14) | 🟡 Medium (quality) | ⚠️ Partial (CB gate) | 🔧 Low |
| 7. Black frames | 🟢 Low (8% archive.org) | 🔴 High (unusable) | ✅ Fixed (CB v3) | ✅ Done |
| 8. Random B-roll | 🟡 Medium (depends on stock) | 🟡 Medium (off-brand) | ❌ Not implemented | 🔧 Medium |
| 9. Consecutive repeats | 🟡 Medium (small pools) | 🟡 Medium (monotony) | ❌ Not implemented | 🔧 Low |
| 10. Zero clips created | 🟢 Low (<5% episodes) | 🔴 Critical (compilation fails) | ⚠️ By design (policy) | 🔧 Monitor |

### Recommended Next Actions

1. **High priority:** Tighten FDA prompt (issue #3)
   - Enforce "narration-first" keyword extraction
   - Stricter temporal anchor validation
   - Better scene type detection → smarter queries

2. **Medium priority:** Source preference by channel profile (issue #8)
   - Documentary channel → prefer Archive.org/Wikimedia (archival)
   - Educational channel → allow Pexels/Pixabay (modern stock)
   - Implement source scoring boost/penalty

3. **Low priority:** Diversity constraint (issue #9)
   - Track last 3 used assets per-beat
   - Penalty for consecutive repeats
   - Fallback if pool exhausted

---

## Debugging Workflows

### Per-Episode Audit

```bash
cd backend
python3 -c "
import json
with open('../projects/<episode_id>/archive_manifest.json') as f:
    m = json.load(f)

print('=== Quality Report ===')
print(f\"Pool videos: {len(m['episode_pool']['videos'])}\")
print(f\"Pool images: {len(m['episode_pool']['images'])}\")

# Check for issues
issues = []
for v in m['episode_pool']['videos']:
    if v.get('llm_analysis', {}).get('has_text_overlay'):
        issues.append(f\"Text overlay: {v['archive_item_id']}\")
    if v.get('llm_analysis', {}).get('relevance_score', 1.0) < 0.3:
        issues.append(f\"Low relevance: {v['archive_item_id']}\")

print(f\"Issues found: {len(issues)}\")
for i in issues[:10]:
    print(f\"  - {i}\")
"
```

### Real-time Monitoring (during AAR)

```bash
tail -f projects/<episode_id>/script_state.json | grep -E "(topic_rejected|duplicate_group|quality_issues)"
```

---

**Poslední update:** 3. ledna 2025  
**Next review:** Po 50+ production episodes (estimate Q1 2025)


