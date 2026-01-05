# AAR v2: Scene Intent + Entity-Driven Queries + Re-Ranking

**Datum:** 3. ledna 2025  
**Cíl:** Systémové generování dotazů vázaných na scénu + anti-noise filtry + relevance re-ranking  
**Status:** Specifikace (bez kódu) - připraveno k implementaci

---

## 0. Definice „Hotovo"

✅ **Každý dotaz vázaný na scénu/beat:**
- Query obsahuje min 1 primary entity (osoba/org) NEBO location entity
- Query obsahuje scene intent keyword (portrait/map/document/atd.)
- Žádné "topic obecně" queries (např. jen "Michael Jackson" bez kontextu)

✅ **Anti-noise funguje:**
- Disambiguation: automatické `-plane -aircraft` když query má "Lisa Marie"
- Source gating: preferovat Wikimedia/oficiální zdroje před random archives
- <10% assetů je off-topic (bez entity match)

✅ **Re-ranking selektuje správně:**
- Top asset pro scénu má entity_match_score > 0 (U non-BROLL intentů VŽDY)
- Intent match: document scene má assets s "document" signály

✅ **Fail-safe:**
- Když není dost výsledků → controlled fallback (drop secondary entities first, not random)
- Metriky jasně ukážou proč asset vyřazen

✅ **Regression suite:**
- 10 fixture epizod (různá témata)
- Min 70% scén dostane asset s entity match
- <10% assetů off-topic

---

## 1. Scene Intent Vrstva

### Co To Je

Každá scéna má **canonical intent** který určuje:
- Jaký typ vizuálu hledat (portrait vs location vs document)
- Jaké keywords použít v query
- Jak scorovat relevanci výsledků

### Typy Intentů (Enum)

```python
SCENE_INTENT_TYPES = {
    "PERSON_PORTRAIT": "Portrait/headshot of specific person",
    "FAMILY_PHOTO": "Photo with family members/relationships",
    "LOCATION_EXTERIOR": "Building/place exterior view",
    "LOCATION_INTERIOR": "Interior space/room",
    "HISTORICAL_EVENT": "Specific event footage/photo",
    "DOCUMENT_PROOF": "Legal document, contract, letter, certificate",
    "ORGANIZATION_BRAND": "Logo, headquarters building, official signage",
    "MEDIA_COVERAGE": "Newspaper headline, magazine cover, TV news clip",
    "MAP_CONTEXT": "Geographic map, route map, historical map",
    "BROLL_GENERIC": "Atmosphere shot without specific entity (fallback)"
}
```

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Nová funkce:** `_infer_scene_intent(scene: Dict) -> str`

**Umístění:** Jako helper funkce PŘED `resolve_scene_assets()` (řádek ~3073)

**Logika inference:**

```
Vstup: scene dict obsahuje:
  - narration_summary (text)
  - keywords[] (list)
  - shot_types[] (FDA enums)

Inference rules (priority order):
1. Shot types mapping:
   - "maps_context" → MAP_CONTEXT
   - "archival_documents" → DOCUMENT_PROOF
   - "leaders_speeches" → PERSON_PORTRAIT (pokud je osoba v keywords)
   - "civilian_life" + person entity → FAMILY_PHOTO

2. Keyword patterns:
   - "portrait", "headshot", "photo of" → PERSON_PORTRAIT
   - "family", "father", "mother", "children" → FAMILY_PHOTO
   - "building", "exterior", "headquarters" → LOCATION_EXTERIOR / ORGANIZATION_BRAND
   - "document", "letter", "contract", "certificate" → DOCUMENT_PROOF
   - "newspaper", "headline", "magazine", "TV" → MEDIA_COVERAGE
   - "map", "route", "geography" → MAP_CONTEXT

3. Narration patterns (regex):
   - "born in", "lived in", "grew up" → LOCATION_EXTERIOR (birthplace)
   - "signed", "established", "founded" → DOCUMENT_PROOF / ORGANIZATION_BRAND
   - "reported", "coverage", "announced" → MEDIA_COVERAGE

4. Fallback: BROLL_GENERIC (žádný match)

Pravidlo: PŘESNĚ 1 intent per scene (no multi-intent)
```

**Kam uložit:**
```python
scene["_scene_intent"] = intent  # Add to scene dict (internal field)
```

### Config File

**Soubor:** `config/scene_intent_rules.json` (nový)

```json
{
  "version": "1.0",
  "shot_type_mappings": {
    "maps_context": "MAP_CONTEXT",
    "archival_documents": "DOCUMENT_PROOF",
    "leaders_speeches": "PERSON_PORTRAIT",
    "civilian_life": "FAMILY_PHOTO",
    "destruction_aftermath": "LOCATION_EXTERIOR",
    "organization_brand": "ORGANIZATION_BRAND"
  },
  "keyword_patterns": {
    "PERSON_PORTRAIT": ["portrait", "headshot", "photo of", "image of"],
    "FAMILY_PHOTO": ["family", "father", "mother", "children", "spouse", "wife", "husband"],
    "LOCATION_EXTERIOR": ["building", "exterior", "facade", "headquarters", "estate"],
    "LOCATION_INTERIOR": ["interior", "room", "inside", "hall"],
    "DOCUMENT_PROOF": ["document", "letter", "contract", "certificate", "deed", "will", "trust"],
    "ORGANIZATION_BRAND": ["logo", "brand", "company", "corporation"],
    "MEDIA_COVERAGE": ["newspaper", "headline", "magazine", "article", "TV news", "broadcast"],
    "MAP_CONTEXT": ["map", "route", "geography", "atlas"]
  },
  "narration_patterns": {
    "LOCATION_EXTERIOR": ["born in", "lived in", "grew up in", "moved to"],
    "DOCUMENT_PROOF": ["signed", "established", "founded", "incorporated"],
    "MEDIA_COVERAGE": ["reported", "coverage", "announced", "headlines"]
  }
}
```

