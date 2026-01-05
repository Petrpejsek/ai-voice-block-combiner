# 🎯 RELEVANCE GATE - Phase 1 Hard Filter Implementace

**Datum:** 2025-12-28  
**Cíl:** Zastavit off-topic assety ještě PŘED scoring, garantovat narativní shodu s konkrétním beatem

---

## 🧠 ZÁKLADNÍ PRINCIP

### Před:
```
AAR → Search archive.org → Score všechny assets → Vyber top-N
```
**Problém:** Populární generic footage (WWII montage) má vysoký downloads → vyhrává nad relevantními

### Po:
```
AAR → Search archive.org → RELEVANCE GATE (PASS/FAIL) → Score jen PASSED → Vyber top-N
```
**Řešení:** Generic footage NEPROJDE gate → nikdy se nedostane do scoringu

---

## ✅ RELEVANCE GATE - 2 ze 3 pravidel MUSÍ projít

Asset musí splnit **alespoň 2 ze 3** pravidel:

### RULE 1: ANCHOR MATCH
- Asset obsahuje **konkrétní anchor** z narrace
- ✅ Anchors: "St Nazaire", "HMS Campbeltown", "Operation Chariot", "Tirpitz"
- ❌ Generic: jen "World War II", "war", "soldiers", "battle"

**Implementace:**
```python
def _check_anchor_match(haystack, narration, keywords):
    # Extract proper nouns: "St Nazaire", "Operation Chariot"
    anchors = re.findall(r"\b[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){1,4}\b", narration)
    
    # Remove generic era terms
    anchors = [a for a in anchors if a not in {"world war", "wwii", "ww2"}]
    
    # Check if ANY anchor in asset
    for anchor in anchors:
        if anchor.lower() in haystack:
            return True, ""
    
    return False, "no_anchor_match"
```

---

### RULE 2: VISUAL NOUN MATCH
- Asset obsahuje **konkrétní vizuální objekty** z narrace
- ✅ Visual nouns: "documents", "office", "maps", "dock", "destroyer"
- ❌ Generic combat: "battlefield", "marching troops", "frontline"

**Kategorie:**
```python
visual_categories = {
    "documents": ["document", "paper", "letter", "archive", "file"],
    "office": ["office", "desk", "interior", "headquarters"],
    "maps": ["map", "chart", "diagram", "plan"],
    "ships": ["destroyer", "battleship", "cruiser", "vessel"],
    "dock": ["dock", "port", "harbor", "shipyard"],
    "intelligence": ["intelligence", "spy", "agent", "secret"],
}
```

**Implementace:**
```python
def _check_visual_noun_match(haystack, narration, keywords):
    # Detect relevant categories from narration
    for cat, markers in visual_categories.items():
        if any(m in narration for m in markers):
            # Check if asset has visuals from this category
            if any(m in haystack for m in markers):
                return True, ""
    
    return False, "no_visual_match"
```

---

### RULE 3: NO FORBIDDEN PATTERNS
- Asset **NESMÍ** obsahovat generic combat patterns (pokud narrace nevyžaduje)
- ✅ Allowed: pokud narrace má "battle of", "combat", "assault"
- ❌ Forbidden: "famous battle", "frontline combat", "military parade", "greatest moments"

**Implementace:**
```python
def _check_forbidden_patterns(haystack, narration):
    # Check if narration needs combat
    explicit_combat = any(t in narration for t in ["battle of", "combat", "assault"])
    
    if explicit_combat:
        return True, ""  # Allow combat footage
    
    # Reject generic patterns
    forbidden = {
        "famous battle", "greatest battle", "iconic speech",
        "montage", "compilation", "highlights"
    }
    
    for pattern in forbidden:
        if pattern in haystack:
            return False, f"forbidden_{pattern}"
    
    return True, ""
```

---

## 🔻 SCORING CHANGES (Phase 2)

### Popularity Downscale
**Před:**
```python
popularity = math.log(max(1, downloads)) * 0.2  # Too strong
```

**Po:**
```python
popularity = math.log(max(1, downloads)) * 0.05  # Weak tiebreaker only
```

