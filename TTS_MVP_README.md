# 🎤 Google TTS MVP Implementation

**Status:** ✅ Ready for testing  
**Endpoint:** `POST /api/tts/generate`  
**Backend:** Flask (port 50000)

---

## 📦 Co bylo implementováno

### ✅ 1. Nový endpoint `/api/tts/generate`

**Lokace:** `backend/app.py` (před `if __name__ == '__main__'`)

**Features:**
- ✅ Přijímá `tts_ready_package` (nebo celé `ScriptPackage`)
- ✅ Validace `narration_blocks[]`
- ✅ Per-block processing (loop přes bloky)
- ✅ Google Cloud TTS integrace
- ✅ MP3 výstup do `uploads/Narrator_XXXX.mp3`
- ✅ Fixed-width číslování (4 cifry)
- ✅ Retry mechanismus (max 3x per block)
- ✅ Exponential backoff (1s → 2s → 4s)
- ✅ Rate limit handling (429)
- ✅ Server error handling (5xx)
- ✅ Detailní logging
- ✅ JSON response se souhrnem

### ✅ 2. ENV konfigurace

**Lokace:** `backend/.env` (template: `env_example.txt`)

```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GCP_TTS_VOICE_NAME=en-US-Neural2-D
GCP_TTS_LANGUAGE_CODE=en-US
GCP_TTS_SPEAKING_RATE=1.0
GCP_TTS_PITCH=0.0
```

### ✅ 3. Dependencies

**Lokace:** `backend/requirements.txt`

```
google-cloud-texttospeech>=2.14.1
```

### ✅ 4. Test nástroje

| Soubor | Popis |
|--------|-------|
| `test_tts_endpoint.py` | Python test skript (3 bloky) |
| `test_tts_curl.sh` | Bash curl test (2 bloky) |
| `GOOGLE_TTS_SETUP.md` | Detailní setup guide |
| `QUICK_START_TTS.md` | 5min quick start |

---

## 🚀 Jak to spustit

### Krok 1: Google Cloud setup

```bash
# 1. Jdi na https://console.cloud.google.com/
# 2. Vytvoř projekt + zapni Cloud Text-to-Speech API
# 3. Vytvoř Service Account + stáhni JSON klíč
# 4. Ulož klíč do ~/credentials/
```

**Detaily:** `GOOGLE_TTS_SETUP.md`

### Krok 2: Backend konfigurace

```bash
cd backend

# Nastav ENV
cp env_example.txt .env
nano .env  # změň GOOGLE_APPLICATION_CREDENTIALS na absolutní cestu

# Instaluj dependencies
pip install -r requirements.txt

# Restart backend
python3 app.py
```

### Krok 3: Test

```bash
# Python test (doporučeno)
python3 test_tts_endpoint.py

# nebo Bash test
./test_tts_curl.sh
```

**Očekávaný výstup:**
```
✅ SUCCESS!
📈 Vygenerováno 3/3 audio bloků
📁 uploads/Narrator_0001.mp3 (45821 bytes)
📁 uploads/Narrator_0002.mp3 (52134 bytes)
📁 uploads/Narrator_0003.mp3 (48392 bytes)
```

---

## 📡 API Reference

### Request

**Endpoint:** `POST http://localhost:50000/api/tts/generate`

**Headers:**
```
Content-Type: application/json
```

**Body (Option A - TTS package):**
```json
{
  "tts_ready_package": {
    "episode_id": "ep_xxx",
    "language": "en-US",
    "narration_blocks": [
      {
        "block_id": "b_0001",
        "text_tts": "Your narration text here"
      }
    ]
  }
}
```

**Body (Option B - Script package):**
```json
{
  "script_package": {
    "tts_ready_package": {
      "narration_blocks": [...]
    }
  }
}
```

### Response (Success)

```json
{
  "success": true,
  "total_blocks": 10,
  "generated_blocks": 10,
  "failed_blocks_count": 0,
  "failed_blocks": [],
  "output_dir": "/path/to/uploads",
  "message": "Vygenerováno 10/10 audio bloků",
  "generated_files": [
    "Narrator_0001.mp3",
    "Narrator_0002.mp3",
    "..."
  ]
}
```

### Response (Partial Success)

```json
{
  "success": true,
  "total_blocks": 10,
  "generated_blocks": 8,
  "failed_blocks_count": 2,
  "failed_blocks": [
    {
      "index": 3,
      "block_id": "b_0003",
      "error": "Rate limit (429): ..."
    }
  ],
  "output_dir": "/path/to/uploads",
  "message": "Vygenerováno 8/10 audio bloků"
}
```

### Response (Error)

```json
{
  "success": false,
  "error": "Chybí GOOGLE_APPLICATION_CREDENTIALS v .env",
  "hint": "Nastavte cestu k service account JSON souboru",
  "total_blocks": 0,
  "generated_blocks": 0
}
```

**HTTP Status Codes:**
- `200`: Success (i když některé bloky failnou)
- `400`: Bad request (chybí narration_blocks)
- `500`: Server error (Google TTS nedostupný)

---

## 🔧 Konfigurace

### Voice options (EN-US)

| Voice | Type | Gender | Kvalita | Cena |
|-------|------|--------|---------|------|
| `en-US-Neural2-D` | Neural2 | Male | ⭐⭐⭐⭐ | $4/1M chars |
| `en-US-Neural2-F` | Neural2 | Female | ⭐⭐⭐⭐ | $4/1M chars |
| `en-US-Studio-O` | Studio | Female | ⭐⭐⭐⭐⭐ | $160/1M chars |
| `en-US-Studio-Q` | Studio | Male | ⭐⭐⭐⭐⭐ | $160/1M chars |

**Doporučení pro MVP:** `en-US-Neural2-D` (dobrý poměr kvalita/cena)