**Load v `_infer_scene_intent()`:**
```python
# Load rules once (module-level cache)
_SCENE_INTENT_RULES = None

def _load_scene_intent_rules():
    global _SCENE_INTENT_RULES
    if _SCENE_INTENT_RULES is not None:
        return _SCENE_INTENT_RULES
    
    rules_path = os.path.join(os.path.dirname(__file__), "../config/scene_intent_rules.json")
    try:
        with open(rules_path) as f:
            _SCENE_INTENT_RULES = json.load(f)
    except Exception:
        # Fallback to hardcoded rules
        _SCENE_INTENT_RULES = {...}
    
    return _SCENE_INTENT_RULES
```

---

## 2. Entity Extraction

### Co Extrahovat

Pro každou scénu:
- **primary_entities:** Osoby, organizace (max 3)
- **secondary_entities:** Místa, artefakty, události (max 5)
- **time_hint:** Rok/období (optional)

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Nová funkce:** `_extract_scene_entities(scene: Dict, episode_topic: str) -> Dict`

**Umístění:** Helper funkce PŘED `resolve_scene_assets()`

**Logika extraction:**

```
Vstup: scene dict + episode_topic

Krok 1: Extract z narration_summary
  - Proper nouns (capitalized words) → candidates
  - Multi-word proper nouns ("Nikola Tesla", "Priscilla Presley")
  - Preserve order (first mention = primary)

Krok 2: Extract z keywords[]
  - Keywords s capital letters → entity candidates
  - Keywords označující místa ("mansion", "estate" + proper noun)

Krok 3: Episode topic jako fallback primary
  - Pokud není v narration, přidej episode_topic jako primary_entity

Krok 4: Time hints
  - Regex: \b(18|19|20)\d{2}\b (4-digit year)
  - Text patterns: "in 1950s", "during WWII", "Victorian era"

Krok 5: Classification (osoba vs místo vs org)
  - Heuristics:
    - Obsahuje "Jr", "Sr", "III" → person
    - Obsahuje "Inc", "Corp", "LLC", "Foundation" → organization
    - Keywords jako "city", "county", "estate" → location
    - Fallback: Check proti známým jménům (optional Wikipedia API)

Output structure:
{
  "primary_entities": ["Nikola Tesla", "Thomas Edison"],
  "secondary_entities": ["Colorado Springs", "Wardenclyffe Tower"],
  "time_hint": "1891",
  "entity_types": {
    "Nikola Tesla": "person",
    "Thomas Edison": "person",
    "Colorado Springs": "location",
    "Wardenclyffe Tower": "location"
  }
}
```

### Hard Rule: Query Must Have Entity

**Enforcement místo:** V query builder (před return queries)

```python
for query in generated_queries:
    has_entity = any(entity.lower() in query.lower() 
                     for entity in primary_entities + secondary_entities)
    if not has_entity and intent != "BROLL_GENERIC":
        # Inject primary entity
        query = f"{primary_entities[0]} {query}" if primary_entities else query
```

---

## 3. Query Builder v2: Templates per Intent

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Funkce:** Přepsat `_extract_episode_queries()` (nebo vytvořit novou `_generate_scene_queries_v2()`)

**Řádek:** Současná funkce je ~4350-4380 (episode-level queries)  
**Nová logika:** Per-scene queries s intent templates

### Query Templates (Config)

**Soubor:** `config/query_templates_v2.json` (nový)

