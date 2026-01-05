# 🚀 Google TTS Quick Start

Rychlý guide pro spuštění Google TTS generování (5 minut setup).

---

## 📋 Co potřebuješ

1. Google Cloud účet (free tier OK)
2. Service Account JSON klíč
3. Backend běžící

---

## ⚡ 3 kroky k prvnímu audio

### 1️⃣ Google Cloud setup (5 min)

```bash
# 1. Jdi na https://console.cloud.google.com/
# 2. Vytvoř projekt: "podcasts-tts"
# 3. Zapni API: Cloud Text-to-Speech API
# 4. Vytvoř Service Account:
#    - Name: podcasts-tts
#    - Role: Cloud Text-to-Speech User
# 5. Stáhni JSON klíč
# 6. Přesuň ho např. do ~/credentials/
```

### 2️⃣ Nastav ENV

```bash
cd backend
cp env_example.txt .env
nano .env
```

Změň tyto řádky:
```bash
GOOGLE_APPLICATION_CREDENTIALS=/Users/tvoje_jmeno/credentials/podcasts-tts-XXXXX.json
GCP_TTS_VOICE_NAME=en-US-Neural2-D
GCP_TTS_LANGUAGE_CODE=en-US
```

**DŮLEŽITÉ:** Použij absolutní cestu (ne `~/`)!

### 3️⃣ Instalace & Test

```bash
# Instaluj Google TTS
cd backend
pip install google-cloud-texttospeech

# Restart backend
python3 app.py
```

V **novém terminálu**:
```bash
cd backend
./test_tts_curl.sh
```

---

## ✅ Očekávaný výstup

```
✅ SUCCESS!

📈 Stats:
  - Vygenerováno: 2 / 2 bloků
  - Výstup: /Users/.../podcasts/uploads

📁 Ověřuji soubory:
  ✅ Narrator_0001.mp3 (45821 bytes)
  ✅ Narrator_0002.mp3 (52134 bytes)
```

---

## 🎬 Použití v pipeline

### Option A: Přímý JSON

```bash
curl -X POST http://localhost:50000/api/tts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tts_ready_package": {
      "narration_blocks": [
        {"block_id": "b_001", "text_tts": "Your text here"}
      ]
    }
  }'
```

### Option B: Z ScriptPackage (z LLM pipeline)

```python
import requests

# Po dokončení script pipeline (LLM1-5)
script_state = project_store.read_script_state(episode_id)
tts_package = script_state['tts_ready_package']

# Vygeneruj audio
response = requests.post(
    'http://localhost:50000/api/tts/generate',
    json={'tts_ready_package': tts_package}
)

result = response.json()
print(f"Vygenerováno {result['generated_blocks']} bloků")
```

### Option C: Frontend integrace

```javascript
// Po script generation
const response = await axios.post('/api/tts/generate', {
  tts_ready_package: scriptState.tts_ready_package
});

if (response.data.success) {
  console.log(`Audio ready: ${response.data.generated_blocks} files`);
  // Nyní můžeš volat /api/generate-video-with-audio
}
```

---

## 🔧 Troubleshooting

### Backend neodpovídá
```bash
# Zkontroluj, že běží
curl http://localhost:50000/api/health
```

### "Chybí GOOGLE_APPLICATION_CREDENTIALS"
```bash
# Zkontroluj .env
cat backend/.env | grep GOOGLE_APPLICATION_CREDENTIALS

# Zkontroluj, že soubor existuje
ls -la /path/uvedená/v/env
```

### "Permission denied" (403)
```bash
# Service Account potřebuje roli v Google Cloud Console:
# IAM & Admin → IAM → přidej "Cloud Text-to-Speech User"
```

---

## 📊 Co dál?

1. **Změň hlas:**
   ```bash
   # V .env změň:
   GCP_TTS_VOICE_NAME=en-US-Studio-O  # Premium female
   ```

2. **Upravit rychlost:**
   ```bash
   GCP_TTS_SPEAKING_RATE=0.9  # Pomalejší
   ```

3. **Generuj dlouhé dokumenty:**
   - 40 minut = ~200 bloků = cca 5-10 minut generování
   - Endpoint má automatický retry při rate limits

4. **Integrace s video:**
   - Po vygenerování audio automaticky volej:
   ```bash
   POST /api/generate-video-with-audio
   ```

---

## 📚 Více info

- **Setup detaily:** `GOOGLE_TTS_SETUP.md`
- **Voice options:** [Google TTS Voices](https://cloud.google.com/text-to-speech/docs/voices)
- **Test skript:** `backend/test_tts_endpoint.py`

---

**Hotovo!** 🎉 Teď máš funkční Google TTS pipeline.



