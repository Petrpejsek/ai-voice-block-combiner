# Topic Intelligence - Gate Filter Fix

## 🐛 Problém

**Popis:** Topic Intelligence vracel méně doporučení, než bylo požadováno.

**Příklad:**
- Uživatel požaduje: **5 doporučení**
- Systém našel: **19 kandidátů**
- Systém vrátil: **4 doporučení** ❌

## 🔍 Analýza Root Cause

### Původní logika v `_apply_gates_and_split`:

```python
# Řádky 1389-1394 (PŘED FIXEM)
if len(top_passed) < count:
    needed = count - len(top_passed)
    fillable = [c for c in other if c['score_total'] >= 50]  # ❌ TOO STRICT
    top_passed.extend(fillable[:needed])
    other = [c for c in other if c not in top_passed]
```

### Co se dělo:

1. **Gate filtering** (momentum/balanced/evergreen) propustilo pouze **4 kandidáty**
2. Systém se pokusil doplnit z `other` seznamu (15 kandidátů)
3. **Problém:** Doplnění bylo omezeno na kandidáty s `score_total >= 50`
4. Pokud zbývající kandidáti měli score < 50, nedoplnili se → **vráceno jen 4 místo 5**

### Proč to byla chyba:

- **Gate testy jsou příliš striktní** pro určité typy témat
- **Threshold 50** je vysoký (A++ = 90+, A = 80+, B = 70+, C = <70)
- **Uživatelská očekávání:** "Požadoval jsem 5, chci dostat 5 nejlepších kandidátů"
- **Reality:** Systém radši vrátil méně témat než snížil kvalitu → **Bad UX**

## ✅ Řešení

### Fix v `backend/topic_intel_service.py` (řádky 1385-1412)

```python
# Sort both lists by score
top_passed.sort(key=lambda x: x['score_total'], reverse=True)
other.sort(key=lambda x: x['score_total'], reverse=True)

# If TOP has fewer than requested, fill from other (with lower threshold)
if len(top_passed) < count:
    needed = count - len(top_passed)
    print(f"⚠️  Gate passed only {len(top_passed)}/{count} - doplňování z Other...")
    
    # FIX: Snížený threshold z 50 na 30, aby systém dokázal vrátit požadovaný počet
    # Pokud ani to nestačí, bereme všechny zbývající (seřazené od nejlepšího)
    fillable = [c for c in other if c['score_total'] >= 30]  # ✅ LOWER THRESHOLD
    if len(fillable) < needed:
        print(f"   Threshold 30+ má jen {len(fillable)} kandidátů, bereme všechny z Other")
        # Pokud stále nemáme dost, přidáme i ty s nejnižším score
        fillable = other  # Už jsou seřazené od nejvyššího score
    
    actually_added = min(len(fillable), needed)
    top_passed.extend(fillable[:needed])
    other = [c for c in other if c not in top_passed]
    print(f"   ✅ Doplněno {actually_added} kandidátů (finální TOP: {len(top_passed)})")
    
    if len(top_passed) < count:
        print(f"   ⚠️  WARNING: Nedostatek kandidátů! Požadováno {count}, dostupných pouze {len(top_passed)}")
        print(f"      Zvažte snížení počtu nebo změnu recommendation_mode")

# Limit TOP to requested count
top_recommendations = top_passed[:count]

# Final validation - pokud stále nemáme požadovaný počet
if len(top_recommendations) < count:
    print(f"   ⚠️  NEDOSTATEK KANDIDÁTŮ: Vráceno {len(top_recommendations)}/{count} doporučení")
    print(f"      Důvod: Nedostatek high-quality kandidátů po filtrování")
```

### Klíčové změny:

1. **Snížený threshold:** `50 → 30` (umožní doplnit více kandidátů)
2. **Fallback bez thresholdu:** Pokud ani threshold 30 nestačí, vezme všechny zbývající
3. **Better logging:** Uživatel vidí, proč dostal méně než požadoval
4. **Graceful degradation:** Systém prioritizuje splnění požadovaného počtu před striktní kvalitou

## 📊 Behavior Po Fixu

### Scénář 1: Gate passed 4/5, Other má score 45+

**PŘED:**
- Gate passed: 4
- Other: 15 (scores: 45, 42, 38...)
- Fillable (score >= 50): 0
- **Result:** 4 doporučení ❌

**PO:**
- Gate passed: 4
- Other: 15 (scores: 45, 42, 38...)
- Fillable (score >= 30): 5
- **Result:** 5 doporučení ✅

### Scénář 2: Gate passed 2/5, Other má score 25+

**PŘED:**
- Gate passed: 2
- Other: 17 (scores: 28, 25, 22...)
- Fillable (score >= 50): 0
- **Result:** 2 doporučení ❌

**PO:**
- Gate passed: 2
- Other: 17 (scores: 28, 25, 22...)
- Fillable (score >= 30): 0 → fallback to all Other
- **Result:** 5 doporučení (best 3 from Other) ✅