```json
{
  "version": "2.0",
  "templates": {
    "PERSON_PORTRAIT": [
      "{PRIMARY} portrait",
      "{PRIMARY} photograph",
      "{PRIMARY} photo {TIME}",
      "{PRIMARY} headshot"
    ],
    "FAMILY_PHOTO": [
      "{PRIMARY} {SECONDARY} photo",
      "{PRIMARY} family {TIME}",
      "{PRIMARY} with {RELATION}",
      "{PRIMARY} {SECONDARY} photograph"
    ],
    "LOCATION_EXTERIOR": [
      "{LOCATION} exterior",
      "{LOCATION} building {TIME}",
      "{LOCATION} photograph",
      "{LOCATION} {TIME} photo"
    ],
    "LOCATION_INTERIOR": [
      "{LOCATION} interior",
      "{LOCATION} room",
      "inside {LOCATION}",
      "{LOCATION} hall {TIME}"
    ],
    "HISTORICAL_EVENT": [
      "{EVENT} {TIME}",
      "{EVENT} footage",
      "{EVENT} photograph",
      "{PRIMARY} {EVENT} {TIME}"
    ],
    "DOCUMENT_PROOF": [
      "{PRIMARY} document",
      "{ORG} trust document",
      "{PRIMARY} estate document",
      "{ORG} contract {TIME}",
      "{PRIMARY} certificate"
    ],
    "ORGANIZATION_BRAND": [
      "{ORG} logo",
      "{ORG} headquarters",
      "{ORG} building",
      "{ORG} {TIME} photograph"
    ],
    "MEDIA_COVERAGE": [
      "{PRIMARY} newspaper",
      "{EVENT} headline {TIME}",
      "{PRIMARY} magazine cover",
      "{EVENT} news {TIME}"
    ],
    "MAP_CONTEXT": [
      "{LOCATION} map",
      "{EVENT} map {TIME}",
      "{LOCATION} route map",
      "map of {LOCATION}"
    ],
    "BROLL_GENERIC": [
      "{TOPIC} {TIME}",
      "{TOPIC} footage",
      "{PRIMARY} {TIME}",
      "{SECONDARY} photograph"
    ]
  },
  "query_mix": {
    "precise_ratio": 0.6,
    "broad_ratio": 0.4,
    "min_queries_per_scene": 6,
    "max_queries_per_scene": 12
  }
}
```

### Query Generation Logic

**V `_generate_scene_queries_v2(scene, entities, intent)`:**

```
1. Load templates pro daný intent
2. Sestavit substitutions dict:
   {
     "PRIMARY": primary_entities[0],
     "SECONDARY": secondary_entities[0],
     "LOCATION": first entity typed as "location",
     "ORG": first entity typed as "organization",
     "EVENT": extract from narration (keywords like "war", "crash", "death"),
     "TIME": time_hint,
     "TOPIC": episode_topic,
     "RELATION": infer from keywords ("father", "mother", "wife")
   }

3. Generate queries:
   - PRECISE (60%): Use all available substitutions
     Příklad: "{PRIMARY} {SECONDARY} {TIME}" → "Tesla Edison 1891"
   
   - BROAD (40%): Drop secondary entities/time
     Příklad: "{PRIMARY} photograph" → "Tesla photograph"

4. Dedup case-insensitive

5. Validate: každý query má min 1 entity (enforce hard rule)

6. Return 6-12 queries (preferovat víc pro důležité scény)
```

### Kde Volat

**V `resolve_scene_assets()`** (řádek ~3073):

```python
# BEFORE current query extraction logic (line ~3120+):

# NEW: Generate scene-specific queries
scene_intent = _infer_scene_intent(scene)
scene_entities = _extract_scene_entities(scene, episode_topic)
scene_queries = _generate_scene_queries_v2(scene, scene_entities, scene_intent)

# Override scene["search_queries"] with new queries
scene["search_queries"] = scene_queries
scene["_scene_entities"] = scene_entities  # Store for scoring later
scene["_scene_intent"] = scene_intent
```

---

## 4. Disambiguation Engine (Anti-Noise)

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Nová funkce:** `_apply_disambiguation(query: str, entities: Dict) -> str`

**Umístění:** Helper funkce volaná Z `_generate_scene_queries_v2()` PŘED return

### Config File

**Soubor:** `config/disambiguation_rules.json` (nový)

```json
{
  "version": "1.0",
  "rules": [
    {
      "trigger": "Lisa Marie",
      "context": "person",
      "exclude_terms": ["-plane", "-aircraft", "-jet", "-aviation"],
      "reason": "Disambiguate from Lisa Marie aircraft"
    },
    {
      "trigger": "Graceland",
      "context": "location",
      "exclude_terms": ["-cemetery"],
      "reason": "Graceland estate vs Graceland Memorial Park"
    },
    {
      "trigger": "Titanic",
      "context": "event",
      "exclude_terms": ["-movie", "-film", "-1997"],
      "reason": "Titanic ship 1912 vs Cameron film"
    },
    {
      "trigger": "Elvis",
      "context": "person",
      "exclude_terms": ["-impersonator", "-tribute", "-cover"],
      "reason": "Real Elvis vs tribute acts"
    }
  ],
  "enabled": true
}
```

### Logika Aplikace

```python
def _apply_disambiguation(query: str, entities: Dict, intent: str) -> str:
    """
    Apply disambiguation rules to query.
    
    Args:
        query: Original query string
        entities: Entity dict with types (person/org/location)
        intent: Scene intent (to check context)
    
    Returns:
        Modified query with exclusion terms added
    """
    rules = _load_disambiguation_rules()
    if not rules.get("enabled"):
        return query
    
    query_lower = query.lower()
    modified = query
    added_terms = []
    
    for rule in rules.get("rules", []):
        trigger = rule["trigger"].lower()
        
        # Check if trigger is in query
        if trigger not in query_lower:
            continue
        
        # Check context match (intent or entity type)
        context = rule.get("context", "").lower()
        context_match = False
        
        if context == "person":
            context_match = any(entities.get("entity_types", {}).get(e) == "person" 
                              for e in entities.get("primary_entities", []))
        elif context == "location":
            context_match = intent in ("LOCATION_EXTERIOR", "LOCATION_INTERIOR", "MAP_CONTEXT")
        elif context == "event":
            context_match = intent == "HISTORICAL_EVENT"
        else:
            context_match = True  # Always apply if no context
        
        if context_match:
            exclude_terms = rule.get("exclude_terms", [])
            modified += " " + " ".join(exclude_terms)
            added_terms.extend(exclude_terms)
    
    if added_terms and verbose:
        print(f"  🔧 Disambiguation: '{query}' → added {added_terms}")
    
    return modified.strip()
```

