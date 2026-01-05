# 🎤 Google TTS - START HERE

**MVP implementace hotová!** Tento dokument ti řekne, co dělat jako první.

---

## ⚡ Quick Start (3 kroky)

### 1. Setup Google Cloud (5 minut)

```bash
# 1. Jdi na https://console.cloud.google.com/
# 2. Vytvoř nový projekt (např. "podcasts-tts")
# 3. Zapni "Cloud Text-to-Speech API"
# 4. Vytvoř Service Account:
#    - Jméno: podcasts-tts-service
#    - Role: Cloud Text-to-Speech User
# 5. Stáhni JSON klíč
# 6. Ulož ho do ~/credentials/ (nebo kamkoliv mimo git)
```

**📖 Detaily:** `GOOGLE_TTS_SETUP.md`

### 2. Nastav backend (2 minuty)

```bash
cd backend

# Zkopíruj ENV template
cp env_example.txt .env

# Edituj .env
nano .env
```

**Změň tyto řádky:**
```bash
# Nastav absolutní cestu k JSON klíči (NE ~/ ale /Users/...)
GOOGLE_APPLICATION_CREDENTIALS=/Users/tvoje_jmeno/credentials/podcasts-tts-XXX.json

# Volitelně změň voice (default je OK)
GCP_TTS_VOICE_NAME=en-US-Neural2-D
GCP_TTS_LANGUAGE_CODE=en-US
```

**⚠️ Důležité poznámky:**
- **REST používá Service Account JSON** (ne AI Studio API key)
- **GOOGLE_APPLICATION_CREDENTIALS musí být nastaveno** (absolutní cesta)
- **Pokud vidíš 401 error:** Je to auth/permissions problém
  - Zkontroluj, že Cloud Text-to-Speech API je zapnutá
  - Zkontroluj service account role (Text-to-Speech User)
  - Zkontroluj billing (i free tier potřebuje platební metodu)

**Instaluj dependencies:**
```bash
pip install -r requirements.txt
```

**Note:** Používáme lightweight REST API přístup (google-auth) místo heavyweight client library.

**Spusť backend:**
```bash
python3 app.py
```

Očekávaný výstup:
```
✅ MoviePy knihovny úspěšně načteny
🎬 FINAL FIXED Ken Burns Backend
🌐 Server běží na: http://localhost:50000
```

### 3. Test (1 minuta)

**V novém terminálu:**
```bash
cd backend
./test_tts_curl.sh
```

**Očekávaný výstup:**
```
✅ SUCCESS!
📈 Vygenerováno 2/2 audio bloků
📁 uploads/Narrator_0001.mp3 (45821 bytes)
📁 uploads/Narrator_0002.mp3 (52134 bytes)
```

---

## ✅ Jestli test prošel...

**Gratulujeme! 🎉 TTS funguje.**

**Co dál:**

1. **Vygeneruj real audio** z tvého `tts_ready_package`:
   ```bash
   curl -X POST http://localhost:50000/api/tts/generate \
     -H "Content-Type: application/json" \
     -d @projects/ep_XXXXX/script_state.json
   ```

2. **Vytvoř video s audio** (automaticky najde Narrator_*.mp3):
   ```bash
   curl -X POST http://localhost:50000/api/generate-video-with-audio \
     -H "Content-Type: application/json" \
     -d '{...}'
   ```

3. **Integruj do pipeline** podle `E2E_INTEGRATION_GUIDE.md`

---

## ❌ Jestli test selhal...

### Error: "Chybí GOOGLE_APPLICATION_CREDENTIALS"

```bash
# Zkontroluj .env:
cat backend/.env | grep GOOGLE_APPLICATION_CREDENTIALS

# Musí být absolutní cesta (začíná /Users/... ne ~/...):
GOOGLE_APPLICATION_CREDENTIALS=/Users/petrliesner/credentials/xxx.json
```

### Error: "Service account soubor neexistuje"

```bash
# Zkontroluj, že soubor existuje:
ls -la /path/from/your/.env

# Pokud ne, zkopíruj JSON ze stažené složky
```

### Error: "Backend neběží"

```bash
# Spusť backend v jiném terminálu:
cd backend
python3 app.py

# Pak zkus test znovu
```

### Error: "Permission denied" nebo "403"

```bash
# V Google Cloud Console → IAM & Admin → IAM
# Tvůj Service Account potřebuje roli:
# "Cloud Text-to-Speech User"
```

**📖 Více troubleshooting:** `GOOGLE_TTS_SETUP.md`

---

## 📚 Dokumentace

| Start here | Popis |
|------------|-------|
| **⚡ START_HERE.md** | Tento soubor (začni tady!) |
| `QUICK_START_TTS.md` | 5min setup guide |
| `GOOGLE_TTS_SETUP.md` | Detailní Google Cloud setup |
| `TTS_MVP_README.md` | API reference, troubleshooting |
| `E2E_INTEGRATION_GUIDE.md` | Jak integrovat do pipeline |
| `FINAL_CHECKLIST.md` | Kompletní přehled implementace |

---

## 🔧 Useful Commands

**Backend:**
```bash
# Spustit
cd backend && python3 app.py

# Health check
curl http://localhost:50000/api/health
```

**Testing:**
```bash
# Bash test (2 bloky)
./backend/test_tts_curl.sh

# Python test (3 bloky)
python3 backend/test_tts_endpoint.py

# Sanity check (ověří všechny komponenty)
python3 backend/sanity_check.py
```

**Generování:**
```bash
# Přímý JSON
curl -X POST http://localhost:50000/api/tts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tts_ready_package": {
      "narration_blocks": [
        {"block_id": "test", "text_tts": "Hello world"}
      ]
    }
  }'

# Ze souboru (script_state.json)
curl -X POST http://localhost:50000/api/tts/generate \
  -H "Content-Type: application/json" \
  -d @projects/ep_XXXXX/script_state.json
```

---

## 🎯 Co to umí

**Input:**
- `tts_ready_package` z LLM pipeline (po LLM5)
- Až 200+ bloků text
- Plain text s `...` pausami

**Output:**
- MP3 soubory: `uploads/Narrator_0001.mp3`, `0002.mp3`, ...
- Fixed-width číslování (4 digits)
- Deterministické pořadí

**Features:**
- ✅ Retry při rate limits (3x s backoff)
- ✅ Partial success (pokračuje když jeden block failne)
- ✅ Automatic cleanup (smaže staré Narrator_*.mp3)
- ✅ Automatic video integration (MoviePy je najde)

**Performance:**
- 10 bloků = ~30s
- 50 bloků = ~2min
- 200 bloků (40min audio) = ~8min

**Free tier:**
- 1M characters/měsíc = ~25 hodin audio zdarma

---

## ✅ 3-Step Checklist

- [ ] Google Cloud projekt vytvořen + API zapnuta
- [ ] Service Account JSON stažen + cesta v `.env`
- [ ] Test prošel: `./backend/test_tts_curl.sh` ✅

**Pokud ano → Ready to rock! 🎸**

---

## 📞 Help

**Problém?**
1. Zkus `python3 backend/sanity_check.py`
2. Přečti `GOOGLE_TTS_SETUP.md` troubleshooting
3. Zkontroluj backend logy (console output)

**Funguje?**
- Pokračuj na `E2E_INTEGRATION_GUIDE.md` pro pipeline integraci

---

**Poslední update:** 26.12.2024  
**Status:** ✅ Production-ready MVP  

🎤 **Let's generate some audio!**

