# 🚀 FDA Quick Reference Card

## Rychlý start (3 kroky)

```bash
# 1. Test
cd backend && python3 test_fda.py

# 2. Standalone API
curl -X POST http://localhost:50000/api/fda/generate \
  -H "Content-Type: application/json" \
  -d '{"narration_blocks": [{"block_id": "b_01", "text_tts": "Text...", "claim_ids": []}]}'

# 3. Pipeline (automaticky běží jako 6. krok)
curl -X POST http://localhost:50000/api/script/generate \
  -d '{"topic": "...", "language": "en", "target_minutes": 3, "openai_api_key": "..."}'
```

---

## Co FDA dělá

✅ Čte `tts_ready_package.narration_blocks[]`  
✅ Odhadne délku řeči (words_per_minute)  
✅ Vytvoří scény (20-35s nebo 3-8 bloků)  
✅ Přiřadí emotion, keywords, shot_types  
✅ Vygeneruje search_queries  
✅ Uloží `shot_plan` do `script_state.json`  

---

## Co FDA NEDĚLÁ

❌ Nevolá externí API (Archive.org, Pexels)  
❌ Nestahuje videa  
❌ Nerenderuje (ffmpeg, moviepy)  
❌ Neupravuje TTS texty  

---

## Výstup: `shot_plan`

```json
{
  "version": "fda_v1",
  "scenes": [
    {
      "scene_id": "sc_0001",
      "start_sec": 0,
      "end_sec": 26,
      "emotion": "hope",
      "keywords": ["word1", "word2", ...],
      "shot_strategy": {
        "shot_types": ["archival_documents"],
        "clip_length_sec_range": [4, 7],
        "cut_rhythm": "medium"
      },
      "search_queries": ["query1", "query2", ...]
    }
  ]
}
```

---

## Allowlisty (MVP pevné hodnoty)

**shot_types (9):**
- historical_battle_footage
- troop_movement
- leaders_speeches
- civilian_life
- destruction_aftermath
- industry_war_effort
- maps_context
- archival_documents
- atmosphere_transition

**emotion (6):**
- neutral, tension, tragedy, hope, victory, mystery

**cut_rhythm (3):**
- slow (5-8s/clip), medium (4-7s), fast (3-5s)

---

## Soubory

```
backend/
├── footage_director.py    # Core modul
├── script_pipeline.py     # Integrace (6. krok)
├── app.py                 # API endpoint
└── test_fda.py           # Test suite

FDA_README.md             # Kompletní dokumentace
FDA_DELIVERY_REPORT.md    # Delivery report
```

---

## API Endpoint

**POST** `/api/fda/generate`

**Input:**
```json
{
  "tts_ready_package": {
    "narration_blocks": [...]
  }
}
```

**Output:**
```json
{
  "success": true,
  "shot_plan": {...},
  "summary": {
    "total_scenes": 3,
    "total_duration_sec": 69
  }
}
```

---

## Pipeline Flow

```
Research → Narrative → Validation → Composer → TTS → 🆕 FDA
```

---

## Troubleshooting

```bash
# Error: FDA_INPUT_MISSING
# → Zkontroluj že tts_ready_package obsahuje narration_blocks[]

# Error: FDA_VALIDATION_FAILED
# → Spusť validate_shot_plan() pro detaily

# Test selhal
# → python3 test_fda.py  (9 testů musí projít)
```

---

## Acceptance Criteria ✅

✅ Shot_plan se uloží do script_state  
✅ Žádné externí API  
✅ Stabilní schema (allowlisty, kontinuita)  

---

**Verze:** FDA v1  
**Status:** Production Ready  
**Dokumentace:** FDA_README.md