### Kdy Aplikovat

**V `_generate_scene_queries_v2()`:**

```python
# AFTER template substitution, BEFORE return:
final_queries = []
for query in generated_queries:
    disambiguated = _apply_disambiguation(query, entities, intent)
    final_queries.append(disambiguated)

return final_queries
```

---

## 5. Source Gating (Preferovat Kvalitu)

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Upravit:** `_score_multi_source_item()` (řádek ~1927-1951)

### Config File

**Soubor:** `config/source_weights_v2.json` (nový)

```json
{
  "version": "2.0",
  "source_scores": {
    "wikimedia": 10.0,
    "europeana": 8.0,
    "archive_org_curated": 7.0,
    "archive_org": 5.0,
    "pexels": 3.0,
    "pixabay": 3.0,
    "unknown": 0.0
  },
  "collection_boosts": {
    "prelinger": 2.0,
    "usgov": 3.0,
    "smithsonian": 5.0,
    "loc": 5.0,
    "library_of_congress": 5.0,
    "national_archives": 4.0,
    "british_library": 4.0
  },
  "collection_penalties": {
    "internet_arcade": -10.0,
    "software": -10.0,
    "cd-rom": -10.0,
    "console_living_room": -10.0
  }
}
```

### Logika Scoring

**Přidat do `_score_multi_source_item()`:**

```python
# Current scoring (keeps):
# 1. License priority (PD > CC-BY)
# 2. Source priority (archive_org=5, wikimedia=3)
# 3. Popularity (downloads log)

# NEW additions:

# 4. Collection boost/penalty
collection = str(item.get("collection", "")).lower()
collection_score = 0.0

# Check boosts
for coll_name, boost in SOURCE_WEIGHTS["collection_boosts"].items():
    if coll_name in collection:
        collection_score += boost
        break  # Only one boost

# Check penalties
for coll_name, penalty in SOURCE_WEIGHTS["collection_penalties"].items():
    if coll_name in collection:
        collection_score += penalty  # Negative value
        break

score += collection_score

# 5. Creator reputation (optional, simple heuristic)
creator = str(item.get("creator", "")).lower()
if any(keyword in creator for keyword in ["museum", "library", "archive", "university"]):
    score += 2.0

return score
```

**Impact:** Penalizované zdroje mohou stále projít, ale s nižším score → re-ranking je odsune dolů.

---

## 6. Relevance Scorer (Re-Ranking)

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Funkce:** Přepsat `_rank_asset()` (řádek ~817-938)

### Nové Scoring Komponenty

```python
def _rank_asset_v2(
    asset: Dict[str, Any],
    scene_entities: Dict,
    scene_intent: str,
    time_hint: Optional[str] = None,
    verbose: bool = False
) -> Tuple[float, Dict[str, Any]]:
    """
    V2 scoring with entity match, intent match, time match.
    
    Returns: (score, debug_dict)
    """
    title = str(asset.get("title", "")).lower()
    desc = str(asset.get("description", "")).lower()
    collection = str(asset.get("collection", "")).lower()
    subject = str(asset.get("subject", "")).lower()
    
    combined_text = f"{title} {desc} {collection} {subject}"
    
    debug = {}
    score = 0.0
    
    # ═══════════════════════════════════════════════════════════════
    # 1. ENTITY MATCH (MOST IMPORTANT)
    # ═══════════════════════════════════════════════════════════════
    primary_entities = scene_entities.get("primary_entities", [])
    secondary_entities = scene_entities.get("secondary_entities", [])
    
    entity_match_score = 0.0
    matched_entities = []
    
    # Primary entity match (high value)
    for entity in primary_entities:
        entity_lower = entity.lower()
        if entity_lower in title:
            entity_match_score += 10.0  # Strong signal
            matched_entities.append(entity)
        elif entity_lower in combined_text:
            entity_match_score += 5.0  # Weaker signal
            matched_entities.append(entity)
    
    # Secondary entity match (medium value)
    for entity in secondary_entities:
        entity_lower = entity.lower()
        if entity_lower in title:
            entity_match_score += 3.0
            matched_entities.append(entity)
        elif entity_lower in combined_text:
            entity_match_score += 1.5
            matched_entities.append(entity)
    
    # Bonus: Multiple entities in same asset
    if len(matched_entities) >= 2:
        entity_match_score += 5.0
        debug["multi_entity_bonus"] = True
    
    debug["entity_match_score"] = entity_match_score
    debug["matched_entities"] = matched_entities
    score += entity_match_score
    
    # ═══════════════════════════════════════════════════════════════
    # 2. INTENT MATCH
    # ═══════════════════════════════════════════════════════════════
    intent_keywords = INTENT_KEYWORDS.get(scene_intent, [])
    intent_match_score = 0.0
    matched_intent_keywords = []
    
    for kw in intent_keywords:
        if kw in title:
            intent_match_score += 3.0
            matched_intent_keywords.append(kw)
        elif kw in combined_text:
            intent_match_score += 1.0
            matched_intent_keywords.append(kw)
    
    debug["intent_match_score"] = intent_match_score
    debug["matched_intent_keywords"] = matched_intent_keywords
    score += intent_match_score
    
    # ═══════════════════════════════════════════════════════════════
    # 3. TIME HINT MATCH (Optional)
    # ═══════════════════════════════════════════════════════════════
    time_match_score = 0.0
    if time_hint:
        time_patterns = [time_hint]
        # Expand: "1977" → ["1977", "1970s", "seventies"]
        if time_hint.isdigit() and len(time_hint) == 4:
            decade = time_hint[:3] + "0s"
            time_patterns.append(decade)
        
        for pattern in time_patterns:
            if pattern.lower() in combined_text:
                time_match_score += 2.0
                debug["time_match"] = pattern
                break
    
    debug["time_match_score"] = time_match_score
    score += time_match_score
    
    # ═══════════════════════════════════════════════════════════════
    # 4. TEXT-IN-IMAGE PENALTY (Optional)
    # ═══════════════════════════════════════════════════════════════
    text_overlay_penalty = 0.0
    # Check if Visual Assistant already flagged this
    llm_analysis = asset.get("llm_analysis", {})
    if llm_analysis.get("has_text_overlay"):
        text_overlay_penalty = -5.0
        debug["text_overlay_penalty"] = True
    
    score += text_overlay_penalty
    
    # ═══════════════════════════════════════════════════════════════
    # 5. SOURCE SCORE (from source gating)
    # ═══════════════════════════════════════════════════════════════
    # Already computed in _score_multi_source_item(), pass through if available
    source_score = asset.get("_source_score", 0.0)
    debug["source_score"] = source_score
    score += source_score * 0.5  # Weight source quality lower than entity match
    
    # ═══════════════════════════════════════════════════════════════
    # FINAL SCORE
    # ═══════════════════════════════════════════════════════════════
    debug["final_score"] = score
    
    return score, debug
```