### Scénář 3: Pouze 3 kandidáti celkem

**PŘED:**
- Total candidates: 3
- Gate passed: 1
- Other: 2
- **Result:** 1 doporučení ❌

**PO:**
- Total candidates: 3
- Gate passed: 1
- Other: 2
- Fillable: all 2 (fallback)
- **Result:** 3 doporučení + WARNING log ⚠️
  ```
  ⚠️  WARNING: Nedostatek kandidátů! Požadováno 5, dostupných pouze 3
      Zvažte snížení počtu nebo změnu recommendation_mode
  ```

## 🧪 Testing

### Manuální test:

```bash
# 1. Restart backend
cd backend && python3 app.py

# 2. Test s UI
# - Otevři http://localhost:4000
# - Scroll dolů na "Topic Intelligence (US)"
# - Set count=5, window=7d, mode=momentum
# - Click "Start Research"
# - Ověř, že TOP má 5 položek (nebo méně s WARNING)

# 3. Test s API
curl -X POST http://localhost:50000/api/topic-intel/research \
  -H "Content-Type: application/json" \
  -d '{
    "count": 5,
    "window_days": 7,
    "profile_id": "us_true_crime",
    "recommendation_mode": "momentum"
  }'
```

### Ověř v response:

```json
{
  "success": true,
  "items": [...]  // Should have 5 items (or fewer with warning in logs)
  "stats": {
    "top_recommendations": 5,  // ✅ Should match request count
    "other_ideas": 14
  }
}
```

## 📝 Logs Po Fixu

Při běhu uvidíš tyto nové logy:

```
✅ Scored 19 candidates
⚠️  Gate passed only 4/5 - doplňování z Other...
   ✅ Doplněno 1 kandidátů (finální TOP: 5)
✅ TOP recommendations: 5
   Other ideas: 14
```

Nebo v případě nedostatku:

```
✅ Scored 3 candidates
⚠️  Gate passed only 1/5 - doplňování z Other...
   Threshold 30+ má jen 0 kandidátů, bereme všechny z Other
   ✅ Doplněno 2 kandidátů (finální TOP: 3)
   ⚠️  WARNING: Nedostatek kandidátů! Požadováno 5, dostupných pouze 3
      Zvažte snížení počtu nebo změnu recommendation_mode
   ⚠️  NEDOSTATEK KANDIDÁTŮ: Vráceno 3/5 doporučení
      Důvod: Nedostatek high-quality kandidátů po filtrování
✅ TOP recommendations: 3
   Other ideas: 0
```

## 🎯 Výhody Fixu

1. **Better UX:** Uživatel dostane očekávaný počet (nebo jasné vysvětlení proč ne)
2. **Flexibilní kvalita:** Systém preferuje splnění požadavku před perfektní kvalitou
3. **Transparent:** Logy jasně ukazují, co se děje
4. **Graceful degradation:** I při edge cases (málo kandidátů) systém funguje rozumně
5. **Backwards compatible:** Gate logic zůstává stejná, jen fallback je lepší

## ⚠️ Potenciální Concerns

### "Nevrátí to nízko-kvalitní témata?"

**Odpověď:** Ano, ale:
- Kandidáti jsou seřazeni od nejvyššího score (nejlepší first)
- Score < 30 znamená "velmi špatný" (C- rating)
- User explicitly requested N topics → dostane N best available
- Alternative (vrátit méně) je horší UX

### "Gate testy jsou teď zbytečné?"

**Odpověď:** Ne:
- Gate testy stále **prioritizují** kvalitní témata (top_passed)
- Fallback se použije **pouze pokud gate neprojde dost témat**
- Gate passed témata jsou always first v seznamu

### "Měli bychom zrelaxovat gate logiku?"

**Možné řešení:**
- Mode "lenient" s relaxed gates
- User preference: "strict" vs "flexible"
- Adaptive thresholds based on request count

## 🔄 Další Kroky

### Okamžité:
- [x] Fix threshold logic (30 místo 50)
- [x] Add better logging
- [x] Add final validation warning
- [ ] Test s různými profiles (True Crime, History, Science)
- [ ] Test s různými modes (momentum, balanced, evergreen)

### Budoucí vylepšení:
- [ ] Add `strict_mode` parameter (true = old behavior, false = new)
- [ ] Expose gate thresholds v UI (advanced settings)
- [ ] Add "quality score" badge v UI (A++/A/B/C)
- [ ] Track gate pass rate per mode (metrics)

## 📖 Related Files

- `backend/topic_intel_service.py` - Main fix location
- `backend/app.py` - API endpoint
- `frontend/src/components/TopicIntelligencePanel.js` - UI component
- `TOPIC_INTELLIGENCE_README.md` - Feature documentation
- `test_topic_intelligence.sh` - E2E test script

---

**Fix Applied:** January 3, 2026  
**Status:** ✅ Ready for Testing  
**Breaking Changes:** None (backwards compatible)


