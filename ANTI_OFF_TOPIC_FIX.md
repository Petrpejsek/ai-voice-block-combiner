# 🎯 Anti Off-Topic Fix - Implementace

**Datum:** 2025-12-28  
**Problém:** Off-topic záběry (generic WWII footage místo specifických entit) + duplicitní queries

## 🔍 Root Cause Analysis

### Problém 1: FDA generoval duplicitní queries
```json
"query_used": "World War II World War II"
```

### Problém 2: AAR scoring upřednostňoval populární videa
Asset s pouze "world" + "war" v title dostal **score 11.0** (top priority).

### Problém 3: Žádná filtrace generic queries
FDA prompt říkal "avoid generic queries", ale LLM to ignoroval.

---

## ✅ Implementované Fixy

### 1️⃣ FDA Prompt - Explicitní příklady (footage_director.py:164-172)

**Přidáno:**
```
- Search queries MUST be specific and include CONCRETE ENTITIES:
  ✅ GOOD: "St Nazaire dry dock 1942", "HMS Campbeltown destroyer", "Operation Chariot commandos"
  ❌ BAD: "World War II strategies", "military tactics", "WWII", "naval warfare"
- NEVER repeat the same query twice (no duplicates like "World War II World War II")
- Each query must be UNIQUE and SPECIFIC to a particular place, person, operation, ship
```

**Proč to pomůže:**
- LLM dostává jasné příklady co je OK/BAD
- Explicitní ban na duplicity

---

### 2️⃣ AAR Scoring - Penalizace generic-only matches (archive_asset_resolver.py:830-862)

**Změna:**
```python
# Track specific entity matches vs generic terms
specific_entity_matches = 0
generic_only_matches = 0

for kw in keywords:
    if kw_s in generic_markers:  # "world", "war", "wwii", etc.
        generic_only_matches += 1
        continue  # Skip - no relevance
    
    if kw_s in title or kw_s in desc:
        specific_entity_matches += 1
        relevance += (weight)

# CRITICAL: Penalize assets with ONLY generic matches
if specific_entity_matches == 0 and generic_only_matches > 0:
    relevance -= 15.0  # Heavy penalty for "WWII" only
```

**Proč to pomůže:**
- Asset s pouze "World War II" v title dostane **-15.0** penalty
- Asset s "St Nazaire" + "WWII" dostane plný bonus (specific entity match)

---

### 3️⃣ AAR Query Filtering - Reject generic queries (archive_asset_resolver.py:1019-1078)

**Přidáno:**
```python
def _query_score(q: str) -> float:
    # ... existing logic ...
    
    # REJECT purely generic queries
    query_words = set(q.lower().split())
    if query_words.issubset({"world", "war", "ii", "ww2", "wwii", "2"}):
        return -10.0  # Reject "World War II" alone
    
    return score

# Filter queries before search
for q in all_queries:
    score = _query_score(q)
    if score < -5.0:
        print(f"⚠️  Rejecting generic query: '{q}'")
        continue  # Don't search
```

**Proč to pomůže:**
- "World War II" query se **vůbec nepošle** do archive.org API
- Pouze specifické queries (score > -5.0) se použijí

---

### 4️⃣ AAR Query Deduplication (archive_asset_resolver.py:1043-1055)

**Přidáno:**
```python
def _dedupe_queries(queries: List[str]) -> List[str]:
    seen = set()
    unique = []
    for q in queries:
        q_norm = q.lower().strip()
        if q_norm not in seen and q_norm:
            seen.add(q_norm)
            unique.append(q)
    return unique

all_queries = _dedupe_queries(all_queries_raw)
```

**Proč to pomůže:**
- "World War II World War II" → "World War II" (1x)
- Case-insensitive deduplication

---

## 📊 Očekávané Výsledky

### Před fixem:
```json
{
  "asset_candidates": [
    {
      "archive_item_id": "WartimeN1943",
      "score": 11.0,
      "query_used": "World War II World War II",
      "debug": {
        "matched_keywords": ["world", "war"]
      }
    }
  ]
}
```
- Generic footage
- Duplicitní query
- High score jen kvůli "world" + "war"

### Po fixu:
```json
{
  "asset_candidates": [
    {
      "archive_item_id": "StNazaireRaid1942",
      "score": 18.5,
      "query_used": "St Nazaire dry dock Operation Chariot",
      "debug": {
        "matched_keywords": ["st nazaire", "dry dock", "operation chariot"],
        "specific_entity_matches": 3
      }
    }
  ]
}
```
- Specific footage
- Unique query
- High score kvůli entity matches

---

## 🧪 Verifikace

### Test sekvence:
```bash
# 1. Clear cache (force fresh queries)
rm -rf projects/ep_9f2ea4ca9f19/archive_cache/*

# 2. Run FDA + AAR with verbose
python backend/run_step.py --episode ep_9f2ea4ca9f19 --step FDA --verbose
python backend/run_step.py --episode ep_9f2ea4ca9f19 --step AAR --verbose

# 3. Check manifest
cat projects/ep_9f2ea4ca9f19/archive_manifest.json | grep "query_used"

# 4. Expected output:
# ✅ "query_used": "St Nazaire dry dock 1942"
# ✅ "query_used": "HMS Campbeltown destroyer"
# ❌ NO "World War II World War II"
# ❌ NO "query_used": "World War II" (alone)
```

### Success criteria:
1. ✅ Žádné duplicitní queries
2. ✅ Žádné generic-only queries ("WWII" alone)
3. ✅ Assets mají specific entity matches (St Nazaire, HMS Campbeltown)
4. ✅ Top-scored assets jsou relevantní k naraci

---

## 🔄 Cache Version Bump

```python
# archive_asset_resolver.py:21
AAR_CACHE_VERSION = "v7_anti_off_topic"  # bumped from v6
```

**Důvod:** Scoring logika se změnila → stará cache by vrátila špatné výsledky.

---

## 📝 Related Issues Fixed

- ✅ Duplicitní queries
- ✅ Generic-only queries
- ✅ Off-topic footage (high downloads, low relevance)
- ✅ Cache persistence bypass (scoring se aplikuje i na cache)

---

**Status:** ✅ Implementováno, čeká na test