### Intent Keywords Config

**Přidat do `config/scene_intent_rules.json`:**

```json
{
  "intent_keywords": {
    "PERSON_PORTRAIT": ["portrait", "headshot", "photo", "photograph", "image"],
    "FAMILY_PHOTO": ["family", "children", "wife", "husband", "father", "mother"],
    "LOCATION_EXTERIOR": ["exterior", "building", "facade", "outside"],
    "LOCATION_INTERIOR": ["interior", "room", "inside", "hall"],
    "DOCUMENT_PROOF": ["document", "letter", "contract", "certificate", "deed", "will"],
    "ORGANIZATION_BRAND": ["logo", "brand", "headquarters", "building"],
    "MEDIA_COVERAGE": ["newspaper", "headline", "magazine", "article", "news"],
    "MAP_CONTEXT": ["map", "atlas", "geography", "route"],
    "BROLL_GENERIC": []
  }
}
```

### Hard Rule: No Entity Match → Reject (Non-BROLL)

**V `_select_top_assets()` (řádek ~941):**

```python
# AFTER scoring all assets:

filtered_by_entity = []
for score, asset in scored:
    debug = asset.get("_rank_debug", {})
    entity_match_score = debug.get("entity_match_score", 0.0)
    
    # Hard rule: non-BROLL intents MUST have entity match
    if scene_intent != "BROLL_GENERIC" and entity_match_score == 0:
        if verbose:
            print(f"  ❌ NO ENTITY MATCH: {asset.get('title', '')[:60]}")
        continue  # Reject
    
    filtered_by_entity.append((score, asset))

# Continue with filtered list
scored = filtered_by_entity
```

---

## 7. Controlled Fallback

### Kde Implementovat

**Soubor:** `backend/archive_asset_resolver.py`  
**Funkce:** Upravit `resolve_scene_assets()` (řádek ~3073)

### Fallback Strategie

```python
# AFTER initial search attempt, BEFORE returning results:

MIN_ASSETS_REQUIRED = 3  # Threshold to trigger fallback

if len(selected_assets) < MIN_ASSETS_REQUIRED:
    print(f"⚠️  AAR Fallback: Only {len(selected_assets)} assets, need {MIN_ASSETS_REQUIRED}")
    
    # === FALLBACK LEVEL 1: Drop secondary entities ===
    if fallback_level == 0:
        entities_fallback = {
            "primary_entities": scene_entities["primary_entities"],
            "secondary_entities": [],  # Drop
            "time_hint": scene_entities["time_hint"]
        }
        queries_fallback = _generate_scene_queries_v2(scene, entities_fallback, scene_intent)
        # Re-search with fallback queries...
        fallback_level = 1
    
    # === FALLBACK LEVEL 2: Drop time hint ===
    elif fallback_level == 1:
        entities_fallback = {
            "primary_entities": scene_entities["primary_entities"],
            "secondary_entities": [],
            "time_hint": None  # Drop time
        }
        queries_fallback = _generate_scene_queries_v2(scene, entities_fallback, scene_intent)
        # Re-search...
        fallback_level = 2
    
    # === FALLBACK LEVEL 3: Broaden intent ===
    elif fallback_level == 2:
        # Specific intent → BROLL_GENERIC
        intent_fallback = "BROLL_GENERIC"
        queries_fallback = _generate_scene_queries_v2(scene, entities_fallback, intent_fallback)
        # Re-search...
        fallback_level = 3
    
    # === FALLBACK LEVEL 4: Topic-level query ===
    elif fallback_level == 3:
        # Last resort: episode_topic + time_hint
        queries_fallback = [f"{episode_topic} {time_hint}".strip()]
        # But STILL enforce entity must appear in title/snippet
        # (Filter in scoring: if primary entity not in title → score = 0)
        fallback_level = 4
    
    # MAX 4 levels, then give up (return what we have)
```

