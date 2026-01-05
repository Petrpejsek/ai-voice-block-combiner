# SPECIFIKACE: Archive.org Content Filter (Games/Software/NSFW Block)

**Datum:** 3. ledna 2025  
**Úkol:** Zablokovat hry/software/ROMs a NSFW obsah z Archive.org před LLM deduplikací  
**Místo implementace:** `backend/video_sources.py` + `backend/archive_asset_resolver.py`

---

## 1. KDE PŘESNĚ IMPLEMENTOVAT

### Místo A: `video_sources.py` → `ArchiveOrgSource.search()`

**Soubor:** `backend/video_sources.py`  
**Funkce:** `ArchiveOrgSource.search()` (řádek ~141-258)  
**Přesné místo:** Hned za `for doc in docs:` loop (řádek ~185), **PŘED** licence gate

**Důvod:** Toto je entry point pro všechny Archive.org video/movie search calls přes multi-source searcher.

**Current flow:**
```python
docs = data.get("response", {}).get("docs", []) or []

for doc in docs:
    item_id = doc.get("identifier", "")
    if not item_id:
        continue
    
    # ⬅️ NOVÝ FILTER PŘIJDE SEM (před licence gate)
    
    license_raw = str(doc.get("licenseurl", "")).strip()
    license_normalized = self._normalize_license(license_raw)
    # ... licence gate logic ...
```

### Místo B: `archive_asset_resolver.py` → `search_archive_org()`

**Soubor:** `backend/archive_asset_resolver.py`  
**Funkce:** `search_archive_org()` (řádek ~1974-2200)  
**Přesné místo:** Po `for doc in docs:` loop (řádek ~2086), **PŘED** append do `raw_items`

**Důvod:** Toto je legacy AAR search používaný pro images + docs/maps stage.

**Current flow:**
```python
for doc in docs:
    identifier = doc.get("identifier", "")
    if not identifier:
        continue
    
    # ⬅️ NOVÝ FILTER PŘIJDE SEM (před raw_items.append)
    
    raw_items.append({
        "archive_item_id": identifier,
        "title": _norm_field(doc.get("title", "Untitled"), 240),
        # ...
    })
```

---

## 2. DOSTUPNÁ METADATA Z ARCHIVE.ORG API

### V `video_sources.py` (ArchiveOrgSource)

**API call:**
```python
params = {
    "q": f"({query}) AND mediatype:(movies OR movingimage)",
    "fl[]": ["identifier", "title", "description", "licenseurl", "downloads", "date"],
    "rows": 50,
    "output": "json"
}
```

**Dostupná pole v `doc`:**
- `identifier` (string)
- `title` (string)
- `description` (string)
- `licenseurl` (string)
- `downloads` (int)
- `date` (string)

**❌ CHYBÍ:** `collection`, `subject`, `mediatype`, `creator`

**⚠️ PROBLÉM:** Current API call **NEFETCHUJE** collection/subject/creator fields!

### V `archive_asset_resolver.py` (search_archive_org)

**API call:**
```python
params = {
    "q": f"({query_text_final}) AND mediatype:({mt})",
    "fl[]": ["identifier", "title", "description", "collection", "subject", "mediatype", "downloads", "date", "creator"],
    "rows": rows_requested,
    "output": "json"
}
```

**Dostupná pole v `doc`:**
- `identifier` (string)
- `title` (string)
- `description` (string)
- `collection` (string nebo list)
- `subject` (string nebo list)
- `mediatype` (string)
- `downloads` (int)
- `date` (string)
- `creator` (string nebo list)

**✅ KOMPLETNÍ:** Všechna potřebná pole jsou k dispozici.

---

## 3. IMPLEMENTAČNÍ PLÁN

### Krok 1: Rozšířit `fl[]` v `video_sources.py`

**Změna v:** `backend/video_sources.py` řádek ~148

**PŘED:**
```python
"fl[]": ["identifier", "title", "description", "licenseurl", "downloads", "date"],
```

**PO:**
```python
"fl[]": ["identifier", "title", "description", "licenseurl", "downloads", "date", "collection", "subject", "mediatype", "creator"],
```

### Krok 2: Definovat blacklist konstanty

**Přidat na začátek:** `backend/video_sources.py` (po imports, před VideoSource class)