**Proč:** Relevance MUSÍ být hlavní driver, ne popularity.

---

## 📊 LOGGING (Definition of Done kritérium)

Každý asset v `asset_candidates` má:

```json
{
  "archive_item_id": "StNazaireRaid1942",
  "score": 18.5,
  "debug": {
    "gate_result": "PASS",
    "gate_details": {
      "rule_1_anchor": "PASS",
      "rule_2_visual": "PASS", 
      "rule_3_forbidden": "PASS",
      "rules_passed": "3/3"
    },
    "matched_keywords": ["st nazaire", "dry dock", "operation chariot"]
  }
}
```

**Rejected assets (verbose mode):**
```
🚫 GATE REJECT: WartimeHighlights1943 - FAIL (1/3 rules): no_anchor_match
📊 Beat b_0001: 4 assets rejected by gate, 2 passed to scoring
```

---

## 🧪 TEST CASES

### ✅ PASS Example (3/3 rules)
**Asset:** "St Nazaire Raid 1942 - Operation Chariot Documentary"  
**Narration:** "During WWII, HMS Campbeltown attacked the dry dock at St Nazaire..."

- ✅ RULE 1: anchor "St Nazaire", "HMS Campbeltown", "Operation Chariot"
- ✅ RULE 2: visual "dry dock", "raid"
- ✅ RULE 3: no forbidden (specific operation, not generic battle)

**Result:** PASS (3/3) → goes to scoring

---

### ❌ FAIL Example (1/3 rules)
**Asset:** "World War II Greatest Battles Compilation"  
**Narration:** "The intelligence officer reviewed documents in his office..."

- ❌ RULE 1: no anchor match (only "WWII")
- ❌ RULE 2: no visual match (no "documents", "office")
- ✅ RULE 3: forbidden "compilation" (generic montage)

**Result:** FAIL (1/3) → HARD REJECT, never scored

---

## 🎯 DEFINITION OF DONE (10/10)

AAR je hotový pokud:

1. ✅ Generic montage nikdy nevyhraje nad beat-specific asset
2. ✅ Každý vybraný asset lze obhájit: *"Tohle vizuálně odpovídá tomu co se vypráví"*
3. ✅ V logu je jasně vidět proč byl asset odmítnut/vybrán
4. ✅ Popularity je jen tiebreaker, ne hlavní driver
5. ✅ Gate je MANDATORY před scoringem

---

## 📈 OČEKÁVANÉ VÝSLEDKY

### Před Relevance Gate:
```json
{
  "asset_candidates": [
    {
      "archive_item_id": "WWII_Greatest_Battles_HD",
      "score": 12.5,
      "debug": {"matched_keywords": ["world", "war"], "downloads": 950000}
    }
  ]
}
```
- Generic montage s vysokými downloads vyhrává

### Po Relevance Gate:
```json
{
  "asset_candidates": [
    {
      "archive_item_id": "StNazaireRaid_OperationChariot_1942",
      "score": 18.5,
      "debug": {
        "gate_result": "PASS",
        "gate_details": {"rules_passed": "3/3"},
        "matched_keywords": ["st nazaire", "operation chariot", "dry dock"]
      }
    }
  ]
}
```
- Specific, beat-relevant asset vyhrává (i s menším downloads)

---

## 🔄 CACHE VERSION

```python
AAR_CACHE_VERSION = "v8_relevance_gate"  # bumped from v7
```

**Důvod:** Scoring + gate logika se změnila → stará cache vrátí špatné výsledky

---

## 🚀 DEPLOYMENT

### Clear cache & test:
```bash
rm -rf projects/ep_9f2ea4ca9f19/archive_cache/*
python backend/run_step.py --episode ep_9f2ea4ca9f19 --step AAR --verbose

# Expected output:
#   🚫 GATE REJECT: WWII_Montage - FAIL (1/3 rules): no_anchor_match
#   ✅ PASS: StNazaireRaid - PASS (3/3 rules)
#   📊 Beat b_0001: 3 rejected, 2 passed to scoring
```

---

**Status:** ✅ Implementováno, čeká na test