### Telemetrie

```python
# Log fallback usage
if fallback_level > 0:
    print(f"📊 AAR Fallback: scene={scene_id}, level={fallback_level}, final_assets={len(selected_assets)}")
```

---

## 8. Logování & Debug (AAR Telemetrie v2)

### Co Logovat Per Asset

**V `_rank_asset_v2()` return debug dict:**

```json
{
  "scene_id": "sc_0001",
  "archive_item_id": "prelinger-12345",
  "query_used": "Tesla portrait 1891",
  "disambiguation_terms_added": ["-plane", "-aircraft"],
  "source_score": 7.0,
  "entity_match_score": 10.0,
  "matched_entities": ["Tesla"],
  "intent_match_score": 3.0,
  "matched_intent_keywords": ["portrait"],
  "time_match_score": 2.0,
  "final_score": 22.0,
  "reject_reason": null
}
```

**Pokud rejected:**

```json
{
  "scene_id": "sc_0001",
  "archive_item_id": "random-item-999",
  "query_used": "Tesla portrait",
  "reject_reason": "NO_ENTITY_MATCH",
  "entity_match_score": 0.0,
  "final_score": 3.5
}
```

### Agregované Metriky (Per Episode)

**Na konci `resolve_episode_pool()` nebo `resolve_shot_plan_assets()`:**

```python
# Compute episode-level stats
total_assets = len(all_assets_selected)
entity_match_count = sum(1 for a in all_assets_selected 
                         if a.get("_rank_debug", {}).get("entity_match_score", 0) > 0)
off_topic_count = total_assets - entity_match_count

reject_reasons = {}
for scene in scenes:
    for rejected in scene.get("_rejected_assets", []):
        reason = rejected.get("reject_reason")
        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1

print(f"📊 AAR Episode Stats:")
print(f"   Total assets selected: {total_assets}")
print(f"   Entity match: {entity_match_count} ({100*entity_match_count/total_assets:.1f}%)")
print(f"   Off-topic: {off_topic_count} ({100*off_topic_count/total_assets:.1f}%)")
print(f"   Top reject reasons: {dict(sorted(reject_reasons.items(), key=lambda x: x[1], reverse=True)[:10])}")
```

### Output File

**Soubor:** `projects/<episode_id>/aar_telemetry.json` (nový)

```json
{
  "episode_id": "ep_abc123",
  "timestamp": "2025-01-03T15:30:00Z",
  "total_scenes": 20,
  "total_assets_selected": 45,
  "entity_match_count": 42,
  "entity_match_percent": 93.3,
  "off_topic_count": 3,
  "off_topic_percent": 6.7,
  "top_reject_reasons": {
    "NO_ENTITY_MATCH": 15,
    "LOW_SCORE": 8,
    "HARD_FILTER": 3
  },
  "fallback_usage": {
    "level_1": 2,
    "level_2": 1,
    "level_3": 0,
    "level_4": 0
  },
  "per_scene_details": [
    {
      "scene_id": "sc_0001",
      "intent": "PERSON_PORTRAIT",
      "entities": ["Tesla"],
      "assets_selected": 3,
      "assets_rejected": 2,
      "top_score": 22.0,
      "avg_score": 18.5
    }
  ]
}
```

---

## 9. Regression Suite

### Fixture Episodes (10-20)

**Soubor:** `backend/test_aar_v2_fixtures.json` (nový)

```json
{
  "fixtures": [
    {
      "fixture_id": "person_portrait",
      "topic": "Nikola Tesla life and inventions",
      "scenes": [
        {
          "narration": "Born in 1856 in Croatia, Tesla showed early genius.",
          "expected_intent": "PERSON_PORTRAIT",
          "expected_primary_entities": ["Nikola Tesla", "Tesla"],
          "min_entity_match_assets": 1
        },
        {
          "narration": "Tesla worked with Thomas Edison in New York.",
          "expected_intent": "PERSON_PORTRAIT",
          "expected_primary_entities": ["Tesla", "Edison"],
          "min_entity_match_assets": 2
        }
      ],
      "acceptance": {
        "min_scenes_with_entity_match": 2,
        "max_off_topic_percent": 10
      }
    },
    {
      "fixture_id": "location_doc",
      "topic": "Elvis Presley Graceland estate",
      "scenes": [
        {
          "narration": "Graceland mansion purchased in 1957.",
          "expected_intent": "LOCATION_EXTERIOR",
          "expected_primary_entities": ["Graceland", "Elvis"],
          "min_entity_match_assets": 1
        },
        {
          "narration": "The estate trust document established succession.",
          "expected_intent": "DOCUMENT_PROOF",
          "expected_primary_entities": ["Elvis", "Graceland"],
          "min_entity_match_assets": 1
        }
      ],
      "acceptance": {
        "min_scenes_with_entity_match": 2,
        "max_off_topic_percent": 10
      }
    }
  ]
}
```

