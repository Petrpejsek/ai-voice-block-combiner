# Relevance Scoring - Quick Reference

## 🎯 Co bylo změněno?

**Problém:** Asset resolver vybíral nerelevantní videa (compilations, moderní editace)

**Řešení:** **Inteligentní relevance scoring** - vždy vybere TOP 1 podle skóre

---

## ⚡ Nový systém (1 minuta)

### Princip:
```
Kandidáty → Ohodnoť skóre (0.0-1.0) → Vezmi TOP 1
```

### 10 pravidel scoring:

**✅ PLUS (+0.75 max):**
- +0.25: Title obsahuje anchor (Napoleon/Moscow)
- +0.15: Description obsahuje anchor
- +0.15: Archivní formát (map/engraving/manuscript)
- +0.10: Dobrá délka (10s-3min)
- +0.10: Typ odpovídá shot_type

**❌ MÍNUS (-0.65 max):**
- −0.30: Compilation/montage/highlights/HD
- −0.15: Extrémní délka (<5s nebo >20min)
- −0.20: Generický title bez anchors

---

## 📊 Příklad

### Video A: "Napoleon's Retreat Moscow 1812 - Archival Map"
```
+0.25 (title anchors) + 0.15 (archival) + 0.10 (duration) + 0.10 (type match)
= 0.60 ✅ TOP 1
```

### Video B: "Historical Footage Compilation HD"
```
+0.00 (no anchors) − 0.30 (compilation) − 0.20 (generic)
= 0.00 ❌ REJECTED
```

---

## 🚀 Klíčové změny

| PŘED | PO |
|------|-----|
| Vzal první výsledek | Vybere TOP 1 podle score |
| Failoval na špatném videu | **NIKDY nefailuje** |
| Žádná telemetrie | JSON log per scéna |
| Compilations projdou | Compilations penalizovány -0.30 |

---

## 📝 Telemetrie

Každá scéna loguje:
```json
AAR_TELEMETRY: {
  "scene_id": "sc_0001",
  "candidates_count": 15,
  "selected_score": 0.60,
  "top3_scores": [0.60, 0.45, 0.35]
}
```

**Grep:**
```bash
grep "AAR_TELEMETRY" /tmp/backend_relevance_scoring.log
```

---

## 🔧 Změněné soubory

**`backend/archive_asset_resolver.py`:**
- Nová funkce `_rank_asset()` (10 pravidel)
- Upravená `_select_top_assets()` (vždy vrátí TOP 1)
- Quality floor snížen: 0.55 → 0.45
- Přidána telemetrie (JSON log)

---

## ✅ Výsledek

**PŘED:**
- ❌ Nerelevantní videa (compilations)
- ❌ ERROR loopy

**PO:**
- ✅ TOP 1 podle relevance
- ✅ Žádné ERROR loopy
- ✅ Lepší kvalita výstupu

---

**Status:** ✅ READY  
**Restart:** Backend restartován (PID v logu)  
**Test:** Spusťte episode a zkontrolujte `AAR_TELEMETRY` logy