```python
# ============================================================================
# ARCHIVE.ORG CONTENT FILTER - Anti-games/software + Anti-NSFW
# ============================================================================
# Blocks games/ROMs/software and NSFW content before deduplication.
# Matches case-insensitively on: title, description, collection, subject, creator, identifier

ARCHIVE_CONTENT_BLACKLIST_GAMES = {
    "sonic",
    "playstation",
    "ps1",
    "ps2", 
    "ps3",
    "ps4",
    "wii",
    "nintendo",
    "sega",
    "rom",
    "iso",
    "bin cue",
    "cue",
    "mame",
    "emulator",
    "game",
    "videogame",
    "software",
}

ARCHIVE_CONTENT_BLACKLIST_NSFW = {
    "porn",
    "xxx",
    "adult",
    "erotic",
    "nudity",
    "sex",
    "hustler",
    "playboy",
}

ARCHIVE_CONTENT_BLACKLIST_ALL = ARCHIVE_CONTENT_BLACKLIST_GAMES | ARCHIVE_CONTENT_BLACKLIST_NSFW

# Allowed mediatypes (strict allowlist)
ARCHIVE_ALLOWED_MEDIATYPES = {"movies", "image"}
```

### Krok 3: Vytvořit filter funkci

**Přidat do:** `backend/video_sources.py` (jako helper funkce před ArchiveOrgSource class)

```python
def _should_drop_archive_item(
    doc: Dict[str, Any],
    verbose: bool = False
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Checks if Archive.org item should be dropped (games/software/NSFW).
    
    Returns:
        (should_drop: bool, drop_reason: str, matched_term: str)
        
    Drop reasons:
        - DROP_MEDIATYPE: mediatype not in allowlist
        - DROP_BLACKLIST_GAMES: matched game/software term
        - DROP_BLACKLIST_NSFW: matched NSFW term
        - None: pass (do not drop)
    """
    # 1) Mediatype allowlist check
    mediatype = str(doc.get("mediatype", "")).strip().lower()
    if mediatype and mediatype not in ARCHIVE_ALLOWED_MEDIATYPES:
        return (True, "DROP_MEDIATYPE", mediatype)
    
    # 2) Extract all text fields (normalize: lowercase, handle lists)
    def _extract_text(field_name: str) -> str:
        val = doc.get(field_name, "")
        if isinstance(val, list):
            return " ".join([str(x).lower() for x in val if x])
        return str(val).lower()
    
    combined_text = " ".join([
        _extract_text("title"),
        _extract_text("description"),
        _extract_text("collection"),
        _extract_text("subject"),
        _extract_text("creator"),
        _extract_text("identifier"),
    ])
    
    # 3) Check NSFW blacklist (higher priority - most critical)
    for term in ARCHIVE_CONTENT_BLACKLIST_NSFW:
        # Word boundary match (avoid false positives like "Sussex")
        pattern = r'\b' + re.escape(term.lower()) + r'\b'
        if re.search(pattern, combined_text):
            return (True, "DROP_BLACKLIST_NSFW", term)
    
    # 4) Check games/software blacklist
    for term in ARCHIVE_CONTENT_BLACKLIST_GAMES:
        pattern = r'\b' + re.escape(term.lower()) + r'\b'
        if re.search(pattern, combined_text):
            return (True, "DROP_BLACKLIST_GAMES", term)
    
    return (False, None, None)
```

### Krok 4: Aplikovat filter v `ArchiveOrgSource.search()`

**Změna v:** `backend/video_sources.py` řádek ~185 (začátek `for doc in docs:` loop)

**VLOŽIT PO `if not item_id: continue`:**

```python
for doc in docs:
    item_id = doc.get("identifier", "")
    if not item_id:
        continue
    
    # ═══════════════════════════════════════════════════════════════
    # CONTENT FILTER: Block games/software/NSFW before license gate
    # ═══════════════════════════════════════════════════════════════
    should_drop, drop_reason, matched_term = _should_drop_archive_item(doc, verbose=self.verbose)
    if should_drop:
        # Collect for telemetry (track drops)
        if not hasattr(self, '_filter_drops'):
            self._filter_drops = []
        self._filter_drops.append({
            "identifier": item_id,
            "title": str(doc.get("title", ""))[:80],
            "reason": drop_reason,
            "matched_term": matched_term,
        })
        if self.verbose:
            print(f"  🚫 Archive.org: Dropped {item_id} ({drop_reason}: {matched_term})")
        continue
    # ═══════════════════════════════════════════════════════════════
    
    # Continue with existing license gate logic...
    license_raw = str(doc.get("licenseurl", "")).strip()
    # ...
```