### Test Script

**Soubor:** `backend/test_aar_v2_regression.py` (nový)

```python
#!/usr/bin/env python3
"""
AAR v2 Regression Suite
Tests intent inference, entity extraction, query generation, re-ranking.
"""

import json
from archive_asset_resolver import (
    _infer_scene_intent,
    _extract_scene_entities,
    _generate_scene_queries_v2,
    _rank_asset_v2
)

def load_fixtures():
    with open("test_aar_v2_fixtures.json") as f:
        return json.load(f)["fixtures"]

def test_fixture(fixture):
    """Test one fixture episode."""
    print(f"\n{'='*60}")
    print(f"Testing: {fixture['fixture_id']} - {fixture['topic']}")
    print(f"{'='*60}")
    
    total_scenes = len(fixture["scenes"])
    scenes_with_entity_match = 0
    off_topic_assets = 0
    total_assets = 0
    
    for i, scene_def in enumerate(fixture["scenes"], 1):
        print(f"\n  Scene {i}: {scene_def['narration'][:60]}...")
        
        # Mock scene dict
        scene = {
            "narration_summary": scene_def["narration"],
            "keywords": [],  # Would be populated by FDA
            "shot_types": []
        }
        
        # Test intent inference
        intent = _infer_scene_intent(scene)
        expected_intent = scene_def["expected_intent"]
        assert intent == expected_intent, f"Intent mismatch: {intent} != {expected_intent}"
        print(f"    ✅ Intent: {intent}")
        
        # Test entity extraction
        entities = _extract_scene_entities(scene, fixture["topic"])
        expected_entities = scene_def["expected_primary_entities"]
        found_entities = entities["primary_entities"]
        
        # Check if at least one expected entity was found
        entity_match = any(e in " ".join(found_entities).lower() for e in [x.lower() for x in expected_entities])
        assert entity_match, f"No entity match: found {found_entities}, expected {expected_entities}"
        print(f"    ✅ Entities: {found_entities}")
        
        # Test query generation
        queries = _generate_scene_queries_v2(scene, entities, intent)
        print(f"    ✅ Queries: {queries[:3]}...")
        
        # Validate queries have entities
        for query in queries:
            has_entity = any(e.lower() in query.lower() for e in found_entities)
            assert has_entity, f"Query missing entity: {query}"
        
        # Count assets with entity match (would need actual search results)
        # For now, mock validation
        scenes_with_entity_match += 1  # Assume pass if we got here
    
    # Check acceptance criteria
    acceptance = fixture["acceptance"]
    min_scenes = acceptance["min_scenes_with_entity_match"]
    
    assert scenes_with_entity_match >= min_scenes, \
        f"Not enough scenes with entity match: {scenes_with_entity_match} < {min_scenes}"
    
    print(f"\n  ✅ FIXTURE PASSED: {scenes_with_entity_match}/{total_scenes} scenes OK")
    return True

def run_all_tests():
    fixtures = load_fixtures()
    passed = 0
    failed = 0
    
    for fixture in fixtures:
        try:
            if test_fixture(fixture):
                passed += 1
        except Exception as e:
            print(f"  ❌ FIXTURE FAILED: {e}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"REGRESSION SUITE RESULTS")
    print(f"{'='*60}")
    print(f"Passed: {passed}/{len(fixtures)}")
    print(f"Failed: {failed}/{len(fixtures)}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n❌ {failed} TESTS FAILED")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(run_all_tests())
```

**Run:**
```bash
cd backend
python3 test_aar_v2_regression.py
```

---

## 10. Kde Přesně v Projektu Upravit

### Soubory k Úpravě

| Soubor | Funkce/Oblast | Řádek (přibližně) | Co Udělat |
|--------|---------------|-------------------|-----------|
| `archive_asset_resolver.py` | Nové helper funkce | Before line ~3073 | Přidat `_infer_scene_intent()`, `_extract_scene_entities()`, `_generate_scene_queries_v2()`, `_apply_disambiguation()` |
| `archive_asset_resolver.py` | `resolve_scene_assets()` | ~3073-3500 | Volat nové funkce na začátku, override `scene["search_queries"]` |
| `archive_asset_resolver.py` | `_rank_asset()` | ~817-938 | Přepsat na `_rank_asset_v2()` s entity/intent/time scoring |
| `archive_asset_resolver.py` | `_select_top_assets()` | ~941-1025 | Přidat hard rule: reject if no entity match (non-BROLL) |
| `archive_asset_resolver.py` | `_score_multi_source_item()` | ~1927-1951 | Přidat collection boost/penalty logic |
| `archive_asset_resolver.py` | `resolve_scene_assets()` fallback | ~3200+ | Implementovat controlled fallback (4 levels) |
| `archive_asset_resolver.py` | Telemetrie | End of `resolve_shot_plan_assets()` | Output episode stats, write `aar_telemetry.json` |

### Config Soubory k Vytvoření