### Speaking rate

```bash
GCP_TTS_SPEAKING_RATE=1.0   # Normal (160 WPM)
GCP_TTS_SPEAKING_RATE=0.9   # Slower (144 WPM) - doporučeno pro komplex
GCP_TTS_SPEAKING_RATE=1.1   # Faster (176 WPM) - dynamičtější
```

**Range:** 0.25 - 4.0

### Pitch

```bash
GCP_TTS_PITCH=0.0   # Natural
GCP_TTS_PITCH=-2.0  # Lower voice
GCP_TTS_PITCH=2.0   # Higher voice
```

**Range:** -20.0 až 20.0

---

## 🎬 Integrace s video pipeline

**Automatická!** Žádná změna nutná.

Existující endpoint `/api/generate-video-with-audio` automaticky hledá:
```python
for filename in os.listdir(UPLOAD_FOLDER):
    if filename.startswith('Narrator_') and filename.endswith('.mp3'):
        narrator_files.append(filename)
```

**Flow:**
1. Generate script (LLM1-5) → `tts_ready_package`
2. **Generate audio** → `POST /api/tts/generate`
3. Generate video → `POST /api/generate-video-with-audio`

---

## 📊 Performance & Limity

### Rychlost generování

| Bloků | Čas | Audio délka |
|-------|-----|-------------|
| 10 | ~30s | ~1 minuta |
| 50 | ~2 min | ~5 minut |
| 200 | ~8 min | ~40 minut |

**Poznámka:** Čas závisí na network latency a Google TTS load.

### Google TTS limity

**Free tier:**
- 1M characters / měsíc zdarma
- 40 minut audio ≈ 40,000 chars ≈ 4% limitu

**Rate limits:**
- 300 requests/minute (dostatečné pro MVP)
- Endpoint má automatický retry + exponential backoff

### Velikost souborů

- ~1.5 kB per slovo (MP3)
- 40 minut ≈ 6,000 slov ≈ 9 MB celkem

---

## 🛡️ Error Handling

### Per-block retry

```
Attempt 1: fail (429) → wait 1s
Attempt 2: fail (5xx) → wait 2s
Attempt 3: fail (timeout) → mark as FAILED
→ Continue to next block
```

**Result:** Partial success možný (8/10 bloků OK)

### Handled errors

| Error | Code | Action |
|-------|------|--------|
| Rate limit | 429 | Retry 3x s backoff |
| Server error | 5xx | Retry 3x s backoff |
| Network timeout | - | Retry 3x s backoff |
| Empty text | - | Skip block |
| Auth error | 401 | Immediate fail |

### Recovery strategy

Pokud některé bloky failnou:
1. Fix problém (credentials, network, atd.)
2. **Re-run stejný request**
3. Endpoint smaže staré `Narrator_*.mp3` před startem
4. → Čisté regenerování

---

## 🧪 Testing Checklist

- [ ] Backend běží na http://localhost:50000
- [ ] `pip install google-cloud-texttospeech` hotovo
- [ ] `GOOGLE_APPLICATION_CREDENTIALS` nastaven (absolutní cesta)
- [ ] Service account JSON existuje
- [ ] `/api/health` vrací OK
- [ ] `test_tts_curl.sh` projde ✅
- [ ] `test_tts_endpoint.py` projde ✅
- [ ] Soubory `Narrator_0001.mp3` existují v `/uploads/`
- [ ] Video pipeline (`generate_video_with_audio`) funguje

---

## 🐛 Known Issues & Limitations

### MVP omezení (záměrné)

- ❌ **Bez SSML:** Plain text pouze (pauzy pomocí `...`)
- ❌ **Bez paralelizace:** Sequential processing (bezpečnější)
- ❌ **Bez cachingu:** Stejný text = nové volání API
- ❌ **Bez progress tracking:** No real-time progress updates
- ❌ **Bez partial regeneration:** Celý dokument vždy znovu

### Future improvements (P2)

- [ ] SSML podpora (Google native breaks/emphasis)
- [ ] Parallel batch processing (5-10 bloků najednou)
- [ ] Text → audio cache (reuse stejných bloků)
- [ ] Streaming progress (WebSocket nebo SSE)
- [ ] Selective regeneration (jen failed bloky)

---

## 📚 Dokumentace

| Soubor | Obsah |
|--------|-------|
| `GOOGLE_TTS_SETUP.md` | Detailní setup guide (Google Cloud + ENV) |
| `QUICK_START_TTS.md` | 5min quick start guide |
| `TTS_MVP_README.md` | Tento soubor (overview) |
| `backend/test_tts_endpoint.py` | Python test script |
| `backend/test_tts_curl.sh` | Bash curl test |

---

## 🔗 Užitečné odkazy

- [Google Cloud TTS Docs](https://cloud.google.com/text-to-speech/docs)
- [Voice List](https://cloud.google.com/text-to-speech/docs/voices)
- [Pricing](https://cloud.google.com/text-to-speech/pricing)
- [SSML Reference](https://cloud.google.com/text-to-speech/docs/ssml)

---

## 📞 Support

**Issues:**
1. Zkontroluj `GOOGLE_TTS_SETUP.md` troubleshooting
2. Spusť test skripty
3. Zkontroluj backend logy

**Common fixes:**
- Restart backend po změně `.env`
- Použij absolutní cesty (ne `~/`)
- Zkontroluj Google Cloud billing (i free tier potřebuje platební metodu)

---

**Status:** ✅ MVP hotovo, ready for production testing

**Next steps:**
1. Setup Google Cloud (5 min)
2. Test s 3 bloky (1 min)
3. Test s real `tts_ready_package` (2 min)
4. Integrace s video pipeline (0 min - auto)

🎉 **Let's generate some audio!**