### Krok 5: Aplikovat filter v `archive_asset_resolver.py`

**Změna v:** `backend/archive_asset_resolver.py` řádek ~2086 (začátek `for doc in docs:` loop)

**VLOŽIT PO `if not identifier: continue`:**

```python
for doc in docs:
    identifier = doc.get("identifier", "")
    if not identifier:
        continue
    
    # ═══════════════════════════════════════════════════════════════
    # CONTENT FILTER: Block games/software/NSFW
    # ═══════════════════════════════════════════════════════════════
    from video_sources import _should_drop_archive_item
    
    should_drop, drop_reason, matched_term = _should_drop_archive_item(doc, verbose=self.verbose)
    if should_drop:
        # Track for telemetry
        if not hasattr(self, '_content_filter_drops'):
            self._content_filter_drops = {}
        self._content_filter_drops.setdefault(drop_reason, []).append({
            "identifier": identifier,
            "title": _norm_field(doc.get("title", ""), 80),
            "matched_term": matched_term,
        })
        continue
    # ═══════════════════════════════════════════════════════════════
    
    # Continue with existing raw_items.append logic...
    raw_items.append({
        "archive_item_id": identifier,
        # ...
    })
```

---

## 4. TELEMETRIE & DIAGNOSTIKA

### Krok 6: Telemetrie v `video_sources.py`

**Přidat na KONEC `ArchiveOrgSource.search()` (před `return`):**

```python
# Telemetry: log filter stats
if hasattr(self, '_filter_drops'):
    drop_breakdown = {}
    for drop in self._filter_drops:
        reason = drop["reason"]
        drop_breakdown[reason] = drop_breakdown.get(reason, 0) + 1
    
    total_before = len(docs)
    total_after = len(safe_results) + len(unknown_results)
    total_dropped = len(self._filter_drops)
    
    if self.verbose:
        print(f"📊 Archive.org Content Filter:")
        print(f"   Before: {total_before} candidates")
        print(f"   After:  {total_after} candidates")
        print(f"   Dropped: {total_dropped} ({', '.join([f'{k}={v}' for k,v in drop_breakdown.items()])})")
    
    # Log to debug file
    try:
        import time as _time, json as _json
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "content-filter-v1",
                "location": "backend/video_sources.py:ArchiveOrgSource.search:content_filter",
                "message": "Archive.org content filter applied",
                "data": {
                    "query": query[:80],
                    "total_before": total_before,
                    "total_after": total_after,
                    "total_dropped": total_dropped,
                    "drop_breakdown": drop_breakdown,
                    "top_drops": self._filter_drops[:5],  # Top 5 dropped items
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    
    # Clear for next call
    self._filter_drops = []
```

### Krok 7: Telemetrie v `archive_asset_resolver.py`

**Přidat na KONEC `search_archive_org()` (před topic gates application):**

```python
# Telemetry: content filter stats
if hasattr(self, '_content_filter_drops'):
    total_dropped = sum(len(v) for v in self._content_filter_drops.values())
    if self.verbose and total_dropped > 0:
        print(f"  🚫 Content Filter: Dropped {total_dropped} items")
        for reason, items in self._content_filter_drops.items():
            print(f"     {reason}: {len(items)}")
    
    # Log to query attempt (existing telemetry system)
    self._log_query_attempt({
        "event": "content_filter_applied",
        "scene_id": self._log_context.get("scene_id", "unknown"),
        "query": query_text[:80],
        "pass": pass_name,
        "total_dropped": total_dropped,
        "drop_breakdown": {k: len(v) for k, v in self._content_filter_drops.items()},
        "top_drops": list(self._content_filter_drops.values())[0][:3] if self._content_filter_drops else [],
    })
    
    # Clear for next call
    self._content_filter_drops = {}
```

---

## 5. AKCEPTAČNÍ KRITÉRIA (Co musí platit po změně)

### Kritérium 1: Zero games/software v kandidátech

**Test:** Spusť episode na "Michael Jackson 2009"