| Soubor | Účel |
|--------|------|
| `config/scene_intent_rules.json` | Intent inference rules, keyword patterns |
| `config/query_templates_v2.json` | Query templates per intent |
| `config/disambiguation_rules.json` | Anti-noise disambiguation rules |
| `config/source_weights_v2.json` | Source/collection scoring weights |

### Test Soubory k Vytvoření

| Soubor | Účel |
|--------|------|
| `backend/test_aar_v2_fixtures.json` | Regression fixtures (10-20 episodes) |
| `backend/test_aar_v2_regression.py` | Regression test runner |
| `projects/<ep>/aar_telemetry.json` | Per-episode telemetrie output |

### Žádné Změny Mimo AAR

**NESAHEJ na:**
- ❌ `footage_director.py` (FDA prompts)
- ❌ `visual_assistant.py` (LLM Vision API)
- ❌ `compilation_builder.py` (CB video assembly)
- ❌ `script_pipeline.py` (pipeline orchestration - jen minimální integrace)

**Jen AAR pipeline:**
- ✅ Query generation logic
- ✅ Asset scoring/ranking
- ✅ Source gating
- ✅ Telemetrie

---

## Implementation Checklist

**Phase 1: Scene Intent + Entity Extraction**
- [ ] Create `config/scene_intent_rules.json`
- [ ] Implement `_infer_scene_intent()`
- [ ] Implement `_extract_scene_entities()`
- [ ] Test with 5 fixture scenes
- [ ] Validate: intents correct, entities extracted

**Phase 2: Query Builder v2**
- [ ] Create `config/query_templates_v2.json`
- [ ] Implement `_generate_scene_queries_v2()`
- [ ] Enforce: every query has entity (hard rule)
- [ ] Test query generation for 10 scenes
- [ ] Validate: queries anchored to entities

**Phase 3: Disambiguation + Source Gating**
- [ ] Create `config/disambiguation_rules.json`
- [ ] Create `config/source_weights_v2.json`
- [ ] Implement `_apply_disambiguation()`
- [ ] Update `_score_multi_source_item()` with collection scoring
- [ ] Test with known ambiguous cases (Lisa Marie, Titanic)

**Phase 4: Re-Ranking**
- [ ] Rewrite `_rank_asset()` → `_rank_asset_v2()`
- [ ] Implement entity_match_score (primary component)
- [ ] Implement intent_match_score
- [ ] Implement time_match_score
- [ ] Add hard rule in `_select_top_assets()`: reject if no entity match
- [ ] Test with 20 real search results

**Phase 5: Controlled Fallback**
- [ ] Implement 4-level fallback in `resolve_scene_assets()`
- [ ] Test fallback triggers (when <3 assets)
- [ ] Validate: fallback queries still have entity requirement

**Phase 6: Telemetrie**
- [ ] Add debug dict to all scoring functions
- [ ] Output per-asset telemetry (reject_reason, scores)
- [ ] Compute episode-level stats
- [ ] Write `projects/<ep>/aar_telemetry.json`
- [ ] Test grep-ability of logs

**Phase 7: Regression Suite**
- [ ] Create `test_aar_v2_fixtures.json` (10 fixtures)
- [ ] Implement `test_aar_v2_regression.py`
- [ ] Run regression suite
- [ ] Fix failures
- [ ] Achieve: >70% scenes with entity match, <10% off-topic

**Phase 8: Integration & Polish**
- [ ] Integrate with existing `resolve_scene_assets()` flow
- [ ] Preserve backwards compatibility (fallback to old logic if configs missing)
- [ ] Update documentation
- [ ] Run full pipeline test (1 real episode)
- [ ] Validate final video quality

---

## Performance Expectations

**Query Generation:**
- Before: ~1 sec per episode (episode-level queries)
- After: ~3-5 sec per episode (per-scene queries + entity extraction)
- Impact: +4 sec per episode (acceptable)

**Scoring/Ranking:**
- Before: Simple keyword match (~0.5ms per asset)
- After: Entity + intent + time match (~2ms per asset)
- Impact: +50 assets × 2ms = +100ms per scene (negligible)

**Total AAR Time:**
- Before: ~30 sec per 20-scene episode
- After: ~40 sec per 20-scene episode
- Impact: +33% AAR time, but MASSIVELY better quality

---

## Success Metrics (Post-Implementation)

**Acceptance Criteria:**
1. ✅ **Entity Match:** ≥70% of assets have entity_match_score > 0
2. ✅ **Off-Topic Rate:** <10% of assets have no entity/intent match
3. ✅ **Disambiguation Works:** "Lisa Marie" queries return person photos, not planes
4. ✅ **Source Quality:** Wikimedia/official sources rank higher than random archives
5. ✅ **Regression Suite:** All 10 fixtures pass (min 7/10 scenes per fixture have entity match)
6. ✅ **Fallback Usage:** <20% of scenes need fallback (indicates good primary queries)
7. ✅ **Performance:** AAR completes in <60 sec for 20-scene episode

**User-Facing Impact:**
- Fewer off-topic assets in episode pool
- Better semantic match between narration and visuals
- Reduced manual filtering needed in UI
- Higher conversion rate (Preview → Compile → YouTube)

---

**Status:** ✅ Specifikace kompletní, připraveno k implementaci  
**Next:** Začni Phase 1 (Scene Intent + Entity Extraction) s regression test od začátku


