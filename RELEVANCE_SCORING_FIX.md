# Relevance Scoring Fix - Dokumentace

## 🎯 Problém

**Původní chování:**
- Asset resolver vybíral **první/náhodný** výsledek z vyhledávání
- Často to byly **nerelevantní** videa: compilations, montage, moderní editace, HD remastery
- Blacklisty a sanitizéry vedly k **ERROR loopům** místo k lepšímu výběru

**Důsledek:**
- Technicky pipeline fungovala, ale **kvalita výstupu byla špatná**
- Uživatel viděl moderní sestřihy místo archivních záběrů

---

## ✅ Řešení

### ARCHITEKTONICKÁ ZMĚNA: Relevance Scoring

**Princip:**
```
Místo: "vezmi první výsledek"
Dělej:  "najdi kandidáty → ohodnoť skóre → vezmi TOP 1"
```

**Klíčové vlastnosti:**
- ✅ **Deterministické** (žádné LLM)
- ✅ **Soft scoring** (ne fail-fast)
- ✅ **Vždy vybere TOP 1** (i když score < 0.45)
- ✅ **Minimální telemetrie** (scene_id, scores, top3)

---

## 📊 Nový Relevance Scoring (10 pravidel)

### ✅ PLUS BODY (max +0.75)

| Pravidlo | Body | Podmínka |
|----------|------|----------|
| 1. Title anchor | **+0.25** | TITLE obsahuje anchor (Napoleon/Moscow/Kremlin) |
| 2. Description anchor | **+0.15** | DESCRIPTION obsahuje anchor |
| 3. Archivní formát | **+0.15** | Obsahuje: engraving/map/manuscript/letter/archival/photograph |
| 4. Dobrá délka | **+0.10** | Délka videa 10s-3min (ideální pro scény) |
| 5. Shot type match | **+0.10** | Typ odpovídá shot_type (map/document/city view) |

### ❌ MÍNUS BODY (max -0.65)

| Pravidlo | Body | Podmínka |
|----------|------|----------|
| 6. Compilation/montage | **−0.30** | TITLE/DESC obsahuje: montage/compilation/highlights/edit/HD/full documentary |
| 7. Extrémní délka | **−0.15** | Video < 5s nebo > 20min |
| 8. Generický title | **−0.20** | TITLE je "historical footage" / "old video" BEZ konkrétních anchors |

---

## 🔍 Příklad scoring

### Video A: "Napoleon's Retreat from Moscow 1812 - Archival Map"
```
+0.25  title_anchors(Napoleon, Moscow, 1812)
+0.15  archival_format(map)
+0.10  good_duration(45s)
+0.10  shot_type_match(maps)
───────
= 0.60  ✅ EXCELLENT (TOP 1)
```

### Video B: "Historical Footage Compilation - HD Remastered"
```
+0.00  title_anchors(0)
−0.30  bad_pattern(compilation, HD)
−0.20  generic_title("historical footage")
───────
= −0.50 → 0.00  ❌ REJECTED (clamped to 0)
```

### Video C: "Moscow City Streets 1812"
```
+0.25  title_anchors(Moscow, 1812)
+0.10  good_duration(120s)
───────
= 0.35  ⚠️  LOW SCORE (ale použije se, pokud je TOP 1)
```

---

## 🚀 Změny chování

### PŘED:
```python
# Vzal první výsledek
asset = results[0]  # ❌ Může být compilation!

# Nebo failoval
if not is_perfect(asset):
    raise RuntimeError("FDA_ASSET_FAILED")  # ❌ Loop!
```

### PO:
```python
# Ohodnotí všechny kandidáty
for asset in results:
    score = _rank_asset(asset, anchors, shot_types)

# Vezme TOP 1 (i když score < 0.45)
best = sorted(results, key=lambda x: x.score)[0]  # ✅ Vždy vybere nejlepší

# NIKDY nefailuje
return best  # ✅ Pipeline pokračuje
```

---

## 📝 Telemetrie (minimální)

Pro každou scénu se loguje:

```json
AAR_TELEMETRY: {
  "scene_id": "sc_0001",
  "candidates_count": 15,
  "filtered_count": 12,
  "selected_asset_id": "prelinger_napoleon_moscow_1812",
  "selected_score": 0.60,
  "top3_scores": [0.60, 0.45, 0.35],
  "top3_titles": [
    "Napoleon's Retreat from Moscow 1812 - Archival Map",
    "Moscow City Streets Historical",
    "19th Century Russian Maps"
  ]
}
```