**Assert:**
```python
# V archive_manifest.json → episode_pool.videos[]
for video in manifest['episode_pool']['videos']:
    title_lower = video['title'].lower()
    desc_lower = video.get('description', '').lower()
    
    # No game terms
    assert not any(term in title_lower for term in ["sonic", "playstation", "nintendo", "rom", "game"])
    assert not any(term in desc_lower for term in ["videogame", "emulator", "mame"])
    
    # No software mediatype (if mediatype field exists)
    if 'mediatype' in video:
        assert video['mediatype'] not in ['software', 'texts']  # texts = PDFs/software manuals
```

### Kritérium 2: Zero NSFW v kandidátech

**Test:** Stejná episode

**Assert:**
```python
for video in manifest['episode_pool']['videos']:
    combined = (video['title'] + " " + video.get('description', '')).lower()
    
    # No NSFW terms
    assert not any(term in combined for term in ["porn", "xxx", "adult", "erotic", "nudity", "sex"])
```

### Kritérium 3: Pipeline doběhne bez pádu

**Test:** Full pipeline run

**Assert:**
- `script_state.json` → `script_status == "DONE"`
- No Python exceptions
- Final video created: `output/episode_*.mp4` exists

### Kritérium 4: Telemetrie funguje

**Test:** Zkontroluj logs

**Assert:**
```bash
grep "content_filter_applied" .cursor/debug.log | tail -10
# Should show drop counts per query
```

**Expected log format:**
```json
{
  "message": "Archive.org content filter applied",
  "data": {
    "query": "Michael Jackson 2009",
    "total_before": 50,
    "total_after": 38,
    "total_dropped": 12,
    "drop_breakdown": {
      "DROP_BLACKLIST_GAMES": 8,
      "DROP_BLACKLIST_NSFW": 3,
      "DROP_MEDIATYPE": 1
    },
    "top_drops": [
      {"identifier": "sonic-adventure", "title": "Sonic Adventure gameplay", "reason": "DROP_BLACKLIST_GAMES", "matched_term": "sonic"},
      {"identifier": "ps2-racing", "title": "PS2 racing game footage", "reason": "DROP_BLACKLIST_GAMES", "matched_term": "ps2"}
    ]
  }
}
```

### Kritérium 5: Kvalita výsledků se zlepší

**Metrika:** Proportion of "news footage / archival docs" vs "random content"

**Before filter (očekávané):**
- 30-40% games/software/NSFW contaminace
- Top results include irrelevant ROMs, gameplay footage

**After filter (target):**
- 0% games/software/NSFW
- Top results: news clips, documentaries, historical footage

---

## 6. TEST PLÁN (Po implementaci)

### Test 1: Spusť 1 epizodu (MJ 2009)

**Command:**
```bash
cd backend
python3 test_archive_pipeline.py  # Nebo UI flow
```

### Test 2: Co pošleš zpátky (Output pro validaci)

#### A) Telemetrie summary
```
=== Content Filter Stats ===
Total queries executed: 15
Total candidates before filter: 450
Total candidates after filter: 380
Total dropped: 70

Drop breakdown:
  DROP_BLACKLIST_GAMES: 45
  DROP_BLACKLIST_NSFW: 18
  DROP_MEDIATYPE: 7
```

#### B) Top 10 výsledků PO filtru
```json
[
  {
    "archive_item_id": "mj-memorial-2009-cnn",
    "title": "Michael Jackson Memorial Service CNN Coverage 2009",
    "mediatype": "movies",
    "source": "archive_org"
  },
  {
    "archive_item_id": "jackson-this-is-it-rehearsal",
    "title": "This Is It rehearsal footage June 2009",
    "mediatype": "movingimage",
    "source": "archive_org"
  }
  // ... 8 more
]
```

#### C) Top 5 nejhorších dropnutých
```json
[
  {
    "identifier": "sonic-collection-dreamcast",
    "title": "Sonic Adventure DX Collection Dreamcast ISO",
    "reason": "DROP_BLACKLIST_GAMES",
    "matched_term": "sonic"
  },
  {
    "identifier": "playstation-magazine-2009",
    "title": "Playstation Magazine June 2009 PDF",
    "reason": "DROP_BLACKLIST_GAMES",
    "matched_term": "playstation"
  },
  {
    "identifier": "hustler-magazine-archive",
    "title": "Hustler Magazine Archive Collection",
    "reason": "DROP_BLACKLIST_NSFW",
    "matched_term": "hustler"
  }
  // ... 2 more
]
```

---

## 7. POZNÁMKY & EDGE CASES

### Edge Case 1: Multi-word terms (`"bin cue"`)

