# Pre-FDA Sanitizer - Quick Start

## ✅ Co je nového?

**Pre-FDA Sanitizer** je nový deterministický krok v pipeline, který **automaticky** odstraňuje abstraktní/generické výrazy z FDA výstupu **PŘED** validací.

### Před Sanitizerem (častý error):
```
❌ FDA_GENERIC_FILLER_DETECTED: Scene 0 (sc_0001) obsahuje blacklisted 
   terms v keywords: ['strategic', 'goal', 'territory', 'peace']
```

### Po Sanitizeru:
```
✅ FDA_SANITIZER_PASS: {"scenes_processed":8,"total_replacements":3,
   "scene_details":[{"scene_id":"sc_0001","replacements":["strategic→archival_documents"]}]}
```

---

## 🚀 Použití (automatické)

**Není potřeba nic měnit!** Sanitizer běží **automaticky** v pipeline:

```
TTS Formatting
    ↓
LLM generuje shot_plan
    ↓
Pre-FDA Sanitizer ← automaticky čistí abstraktní termy
    ↓
validate_and_fix_shot_plan
    ↓
validate_shot_plan_hard_gate
    ↓
Uložení
```

---

## 🔍 Jak to funguje?

### 1. Blacklist (zakázané abstraktní výrazy)
```python
"strategic", "strategy", "goal", "territory", "peace", 
"influence", "power", "importance", "history", "events", ...
```

### 2. Visual Proxy (konkrétní náhrady)
```python
"strategic"  → "archival_documents"
"goal"       → "official_correspondence"
"territory"  → "marked_maps"
"peace"      → "treaty_documents"
```

### 3. Deterministické nahrazení
```python
# Původní keywords
["strategic", "Napoleon", "Moscow", "goal"]

# Po sanitizaci
["archival_documents", "Napoleon", "Moscow", "official_correspondence"]
```

**Význam narace zůstává zachován:**
- ✅ "strategic goal" → dokumentované cíle (archival_documents + official_correspondence)
- ✅ "territory control" → mapy území (marked_maps + border_maps)
- ✅ Konkrétní termíny (Napoleon, Moscow) zůstávají beze změny

---

## 📊 Logging

### Success (PASS)
```bash
grep "FDA_SANITIZER_PASS" backend_server.log
```
```json
{"timestamp":"2025-12-28T12:34:56Z","status":"FDA_SANITIZER_PASS","scenes_processed":8,"total_replacements":3}
```

### Failure (FATAL)
```bash
grep "FDA_SANITIZER_FAIL" backend_server.log
```
```json
{"timestamp":"2025-12-28T12:34:56Z","status":"FDA_SANITIZER_FAIL","error":"FDA_SANITIZER_UNMAPPED: Token 'unknown_term' ..."}
```

---

## 🚨 Troubleshooting

### Error: `FDA_SANITIZER_UNAVAILABLE`

**Příčina:** `pre_fda_sanitizer.py` není dostupný (import failed)

**Řešení:**
```bash
cd backend
ls pre_fda_sanitizer.py  # Zkontroluj, zda soubor existuje
python3 -c "import pre_fda_sanitizer"  # Test importu
```

### Error: `FDA_SANITIZER_UNMAPPED`

**Příčina:** Blacklisted term nemá mapování v `VISUAL_PROXY_MAP`

**Řešení:**
1. Otevři `backend/pre_fda_sanitizer.py`
2. Najdi `VISUAL_PROXY_MAP`
3. Přidej mapování pro chybějící term:
   ```python
   VISUAL_PROXY_MAP = {
       # ... existující mapování ...
       "new_blacklisted_term": "concrete_visual_proxy",
   }
   ```

### Error: `FDA_SANITIZER_FAILED`

**Příčina:** Po sanitizaci zůstal blacklisted term

**Řešení:**
1. Zkontroluj log pro diagnostic data
2. Ověř, že `VISUAL_PROXY_MAP` obsahuje správné náhrady
3. Spusť testy: `pytest backend/test_pre_fda_sanitizer.py -v`

---

## 🧪 Testování

### Quick test
```bash
cd backend
python3 -m pytest test_pre_fda_sanitizer.py -v
```

### Očekávaný výstup
```
============================== 16 passed in 0.09s ==============================
```

### Integration test s reálným projektem
```bash
cd backend
python3 run_fda_on_project.py <episode_id>

# Očekávaný výsledek:
# ✅ FDA_SANITIZER_PASS
# ✅ Shot plan uložen bez FDA_GENERIC_FILLER_DETECTED errors
```

---

## 📚 Co dělat, když...

### ❓ Chci přidat nový blacklisted term

1. Otevři `backend/pre_fda_sanitizer.py`
2. Přidej do `BLACKLISTED_ABSTRACT_TERMS`:
   ```python
   BLACKLISTED_ABSTRACT_TERMS = [
       # ... existující termy ...
       "novy_abstraktni_term",
   ]
   ```
3. Přidej mapování do `VISUAL_PROXY_MAP`:
   ```python
   VISUAL_PROXY_MAP = {
       # ... existující mapování ...
       "novy_abstraktni_term": "konkretni_vizualni_nahrada",
   }
   ```
4. Spusť testy: `pytest backend/test_pre_fda_sanitizer.py`

### ❓ Chci změnit náhradu pro existující term

1. Otevři `backend/pre_fda_sanitizer.py`
2. Uprav `VISUAL_PROXY_MAP`:
   ```python
   "strategic": "nova_nahrada",  # Původně: "archival_documents"
   ```
3. Spusť testy
4. Ověř, že FDA nepadá na novou náhradu

### ❓ Chci odstranit term z blacklistu

1. Otevři `backend/pre_fda_sanitizer.py`
2. Odstraň z `BLACKLISTED_ABSTRACT_TERMS`
3. Odstraň z `VISUAL_PROXY_MAP`
4. Spusť testy

---

## ✅ Definition of Done

### Před merge:
- [x] Všechny testy procházejí (16/16)
- [x] FDA už nepadá na "strategic", "goal", "territory", "peace"
- [x] Význam narace zachován
- [x] Žádné fallbacky (všechny chyby jsou FATAL)
- [x] Grep-friendly logging

### Před production:
- [ ] Integration test s reálným projektem
- [ ] Ověření, že FDA_GENERIC_FILLER_DETECTED errors jsou 0
- [ ] Performance test (sanitizer nesmí zpomalit pipeline)

---

## 📖 Další dokumentace

- **Podrobná dokumentace:** `PRE_FDA_SANITIZER_GUIDE.md`
- **FDA dokumentace:** `FDA_README.md`
- **Troubleshooting:** `FDA_TROUBLESHOOTING.md`

---

**Poslední aktualizace:** 2025-12-28  
**Verze:** 1.0  
**Status:** ✅ Testováno, připraveno k nasazení



