# AI Voice Block Combiner

Moderní webová aplikace pro generování, kombinování a zpracování audio souborů pomocí ElevenLabs Text-to-Speech API s pokročilými funkcemi pro tvorbu videí a titulků.

## 🎯 Funkce

### 🎤 Generování hlasů
- **ElevenLabs TTS integrace** - Pokročilé generování hlasů pomocí AI
- **Batch zpracování** - Generování více hlasových bloků najednou
- **Voice mapping** - Podpora pro různé hlasové profily
- **JSON konfigurace** - Snadná správa hlasových bloků

### 🔊 Audio zpracování
- **Volume control** - Individuální nastavení hlasitosti pro každý hlas
- **Paměťový systém** - Automatické ukládání nastavení hlasitosti
- **Audio kombinování** - Spojování souborů s konfigurovatelnou pauzou
- **Formát podpora** - MP3, WAV, M4A

### 🎬 Video generování
- **Waveform vizualizace** - Automatické generování waveform videa
- **Obrázek pozadí** - Podpora PNG, JPG, JPEG
- **Video pozadí** - Podpora MP4, MOV s loop funkcí
- **Titulky** - Automatické generování SRT souborů s konfigurovatelnou velikostí

### ⚡ Pokročilé funkce
- **Timeout ochrana** - Prodloužené timeouty pro velké projekty (120+ souborů)
- **Auto-sorting** - Zachování pořadí dialogů (Tesla_01 → Socrates_01 → Tesla_02...)
- **Real-time progress** - Živé sledování průběhu zpracování
- **Error handling** - Robustní zpracování chyb s detailním logováním

## 🛠️ Technické požadavky

### Backend
- **Python 3.8+**
- **Flask** - Web framework
- **pydub** - Audio zpracování
- **FFmpeg** - Video/audio konverze
- **requests** - HTTP komunikace

### Frontend
- **Node.js 16+**
- **React 18** - UI framework
- **Tailwind CSS** - Styling
- **Axios** - HTTP klient

### Systémové požadavky
- **FFmpeg** nainstalované v systému
- **ElevenLabs API klíč**
- **4GB+ RAM** pro velké projekty
- **SSD storage** doporučeno pro rychlé zpracování

## 📦 Instalace

### 1. Klonování projektu
```bash
git clone <repository-url>
cd podcasts
```

### 2. Backend setup
```bash
cd backend
pip install -r requirements.txt
```

### 3. Frontend setup
```bash
cd frontend
npm install
```

### 4. Environment konfigurace
Vytvořte `.env` soubor v `backend/` složce:
```env
ELEVENLABS_API_KEY=your_api_key_here
FLASK_ENV=development
```

## 🚀 Spuštění

### Development mode
```bash
# Terminal 1 - Backend
cd backend
python3 app.py

# Terminal 2 - Frontend  
cd frontend
PORT=4000 npm start
```

### Přístup k aplikaci
- **Frontend:** http://localhost:4000
- **Backend API:** http://localhost:5000
- **Health check:** http://localhost:5000/api/health

## 📚 API Dokumentace

### Voice Generation
```http
POST /api/generate-voices
Content-Type: application/json

{
  "voice_blocks": {
    "Tesla_01": {
      "voice_id": "voice_id_here",
      "text": "Text to convert to speech"
    }
  },
  "api_key": "your_elevenlabs_api_key"
}
```

### Audio Processing
```http
POST /api/upload
Content-Type: multipart/form-data

{
  "audio_files": [File[]],
  "pause_duration": 0.6,
  "generate_subtitles": true,
  "generate_video": true,
  "background_filename": "background.jpg",
  "file_volumes": {"file1.mp3": 5.0}
}
```

### File Management
```http
GET /api/files                    # List audio files
GET /api/list-backgrounds         # List image backgrounds  
GET /api/list-video-backgrounds   # List video backgrounds
GET /api/download/<filename>      # Download generated files
```

## 📁 Struktura projektu

```
podcasts/
├── backend/
│   ├── app.py                 # Flask server
│   ├── requirements.txt       # Python dependencies
│   └── env_example.txt       # Environment template
├── frontend/
│   ├── src/
│   │   ├── App.js            # Main React component
│   │   ├── components/       # React components
│   │   └── index.css         # Styles
│   ├── package.json          # Node dependencies
│   └── tailwind.config.js    # Tailwind configuration
├── uploads/                  # Input audio files
├── output/                   # Generated files
├── README.md                # Documentation
└── start.sh                 # Startup script
```

## ⚙️ Konfigurace

### Volume Control
Hlasitost se nastavuje v decibelech (-20dB až +20dB):
```json
{
  "Tesla_voice": 15.0,    // +15dB boost
  "Socrates_voice": 0.0   // No change
}
```

### Video nastavení
```javascript
// Velikost titulků (v pixelech)
FontSize: 16              // Menší titulky
FontSize: 32              // Větší titulky

// Timeouts (v milisekundách)  
timeout: 1200000          // 20 minut pro velké projekty
```

### Podporované formáty
- **Audio:** MP3, WAV, M4A
- **Obrázky:** PNG, JPG, JPEG
- **Video:** MP4, MOV
- **Titulky:** SRT

## 🐛 Troubleshooting

### Backend nespouští
```bash
# Zkontrolujte Python verzi
python3 --version

# Zkontrolujte port 5000
lsof -ti:5000
kill <PID>

# Restartujte server
cd backend && python3 app.py
```

### Frontend chyby
```bash
# Vyčistěte cache
rm -rf node_modules package-lock.json
npm install

# Restart na jiném portu
PORT=4001 npm start
```

### FFmpeg problémy
```bash
# MacOS
brew install ffmpeg

# Ubuntu/Debian  
sudo apt update && sudo apt install ffmpeg

# Ověření instalace
ffmpeg -version
```

### ElevenLabs API chyby
- Zkontrolujte platnost API klíče
- Ověřte credit limit
- Zkontrolujte voice_id formát

### Velké soubory timeout
```javascript
// Frontend - zvyšte timeout
timeout: 1800000  // 30 minut

// Backend - prodloužení processing timeout
subprocess.run(..., timeout=1800)
```

## 📋 Známé limity

- **Velikost souborů:** Max 100MB pro video pozadí
- **Počet souborů:** Testováno až do 150 audio bloků
- **Generování času:** ~20 minut pro 120+ souborů
- **Paměť:** 4GB+ RAM pro velké projekty

## 🔧 Development

### Debug mode
```bash
# Backend s debug logováním
FLASK_ENV=development python3 app.py

# Frontend s hot reload
npm start
```

### Testing
```bash
# Test API health
curl http://localhost:5000/api/health

# Test file upload
curl -X POST -F "audio_files=@test.mp3" http://localhost:5000/api/upload
```

## 📞 Podpora

Pro technické problémy:
1. Zkontrolujte logy v terminálu
2. Ověřte všechny požadavky jsou splněny
3. Restartujte oba servery
4. Zkontrolujte síťové připojení pro ElevenLabs API

---

**Verze:** 2.0.0  
**Poslední aktualizace:** Červenec 2025  
**Kompatibilita:** Python 3.8+, Node.js 16+, FFmpeg 4.0+