**Solution:** Regex word boundary match handles this:
```python
pattern = r'\b' + re.escape("bin cue") + r'\b'
# Matches: "file.bin cue sheet"
# Doesn't match: "combining curator"
```

### Edge Case 2: False positives (např. "Sussex", "Sonic boom")

**Current approach:** Word boundary match (`\b`) minimizes but doesn't eliminate.

**If needed later:** Add whitelist exceptions:
```python
WHITELIST_EXCEPTIONS = {"sonic boom", "sussex", "creator studio"}
```

### Edge Case 3: `mediatype` field missing

**Behavior:** Filter does NOT drop if mediatype is empty/missing (fail-open policy).

**Reason:** Some legitimate items have missing mediatype. Better to have false negatives (allow some bad) than false positives (block good content).

**If this causes issues:** Switch to fail-closed:
```python
if not mediatype:
    return (True, "DROP_MISSING_MEDIATYPE", "empty")
```

### Edge Case 4: Wikimedia/Europeana/Stock sources

**Important:** Tento filter se aplikuje **POUZE na Archive.org**.

**Důvod:**
- Wikimedia: Manually curated, unlikely to have games/NSFW
- Europeana: Cultural heritage, strict curation
- Pexels/Pixabay: Stock libraries, commercial safe

**If needed later:** Extend filter to other sources (implement in their respective `search()` methods).

---

## 8. PERFORMANCE IMPACT

**Expected overhead per query:**
- Regex match: ~0.1ms per candidate
- 50 candidates × 0.1ms = **5ms total** (negligible)

**Memory:** ~100 bytes per dropped item (telemetry) × max 50 drops = **5KB** (negligible)

**Network:** Zero extra API calls (uses existing metadata)

**Total impact:** <1% slowdown, within noise margin.

---

## 9. ROLLBACK PLAN

**If filter is too aggressive (blocks good content):**

### Option A: Disable via env var
```python
ENABLE_ARCHIVE_CONTENT_FILTER = os.getenv("AAR_ENABLE_CONTENT_FILTER", "1") == "1"

if ENABLE_ARCHIVE_CONTENT_FILTER:
    should_drop, drop_reason, matched_term = _should_drop_archive_item(doc)
    # ...
```

### Option B: Soften mediatype allowlist
```python
# Add "texts" for historical documents/maps
ARCHIVE_ALLOWED_MEDIATYPES = {"movies", "image", "texts"}
```

### Option C: Remove specific blacklist terms
```python
# If "game" is too broad (catches "game theory" documentaries)
ARCHIVE_CONTENT_BLACKLIST_GAMES.remove("game")
```

---

## 10. NEXT STEPS (PO TESTU)

**Pokud test projde:**
1. ✅ Content filter funguje → deploy to production
2. Monitor drop rates první týden (očekáváno: 10-20% drop rate)
3. Collect false positive reports (user feedback)

**Pokud jsou false positives:**
1. Whitelist exceptions pro common false positives
2. Soften blacklist (remove broad terms like "game")
3. Add positive signals (e.g., require "news" or "documentary" in title)

**Následující iterace (mentioned v user query):**
- **Netýká se tohoto úkolu:** FDA prompt refinement + query generator improvements
- Tohle děláme až po validaci content filteru

---

## SOUHRN ZMĚN

| Soubor | Funkce | Řádek | Změna |
|--------|--------|-------|-------|
| `video_sources.py` | Top-level | ~10 | Přidat blacklist konstanty |
| `video_sources.py` | Helper | ~50 | Přidat `_should_drop_archive_item()` funkci |
| `video_sources.py` | `ArchiveOrgSource.search()` | ~148 | Rozšířit `fl[]` o collection/subject/creator |
| `video_sources.py` | `ArchiveOrgSource.search()` | ~185 | Aplikovat filter v loop |
| `video_sources.py` | `ArchiveOrgSource.search()` | ~250 | Přidat telemetrii |
| `archive_asset_resolver.py` | `search_archive_org()` | ~2086 | Aplikovat filter v loop |
| `archive_asset_resolver.py` | `search_archive_org()` | ~2130 | Přidat telemetrii |

**Total LOC:** ~150 lines (100 filter logic + 50 telemetry)

**Estimated implementation time:** 30-45 minut  
**Testing time:** 10-15 minut (1 full episode run)

---

**Ready for implementation.** 🚀


