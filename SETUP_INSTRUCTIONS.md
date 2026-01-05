# 🎯 QUICK START: Google TTS Setup

**Stav:** ✅ Infrastruktura připravena  
**Čeká na:** Service account JSON od uživatele

---

## 🚀 Co musíte udělat (2 kroky)

### Krok 1: Získejte Service Account JSON

1. Jděte na [Google Cloud Console](https://console.cloud.google.com)
2. Vyberte projekt (nebo vytvořte nový)
3. **Zapněte Text-to-Speech API:**
   - APIs & Services → Enable APIs and Services
   - Hledejte: "Cloud Text-to-Speech API"
   - Enable
4. **Vytvořte Service Account:**
   - IAM & Admin → Service Accounts
   - Create Service Account
   - Name: `tts-service-account`
   - Role: `Cloud Text-to-Speech User`
5. **Stáhněte JSON klíč:**
   - Klikněte na vytvořený service account
   - Keys → Add Key → Create New Key
   - Vyberte: **JSON**
   - Download

### Krok 2: Přesuňte JSON do projektu

```bash
# Přesuňte stažený JSON do secrets/
mv ~/Downloads/your-project-*.json backend/secrets/google-tts-key.json
```

**Nebo jakýkoliv název:**
- `backend/secrets/service-account.json`
- `backend/secrets/my-key.json`
- Cokoliv končící na `.json`

---

## ⚡ Spusťte Setup Script

Po přidání JSON souboru spusťte:

```bash
python3 setup_google_tts.py
```

**Script automaticky:**
1. ✅ Najde JSON v `backend/secrets/`
2. ✅ Aktualizuje `backend/.env` s `GOOGLE_APPLICATION_CREDENTIALS`
3. ✅ Restartuje backend
4. ✅ Spustí E2E smoke test
5. ✅ Vypíše **PASS/FAIL**

---

## 📊 Očekávaný výstup

```
======================================================================
  🚀 Google TTS Setup Script
======================================================================

🔹 Krok 1: Hledání service account JSON
----------------------------------------------------------------------
✅ Nalezen: google-tts-key.json
   Cesta: /Users/petrliesner/podcasts/backend/secrets/google-tts-key.json
✅ Validní service account JSON
   Project ID: my-project-12345
   Email: tts-service-account@my-project-12345.iam.gserviceaccount.com

🔹 Krok 2: Aktualizace backend/.env
----------------------------------------------------------------------
   Čtu existující .env
   Nastavuji GCP_TTS_VOICE_NAME=en-US-Neural2-D
   Nastavuji GCP_TTS_LANGUAGE_CODE=en-US
   Nastavuji GCP_TTS_SPEAKING_RATE=1.0
   Nastavuji GCP_TTS_PITCH=0.0
✅ Aktualizováno .env
   GOOGLE_APPLICATION_CREDENTIALS=/Users/petrliesner/podcasts/backend/secrets/google-tts-key.json

🔹 Krok 3: Zastavení běžícího backendu
----------------------------------------------------------------------
   Zastavuji proces PID 92247
✅ Backend zastaven

🔹 Krok 4: Spuštění backendu
----------------------------------------------------------------------
   Backend startuje (PID 93456)
   Log: /tmp/backend_setup.log
   Čekám na start..........
✅ Backend běží na http://localhost:50000

🔹 Krok 5: Spuštění E2E smoke testu
----------------------------------------------------------------------
======================================================================
  🔥 E2E SMOKE TEST: TTS → Video Concatenation
======================================================================

✅ Backend běží a je dostupný
🧹 Čistím staré MP3 soubory...
   Smazáno 0 souborů

🔹 Krok 1: Generování TTS (3 bloky)
----------------------------------------------------------------------
🔄 Refreshing Google Cloud access token...
✅ Token refreshed. Expires in 3599 seconds.
📡 HTTP Status: 200
✅ TTS generování úspěšné: 3/3 bloků

🔹 Krok 2: Ověření MP3 souborů
----------------------------------------------------------------------
✅ Narrator_0001.mp3 existuje (45234 bytes)
✅ Narrator_0002.mp3 existuje (67891 bytes)
✅ Narrator_0003.mp3 existuje (52345 bytes)
✅ Všechny 3 MP3 soubory existují

======================================================================
📊 FINÁLNÍ SOUHRN
======================================================================
✅ Service account JSON:  OK
✅ Backend .env update:   OK
✅ Backend restart:       OK
✅ E2E smoke test:        PASS

======================================================================
🎉 SUCCESS: Setup kompletní! Google TTS funguje.
⏱️  Celková doba: 45.3s
======================================================================

📁 Vygenerované soubory:
   - uploads/Narrator_*.mp3 (TTS audio)
   - output/final_video_*.mp4 (finální video)

🚀 Můžete použít frontend nebo přímo API:
   http://localhost:50000/api/tts/generate
```

---

## 🎯 Co bylo připraveno

### ✅ Infrastruktura (hotovo)

1. **Secrets adresář:** `backend/secrets/`
   - ✅ Vytvořen
   - ✅ V `.gitignore` (bezpečné pro git)
   - ✅ README s instrukcemi

2. **Setup script:** `setup_google_tts.py`
   - ✅ Auto-detekce JSON souborů
   - ✅ Auto-konfigurace `.env`
   - ✅ Backend restart
   - ✅ E2E test execution
   - ✅ PASS/FAIL reporting

3. **E2E smoke test:** `backend/e2e_smoke_test.py`
   - ✅ TTS generation test (3 bloky)
   - ✅ MP3 file verification
   - ✅ Video concatenation test
   - ✅ Clear PASS/FAIL output

4. **Git security:** `.gitignore`
   - ✅ `backend/secrets/*.json` ignored
   - ✅ Service account keys won't leak

---

## 🔧 Troubleshooting

### "Žádný .json soubor v backend/secrets"

**Příčina:** JSON klíč nebyl přidán  
**Řešení:** Zkopírujte JSON soubor do `backend/secrets/`

```bash
mv ~/Downloads/your-key.json backend/secrets/google-tts-key.json
```

### "403 Forbidden" v E2E testu

**Příčina:** API není enabled nebo billing chybí  
**Řešení:**
1. Google Cloud Console → APIs & Services
2. Zapněte: "Cloud Text-to-Speech API"
3. Zkontrolujte billing account

### "401 Unauthorized" v E2E testu

**Příčina:** Service account nemá správnou roli  
**Řešení:**
1. Google Cloud Console → IAM & Admin → Service Accounts
2. Najděte váš service account
3. Přidejte roli: "Cloud Text-to-Speech User"

### Backend se nespustí

**Příčina:** Port 50000 je obsazený nebo dependencies chybí  
**Řešení:**
```bash
# Zabijte proces na portu
lsof -ti tcp:50000 | xargs kill -9

# Nainstalujte dependencies
cd backend && pip3 install -r requirements.txt

# Spusťte manuálně pro debugging
cd backend && python3 app.py
```

---

## 📚 Dokumentace

- **[E2E_FINAL_SUMMARY.md](E2E_FINAL_SUMMARY.md)** - Kompletní test výsledky
- **[GOOGLE_TTS_SETUP.md](GOOGLE_TTS_SETUP.md)** - Detailní TTS setup
- **[TOKEN_FIX_CRITICAL.md](TOKEN_FIX_CRITICAL.md)** - Token refresh implementace
- **[backend/secrets/README.md](backend/secrets/README.md)** - Security guide

---

## ✅ Status

**Připraveno:** ✅ 100%  
**Čeká na:** Service account JSON od uživatele  
**Časová náročnost:** ~2 minuty (get JSON + run script)

**Instrukce pro uživatele:**
1. Stáhněte service account JSON z Google Cloud Console
2. Přesuňte do `backend/secrets/`
3. Spusťte `python3 setup_google_tts.py`
4. Čekejte na **PASS** ✅

**Vše ostatní je automatické!** 🚀



