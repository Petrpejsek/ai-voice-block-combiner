# 🔄 Restart Guide - FDA Integration

## Problém
FDA není vidět v UI mezi asistenty, protože frontend má hardcoded seznam kroků.

## Řešení ✅

Frontend byl aktualizován! Nyní potřebujete **restart obou serverů**.

---

## 🚀 Restart (krok za krokem)

### 1. Zjistit běžící terminály

```bash
cd /Users/petrliesner/podcasts
ls -la terminals/
```

### 2. Restart backendu

```bash
# Najdi PID backendu (port 50000)
lsof -ti:50000

# Zastav backend (pokud běží)
kill $(lsof -ti:50000)

# Spusť backend znovu
cd /Users/petrliesner/podcasts/backend
python3 app.py
```

**Očekávaný výstup:**
```
✅ MoviePy knihovny úspěšně načteny
🎬 FINAL FIXED Ken Burns Backend
...
 * Running on http://127.0.0.1:50000
```

### 3. Restart frontendu

```bash
# Najdi PID frontendu (port 4000)
lsof -ti:4000

# Zastav frontend (pokud běží)
kill $(lsof -ti:4000)

# Spusť frontend znovu
cd /Users/petrliesner/podcasts/frontend
PORT=4000 npm start
```

**Očekávaný výstup:**
```
Compiled successfully!

You can now view frontend in the browser.

  Local:            http://localhost:4000
```

---

## ✅ Ověření v UI

Po restartu **obou serverů** uvidíte v UI:

```
Průběh                           narrative attempts: 1

Research…                        ✅ DONE
Writing…                         ✅ DONE
Validating…                      ✅ DONE
Packaging…                       ✅ DONE
TTS Formatting…                  ✅ DONE
Footage Director…                ✅ DONE  ← NOVÝ KROK
```

---

## 🔍 Co bylo změněno ve frontendu

### `frontend/src/components/VideoProductionPipeline.js`

1. **Přidán krok do UI** (řádek 1046):
   ```js
   {renderStepRow('Footage Director…', 'footage_director')}
   ```

2. **Přidán raw output** (řádek 509):
   ```js
   if (key === 'footage_director') return scriptState?.shot_plan || null;
   ```

3. **Přidán do retry seznamu** (řádek 490):
   ```js
   ['research', 'narrative', 'validation', 'composer', 'tts_format', 'footage_director']
   ```

4. **Aktualizován popis pipeline** (řádek 627):
   ```
   Research → Writing → Validating → Packaging → TTS → Footage Director
   ```

---

## 🧪 Test po restartu

### 1. Backend test
```bash
curl http://localhost:50000/api/health
# Expected: {"status": "healthy"}
```

### 2. Frontend test
```bash
# Otevři prohlížeč
open http://localhost:4000
```

### 3. Vygeneruj nový script (FDA automaticky běží)
```bash
curl -X POST http://localhost:50000/api/script/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "test fda integration",
    "language": "en",
    "target_minutes": 2,
    "openai_api_key": "sk-..."
  }'
```

**V UI uvidíš:** Všech 6 kroků včetně "Footage Director…"

---

## 🎯 Shrnutí změn

### Backend (už hotovo ✅)
- ✅ `footage_director.py` - core modul
- ✅ `script_pipeline.py` - integrace jako 6. krok
- ✅ `app.py` - API endpoint `/api/fda/generate`

### Frontend (právě změněno ✅)
- ✅ Přidán krok "Footage Director…" do UI
- ✅ Přidán raw output pro `shot_plan`
- ✅ Přidán do retry seznamu
- ✅ Aktualizován popis pipeline

---

## ⚠️ Troubleshooting

### Problem: Po restartu stále nevidím FDA v UI

**Řešení:**
1. Hard refresh browseru: `Cmd + Shift + R` (Mac) nebo `Ctrl + F5` (Windows)
2. Ověř že frontend běží na port 4000: `lsof -ti:4000`
3. Zkontroluj konzoli v browseru (F12) zda nejsou chyby

### Problem: Backend hlásí chybu při importu

**Řešení:**
```bash
cd /Users/petrliesner/podcasts/backend
python3 -c "from footage_director import run_fda; print('✅ Import OK')"
```

### Problem: UI zobrazuje starý počet kroků

**Řešení:** Clear cache browseru nebo použij Incognito mode

---

## 📱 Kontakt

Po restartu by mělo vše fungovat! Pokud něco nefunguje, zkontroluj:
- Backend běží na port 50000 ✅
- Frontend běží na port 4000 ✅
- Browser cache je clear ✅

**FDA by měl být viditelný jako 6. krok v pipeline!** 🎉