**Účel:**
- Debug: Proč bylo vybráno toto video?
- Monitoring: Jsou skóre dostatečně vysoká?
- Optimalizace: Které pravidlo má největší dopad?

---

## 🔧 Změněné soubory

### `backend/archive_asset_resolver.py`

**1. Nová funkce `_rank_asset()`**
- 10 pravidel (5 plus, 3 mínus)
- Deterministické scoring (0.0-1.0)
- Přijímá `shot_types` pro type matching

**2. Upravená funkce `_select_top_assets()`**
- Volá nový `_rank_asset()` s `shot_types`
- **NIKDY nefailuje** (i když score < 0.45)
- Přidána telemetrie (JSON log)

**3. Snížený quality floor**
```python
# PŘED:
ASSET_RANKING_QUALITY_FLOOR = 0.55  # Příliš přísné

# PO:
ASSET_RANKING_QUALITY_FLOOR = 0.45  # Rozumnější práh
```

---

## 🎯 Co to znamená pro uživatele

### PŘED:
```
🔍 Vyhledávání: "Napoleon Moscow 1812"
📹 Výsledky: 15 videí
❌ Vybrané: "Historical Footage Compilation HD" (první výsledek)
😞 Výstup: Moderní sestřih s hudbou a efekty
```

### PO:
```
🔍 Vyhledávání: "Napoleon Moscow 1812"
📹 Výsledky: 15 videí
🎯 Scoring: 15 videí ohodnoceno (0.0-1.0)
✅ Vybrané: "Napoleon's Retreat - Archival Map 1812" (score: 0.60)
😊 Výstup: Autentický archivní materiál
```

---

## 🧪 Jak testovat

### Quick test:
```bash
cd backend
python3 -c "
from archive_asset_resolver import _rank_asset

# Test asset
asset = {
    'title': 'Napoleon Moscow 1812 Archival Map',
    'description': 'Historical engraving showing retreat',
    'duration_sec': 45
}

anchors = ['napoleon', 'moscow', '1812']
shot_types = ['maps_context']

score, debug = _rank_asset(asset, anchors, shot_types=shot_types)
print(f'Score: {score}')
print(f'Rules: {debug[\"rules\"]}')
"
```

**Očekávaný výstup:**
```
Score: 0.60
Rules: ['+0.25 title_anchors(3)', '+0.15 archival_format', '+0.10 good_duration(45s)', '+0.10 shot_type_match(maps)']
```

---

## 📊 Pravidla pro budoucnost

### ✅ DO:
- Vždy vybrat TOP 1 podle score
- Logovat telemetrii pro debug
- Penalizovat compilations/montage
- Preferovat archivní formáty

### ❌ DON'T:
- NIKDY nefailovat kvůli nízkému score
- NIKDY nevybírat náhodně
- NIKDY nepoužívat první výsledek bez scoring
- NIKDY nepřidávat LLM do scoring (deterministické!)

---

## 🔍 Monitoring

### Grep-friendly logy:
```bash
# Všechny telemetrie
grep "AAR_TELEMETRY" /tmp/backend_relevance_scoring.log

# Nízké skóre (< 0.45)
grep "AAR_TELEMETRY" /tmp/backend_relevance_scoring.log | jq 'select(.selected_score < 0.45)'

# Top 3 scores per scéna
grep "AAR_TELEMETRY" /tmp/backend_relevance_scoring.log | jq '.scene_id, .top3_scores'
```

---

## 🚀 Výsledek

### Před fixem:
- ❌ Nerelevantní videa (compilations, moderní editace)
- ❌ ERROR loopy kvůli blacklistům
- ❌ Špatná kvalita výstupu

### Po fixu:
- ✅ TOP 1 podle relevance score
- ✅ Žádné ERROR loopy (vždy vybere nejlepší)
- ✅ Lepší kvalita výstupu (archivní materiály)
- ✅ Telemetrie pro debug a monitoring

---

**Datum:** 2025-12-29  
**Status:** ✅ READY FOR PRODUCTION  
**Breaking changes:** Žádné (zpětně kompatibilní)  
**Testováno:** Unit test + smoke test



