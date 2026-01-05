# ✅ UI Cleanup - Finální Stav

## Úpravy v `frontend/src/App.js`

### 1. Skryté komponenty (using `{false && (...)}`):

#### A) **VoiceGenerationQueue** (řádek ~1580-1588)
```jsx
{false && (
  <div className="mb-8">
    <VoiceGenerationQueue 
      ref={voiceQueueRef}
      elevenlabsApiKey={elevenlabsApiKey}
      onVoicesGenerated={handleVoicesGenerated}
      onApiKeyRequired={handleApiKeyRequired}
    />
  </div>
)}
```
**Důvod:** Stará ElevenLabs fronta - nahrazeno Google Cloud TTS v VideoProductionPipeline.

#### B) **Video Generation Studio** (řádek ~1590-1612)
```jsx
{false && (
  <div className="mb-8">
    <div className="bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg p-6 text-white">
      ...DALL-E video generator...
    </div>
  </div>
)}
```
**Důvod:** Starý purple banner pro DALL-E videa - nahrazeno archive.org pipeline (AAR + CB).

#### C) **Voice Generator Card** (řádek ~1614-1619)
```jsx
{false && (
  <div className="bg-white rounded-lg shadow-sm mb-6">
    <VoiceGenerator 
      onVoicesGenerated={handleVoicesGenerated}
    />
  </div>
)}
```
**Důvod:** Ruční generování hlasů z JSON - nahrazeno automatickou pipeline.

#### D) **DALL-E Test Section** (řádek ~1621-1720)
```jsx
{false && (
  <div className="bg-white rounded-lg shadow-sm mb-6 p-6">
    ...DALL-E testování...
  </div>
)}
```
**Důvod:** Testování DALL-E obrázků - nepoužívá se (máme archive.org videa).

#### E) **Main Processing Card** (řádek ~1723-2231)
```jsx
{false && (
  <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
    ...stará kombinace audio souborů...
  </div>
)}
```
**Důvod:** Stará sekce pro kombinování audio (upload + intro/outro) - nahrazeno pipeline.

### 2. Zakomentované importy:

```javascript
// import FileUploader from './components/FileUploader'; // DEPRECATED
// import VoiceGenerator from './components/VoiceGenerator'; // DEPRECATED
// import VoiceGenerationQueue from './components/VoiceGenerationQueue'; // DEPRECATED
// import BackgroundUploader from './components/BackgroundUploader'; // DEPRECATED
// import VideoBackgroundUploader from './components/VideoBackgroundUploader'; // DEPRECATED
// import VideoGenerationSimple from './components/VideoGenerationSimple'; // DEPRECATED
```

### 3. Zakomentované state proměnné:

```javascript
// DEPRECATED states (pro skryté komponenty) - zakomentováno
// const [audioFiles, setAudioFiles] = useState([]);
// const [introFile, setIntroFile] = useState(null);
// const [outroFile, setOutroFile] = useState(null);
// const [generatedVoiceFiles, setGeneratedVoiceFiles] = useState([]);
// const [selectedBackground, setSelectedBackground] = useState(null);
// const [dallePrompt, setDallePrompt] = useState('');
// const [isGeneratingImage, setIsGeneratingImage] = useState(false);
// const voiceQueueRef = React.useRef(null);
```

---

## Výsledek: Čistý UI s jedinou aktivní komponentou

### Viditelné v UI:

```
╔═══════════════════════════════════════════════════════╗
║  Petr's genius video machine                          ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║  📝 VideoProductionPipeline                          ║
║  ├─ 1. Generování textu                              ║
║  │   ├─ Téma dokumentu [input]                       ║
║  │   ├─ Jazyk / Target minutes                       ║
║  │   ├─ [Vygenerovat scénář] button                  ║
║  │   └─ Progress: Research → FDA                     ║
║  │                                                    ║
║  ├─ 2. Voice-over Generation                         ║
║  │   ├─ [Vygenerovat Voice-over] button              ║
║  │   └─ Audio soubory (collapsible ▼)                ║
║  │                                                    ║
║  └─ 3. Video Compilation ⭐ NOVÉ!                     ║
║      ├─ [Vygenerovat Video] button                   ║
║      ├─ Progress bar (AAR → CB)                      ║
║      └─ Video player + download                      ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
```

### Co je skryto (ale KÓD ZŮSTÁVÁ pro future use):

❌ VoiceGenerationQueue (ElevenLabs)
❌ Video Generation Studio (DALL-E)
❌ Voice Generator Card
❌ DALL-E Test Section
❌ Main Processing Card (stará kombinace audio)

---

## Technická dokumentace:

### Současná pipeline flow:

```
USER INPUT (téma)
   ↓
1. Research → Writing → Validation → Packaging → TTS Formatting → FDA
   ↓
   [tts_ready_package.json]
   ↓
2. Google Cloud TTS (Voice-over Generation)
   ↓
   [MP3 bloky]
   ↓
3. Archive Asset Resolver (AAR)
   ↓
   [archive_manifest.json]
   ↓
4. Compilation Builder (CB)
   ↓
   [episode_*.mp4] ✅
```

### Backend endpoints používané UI:

```python
POST /api/pipeline/generate_async  # Generování scénáře + FDA
GET  /api/pipeline/status/<id>     # Polling progress
POST /api/tts/generate              # Google Cloud TTS
POST /api/video/compile             # AAR + CB pipeline
GET  /api/projects/<id>             # Load project state
```

### Výhody cleanupu:

✅ Žádné zombie orphan komponenty
✅ Jednoduchá UX (3 kroky místo 5+ sekcí)
✅ Kód stále existuje pro future use (lze rychle obnovit)
✅ Žádné warning/errory kvůli nepoužívaným state
✅ Rychlejší load time (méně komponent)

---

**Status:** ✅ HOTOVO
**Datum:** 27. prosince 2025
**Verze:** v2.0-clean

