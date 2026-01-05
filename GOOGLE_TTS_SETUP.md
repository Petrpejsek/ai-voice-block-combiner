# Google Cloud Text-to-Speech Setup Guide

## 🎯 MVP Implementace - rychlý start

Tento guide popisuje, jak nastavit Google Cloud TTS pro automatické generování audio z `tts_ready_package`.

---

## 📋 Prerekvizity

1. **Google Cloud účet** (free tier má 1M characters/měsíc zdarma)
2. **Python 3.8+** s nainstalovanými dependencies
3. **Backend běžící** na http://localhost:50000

---

## 🚀 Setup (krok za krokem)

### 1. Vytvoř Google Cloud projekt

1. Jdi na [Google Cloud Console](https://console.cloud.google.com/)
2. Vytvoř nový projekt (např. "podcasts-tts")
3. Zapni **Cloud Text-to-Speech API**:
   - Jdi na "APIs & Services" → "Enable APIs and Services"
   - Hledej "Cloud Text-to-Speech API"
   - Klikni "Enable"

### 2. Vytvoř Service Account

1. Jdi na "IAM & Admin" → "Service Accounts"
2. Klikni "Create Service Account"
3. Název: `podcasts-tts-service` (nebo libovolný)
4. Role: **"Cloud Text-to-Speech User"** (nebo Editor pro testing)
5. Klikni "Done"

### 3. Stáhni Service Account JSON klíč

1. V seznamu Service Accounts klikni na právě vytvořený account
2. Tab "Keys" → "Add Key" → "Create new key"
3. Typ: **JSON**
4. Stáhne se soubor `podcasts-tts-service-XXXXXX.json`
5. Přesuň ho do bezpečného místa (např. `~/credentials/`)
6. **NIKDY ho necommituj do gitu!**

### 4. Nastav ENV proměnné

Edituj `/backend/.env` (nebo vytvoř z `env_example.txt`):

```bash
# Google Cloud Text-to-Speech
GOOGLE_APPLICATION_CREDENTIALS=/Users/petrliesner/credentials/podcasts-tts-service-XXXXXX.json
GCP_TTS_VOICE_NAME=en-US-Neural2-D
GCP_TTS_LANGUAGE_CODE=en-US
GCP_TTS_SPEAKING_RATE=1.0
GCP_TTS_PITCH=0.0
```

**Důležité:**
- Cesta musí být **absolutní** (ne `~/` ale `/Users/username/...`)
- Soubor musí existovat a být readable

### 5. Instaluj dependencies

```bash
cd backend
pip install -r requirements.txt
```

Důležité packages:
```
google-auth>=2.16.0  # Pro OAuth2 autentizaci s Google Cloud
requests>=2.31.0     # Pro REST API volání
```

**Poznámka:** Používáme REST API přístup místo heavyweight client library.

### 6. Restart backend

```bash
cd backend
python3 app.py
```

Backend by měl běžet na: http://localhost:50000

---

## 🧪 Test endpoint

### Rychlý test (curl)

```bash
curl -X POST http://localhost:50000/api/tts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tts_ready_package": {
      "narration_blocks": [
        {
          "block_id": "test_001",
          "text_tts": "Hello, this is a test of Google Cloud Text to Speech."
        }
      ]
    }
  }'
```

**Očekávaný výstup:**
```json
{
  "success": true,
  "total_blocks": 1,
  "generated_blocks": 1,
  "failed_blocks_count": 0,
  "output_dir": "/path/to/uploads",
  "message": "Vygenerováno 1/1 audio bloků",
  "generated_files": ["Narrator_0001.mp3"]
}
```

### Python test skript

```bash
cd backend
python3 test_tts_endpoint.py
```

---

## 📁 Výstup

Vygenerované MP3 soubory:
```
uploads/
├── Narrator_0001.mp3
├── Narrator_0002.mp3
├── Narrator_0003.mp3
└── ...
```

**Naming convention:**
- `Narrator_{index:04d}.mp3` (4 číslice)
- Index začíná od 1
- Pořadí = pořadí v `narration_blocks[]`

---

## 🎤 Voice Options

### Dostupné hlasy (EN-US)

| Voice Name | Typ | Gender | Doporučení |
|------------|-----|--------|------------|
| `en-US-Neural2-D` | Neural2 | Male | ✅ Dokumenty, profesionální |
| `en-US-Neural2-F` | Neural2 | Female | ✅ Dokumenty, přátelský |
| `en-US-Studio-O` | Studio | Female | ⭐ Nejvyšší kvalita |
| `en-US-Studio-Q` | Studio | Male | ⭐ Nejvyšší kvalita |
| `en-US-Wavenet-D` | Wavenet | Male | Legacy (starší) |

**Pro MVP doporučuji:**
- `en-US-Neural2-D` (male, dobře čitelný)
- `en-US-Studio-O` (female, premium kvalita)

### Otestuj různé hlasy

Změň v `.env`:
```bash
GCP_TTS_VOICE_NAME=en-US-Studio-O
```

Restart backend a vygeneruj znovu.

---

## ⚙️ Parametry

### Speaking Rate (rychlost řeči)

```bash
GCP_TTS_SPEAKING_RATE=1.0   # Default (normální rychlost)
GCP_TTS_SPEAKING_RATE=0.8   # Pomalejší (pro komplikovaný obsah)
GCP_TTS_SPEAKING_RATE=1.2   # Rychlejší (pro dynamiku)
```

**Range:** 0.25 - 4.0

### Pitch (výška hlasu)

```bash
GCP_TTS_PITCH=0.0    # Default (přirozená výška)
GCP_TTS_PITCH=-2.0   # Nižší hlas
GCP_TTS_PITCH=2.0    # Vyšší hlas
```

**Range:** -20.0 až 20.0 (doporučuji -5.0 až 5.0)

---

## 🔧 Troubleshooting

### Error: "google-cloud-texttospeech není nainstalován"

```bash
pip install google-cloud-texttospeech
```

### Error: "Chybí GOOGLE_APPLICATION_CREDENTIALS"

Zkontroluj `.env`:
```bash
cat backend/.env | grep GOOGLE_APPLICATION_CREDENTIALS
```

Cesta musí být absolutní.

### Error: "Service account soubor neexistuje"

```bash
# Zkontroluj, že soubor existuje
ls -la /path/to/your/service-account-key.json
```

### Error: "Permission denied" nebo "403"

Service Account potřebuje roli:
- "Cloud Text-to-Speech User" (minimum)
- nebo "Editor" (pro testing)

Zkontroluj v Google Cloud Console → IAM & Admin → IAM

### Rate limit (429)

Endpoint automaticky retry s exponential backoff.

Free tier limit: **1 milion characters / měsíc**

40 minut audio = cca 40,000 characters = 4% limitu

---

## 📊 Ceny (pro info)

**Free tier:**
- 1 milion characters/měsíc zdarma
- Standard voices (Neural2): **$4** per 1M characters
- WaveNet voices: **$16** per 1M characters
- Studio voices: **$160** per 1M characters (!)

**Doporučení pro MVP:**
- Použij **Neural2** voices (dobrý poměr kvalita/cena)
- Free tier pokryje cca **25 hodin** audio měsíčně

---

## 🔗 Užitečné odkazy

- [Google Cloud TTS Docs](https://cloud.google.com/text-to-speech/docs)
- [Voice List](https://cloud.google.com/text-to-speech/docs/voices)
- [SSML Guide](https://cloud.google.com/text-to-speech/docs/ssml) (pro future)
- [Pricing](https://cloud.google.com/text-to-speech/pricing)

---

## ✅ Checklist před prvním použitím

- [ ] Google Cloud projekt vytvořen
- [ ] Cloud Text-to-Speech API zapnuta
- [ ] Service Account vytvořen
- [ ] JSON klíč stažen
- [ ] `GOOGLE_APPLICATION_CREDENTIALS` v `.env` nastaven (absolutní cesta)
- [ ] `google-cloud-texttospeech` nainstalován
- [ ] Backend restartován
- [ ] Test endpoint funguje (curl nebo Python skript)
- [ ] Soubory `Narrator_0001.mp3` existují v `/uploads/`

---

## 🎬 Integrace s video pipeline

**Automatická!** Existující `generate_video_with_audio()` hledá:
```python
for filename in os.listdir(UPLOAD_FOLDER):
    if filename.startswith('Narrator_') and filename.endswith('.mp3'):
        narrator_files.append(filename)
```

→ Žádná změna nutná, funguje okamžitě!

---

**Hotovo!** 🎉 Teď můžeš generovat 40min audio dokumenty s Google TTS.

