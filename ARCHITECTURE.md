# AI YouTube Documentary Farm - Architektonický dokument

## 🎯 Cíle systému

Produkce kvalitních YouTube dokumentů ve velkém měřítku s:
- **Automatizovanou tvorbou scénářů** pomocí více specializovaných AI asistentů
- **Profesionální produkcí** s ElevenLabs TTS, video efekty a automatizovaným střihem
- **Modulární architekturou** oddělující scénář, produkci, vizuál a distribuci
- **Škálovatelností** na desítky kanálů současně
- **Kvalitou** srovnatelnou s profesionálními dokumenty

---

## 🏗️ Architektura vrstev

```
┌─────────────────────────────────────────────────────────────┐
│                    DISTRIBUTION LAYER                        │
│  (YouTube API, Scheduling, Multi-Channel Management)        │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    VISUAL LAYER                              │
│  (DALL-E, Stock Footage, Ken Burns, Video Composition)      │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION LAYER                          │
│  (ElevenLabs TTS, Audio Mixing, Video Assembly, FFmpeg)      │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    SCRIPT LAYER                              │
│  (Multi-AI Assistants, Research, Story Structure)           │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    DATA & ORCHESTRATION LAYER                 │
│  (Project DB, Queue System, Workflow Engine, State Mgmt)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Vrstva 1: Script Layer (Scénář)

### **Zodpovědnost**
- Výzkum tématu a faktů
- Tvorba strukturovaného scénáře
- Generování dialogů a narace
- Optimalizace pro YouTube (SEO, engagement)

### **Komponenty**

#### **1.1 Multi-AI Assistant System**
```
┌─────────────────────────────────────────┐
│     Assistant Orchestrator              │
│  (Koordinuje práci všech asistentů)     │
└─────────────────────────────────────────┘
           ↓
    ┌──────┴──────┬──────────┬──────────┐
    ↓             ↓          ↓          ↓
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Research │ │Narrative│ │Dialogue │ │SEO/Eng. │
│Assistant│ │Assistant│ │Assistant│ │Assistant│
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

**Specializovaní asistenti:**
- **Research Assistant** - faktografický výzkum, ověřování informací
- **Narrative Assistant** - struktura příběhu, story arc, pacing
- **Dialogue Assistant** - přirozené dialogy, charakterizace postav
- **SEO/Engagement Assistant** - optimalizace pro YouTube algoritmus
- **Fact-Checker Assistant** - validace faktů, kontrola konzistence

#### **1.2 Script Structure**
```json
{
  "project_id": "doc_001",
  "topic": "Historie elektrických aut",
  "target_channel": "tech_history",
  "script": {
    "intro": {
      "hook": "V roce 1899...",
      "duration_estimate": 30,
      "voice_blocks": [
        {"id": "narrator_01", "text": "...", "voice_id": "narrator_voice"}
      ]
    },
    "chapters": [
      {
        "title": "Počátky elektromobility",
        "duration_estimate": 180,
        "voice_blocks": [...],
        "visual_cues": ["dalle_prompt_1", "stock_footage_1890s"],
        "music_cue": "ambient_historical"
      }
    ],
    "outro": {...}
  },
  "metadata": {
    "target_duration": 1200,
    "keywords": ["elektromobil", "historie", "Tesla"],
    "seo_title": "...",
    "seo_description": "..."
  }
}
```

### **Datové toky**
```
User Input (Topic/Channel) 
  → Assistant Orchestrator
  → Parallel AI Assistant Calls
  → Script Assembly
  → Validation & Review
  → Script JSON → Production Layer
```

---

## 🎬 Vrstva 2: Production Layer (Produkce)

### **Zodpovědnost**
- Generování hlasů přes ElevenLabs TTS
- Kombinování audio tracků
- Sestavování video sekvencí
- Synchronizace audio/video
- Export finálního videa

### **Komponenty**

#### **2.1 Voice Generation Engine**
```
Script JSON (voice_blocks)
  → Voice Block Parser
  → ElevenLabs API Batch Queue
  → Voice File Generation (MP3/WAV)
  → Audio Quality Check
  → Voice Files Storage
```

**Funkce:**
- Batch processing pro stovky voice blocks
- Retry mechanismus pro failed requests
- Voice consistency mapping (stejný hlas pro stejnou postavu)
- Audio normalization a quality checks

#### **2.2 Audio Production Pipeline**
```
Voice Files + Music + SFX
  → Audio Mixer
  → Volume Normalization
  → Pause Insertion
  → Audio Timeline Assembly
  → Master Audio Track
```

#### **2.3 Video Assembly Engine**
```
Master Audio Track + Visual Assets
  → Timeline Builder
  → Clip Sequencing
  → Transition Effects
  → Audio-Video Sync
  → Final Video Render (FFmpeg/MoviePy)
```

### **Datové toky**
```
Script JSON
  → Voice Generation (ElevenLabs)
  → Audio Assembly
  → Visual Layer Integration
  → Video Rendering
  → Final Video File → Distribution Layer
```

---

## 🎨 Vrstva 3: Visual Layer (Vizuál)

### **Zodpovědnost**
- Generování obrázků (DALL-E)
- Správa stock footage
- Video efekty (Ken Burns, transitions)
- Kompozice vizuálů s audio
- Branding a channel-specific styling

### **Komponenty**

#### **3.1 Image Generation System**
```
Visual Cues from Script
  → DALL-E Prompt Generator
  → DALL-E API Calls
  → Image Download & Storage
  → Image Quality Validation
  → Image Library
```

#### **3.2 Stock Footage Manager**
```
Visual Cues
  → Stock Footage Search (Pexels/Unsplash API)
  → Footage Download
  → Footage Library
  → Smart Matching Algorithm
```

#### **3.3 Video Effects Engine**
```
Images/Footage + Duration
  → Ken Burns Effect Generator
  → Transition Effects
  → Color Grading
  → Channel-Specific Styling
  → Processed Visual Assets
```

#### **3.4 Visual Composition**
```
Processed Visuals + Audio Timeline
  → Scene Matching Algorithm
  → Visual-Audio Synchronization
  → Composition Rules Engine
  → Final Visual Timeline
```

### **Datové toky**
```
Script Visual Cues
  → Parallel: DALL-E Generation + Stock Footage Search
  → Visual Asset Library
  → Effect Processing
  → Composition with Audio
  → Visual Timeline → Production Layer
```

---

## 📺 Vrstva 4: Distribution Layer (Distribuce)

### **Zodpovědnost**
- Správa více YouTube kanálů
- Upload videa na YouTube
- Metadata management (titles, descriptions, tags)
- Scheduling a publikování
- Analytics a monitoring

### **Komponenty**

#### **4.1 Multi-Channel Manager**
```
Channel Configuration
  ┌─────────────┬─────────────┬─────────────┐
  │ Channel 1   │ Channel 2   │ Channel N   │
  │ (tech)      │ (history)   │ (science)    │
  └─────────────┴─────────────┴─────────────┘
         ↓              ↓              ↓
    Channel-Specific Settings
    (Branding, Style, Audience)
```

#### **4.2 YouTube API Integration**
```
Final Video + Metadata
  → YouTube API Client
  → Video Upload
  → Metadata Setting (title, description, tags, thumbnail)
  → Publishing/Scheduling
  → Upload Status Tracking
```

#### **4.3 Content Scheduling System**
```
Video Queue
  → Schedule Optimizer (best upload times)
  → Publishing Calendar
  → Automated Publishing
  → Post-Publish Analytics
```

### **Datové toky**
```
Final Video + Script Metadata
  → Channel Selection
  → YouTube API Upload
  → Metadata Application
  → Publishing/Scheduling
  → Analytics Collection
```

---

## 🗄️ Vrstva 5: Data & Orchestration Layer

### **Zodpovědnost**
- Správa projektů a jejich stavů
- Workflow orchestrace
- Queue management
- State persistence
- Error handling a retry logic

### **Komponenty**

#### **5.1 Project Database**
```
Project Schema:
{
  "project_id": "uuid",
  "channel_id": "tech_history",
  "status": "script_generation|voice_generation|production|completed",
  "script": {...},
  "assets": {
    "voices": [...],
    "images": [...],
    "video": "path/to/video.mp4"
  },
  "metadata": {...},
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

#### **5.2 Workflow Orchestrator**
```
Project Creation
  → State Machine:
      [NEW] 
        → [SCRIPT_GENERATION] 
          → [VOICE_GENERATION] 
            → [VISUAL_GENERATION] 
              → [PRODUCTION] 
                → [DISTRIBUTION] 
                  → [COMPLETED]
```

#### **5.3 Queue System**
```
Task Queues:
  - script_generation_queue
  - voice_generation_queue
  - visual_generation_queue
  - video_rendering_queue
  - distribution_queue
```

#### **5.4 State Management**
```
Project State Tracking:
  - Current stage
  - Progress percentage
  - Error logs
  - Retry attempts
  - Resource usage
```

### **Datové toky**
```
User Request
  → Project Creation (DB)
  → Workflow Orchestrator
  → Queue Tasks
  → State Updates
  → Next Stage Trigger
  → Completion → Distribution
```

---

## 🔄 Kompletní datový tok projektu

```
1. USER INPUT
   ↓
   [Topic, Channel, Preferences]
   
2. SCRIPT LAYER
   ↓
   [Multi-AI Assistants → Script JSON]
   
3. DATA LAYER
   ↓
   [Project Created, State: SCRIPT_COMPLETE]
   
4. PRODUCTION LAYER (Voice)
   ↓
   [ElevenLabs TTS → Voice Files]
   
5. VISUAL LAYER
   ↓
   [DALL-E + Stock Footage → Visual Assets]
   
6. PRODUCTION LAYER (Assembly)
   ↓
   [Audio + Visuals → Final Video]
   
7. DATA LAYER
   ↓
   [State: PRODUCTION_COMPLETE]
   
8. DISTRIBUTION LAYER
   ↓
   [YouTube Upload → Published]
   
9. DATA LAYER
   ↓
   [State: COMPLETED, Analytics Stored]
```

---

## 🚀 Škálovatelnost

### **Horizontální škálování**

#### **Multi-Channel Support**
- Každý kanál má vlastní konfiguraci (branding, style, audience)
- Paralelní produkce pro více kanálů současně
- Channel-specific AI assistants (různé styly scénářů)

#### **Queue-Based Architecture**
- Asynchronní zpracování všech fází
- Worker pools pro každou vrstvu
- Auto-scaling workers podle zátěže

#### **Resource Management**
```
Worker Pools:
  - Script Generation Workers (AI API calls)
  - Voice Generation Workers (ElevenLabs)
  - Visual Generation Workers (DALL-E)
  - Video Rendering Workers (FFmpeg)
  - Distribution Workers (YouTube API)
```

### **Vertikální optimalizace**

#### **Caching & Reuse**
- Reusable voice files (stejné postavy)
- Image library cache (DALL-E results)
- Stock footage library
- Template-based video compositions

#### **Batch Processing**
- Batch voice generation (100+ blocks najednou)
- Parallel image generation
- Optimized video rendering pipeline

---

## 🔌 API & Integrace

### **Externí API**

#### **ElevenLabs TTS**
- Voice generation
- Voice cloning (pro konzistentní postavy)
- Batch processing

#### **OpenAI**
- GPT-4o (AI assistants pro scénář)
- DALL-E 3 (obrázky)
- Whisper (případně pro transkripce)

#### **YouTube Data API v3**
- Video upload
- Metadata management
- Analytics

#### **Stock Footage APIs**
- Pexels Video API
- Unsplash Video API
- Pixabay Video API

### **Interní API**

```
Backend Services:
  - Script Service (port 50001)
  - Production Service (port 50002)
  - Visual Service (port 50003)
  - Distribution Service (port 50004)
  - Orchestration Service (port 50000)
```

---

## 📊 Monitoring & Analytics

### **Production Metrics**
- Projekty za den/týden
- Průměrná doba produkce
- Success rate jednotlivých fází
- Error rates a retry statistics

### **Quality Metrics**
- Video quality scores
- Engagement predictions
- SEO score
- Fact-check accuracy

### **Resource Metrics**
- API usage (ElevenLabs, OpenAI)
- Storage usage
- Compute time
- Cost tracking

---

## 🛡️ Error Handling & Resilience

### **Retry Strategies**
- Exponential backoff pro API calls
- Max retry limits
- Fallback mechanisms (alternativní API, cached resources)

### **State Recovery**
- Checkpoint system (uložení stavu po každé fázi)
- Resume failed projects
- Partial completion handling

### **Quality Gates**
- Validation po každé fázi
- Manual review triggers (pro kritické chyby)
- Auto-fix mechanisms (kde je to možné)

---

## 🎯 Klíčové principy architektury

1. **Separation of Concerns** - každá vrstva má jasně definovanou zodpovědnost
2. **Asynchronous Processing** - všechny dlouhé operace jsou asynchronní
3. **Queue-Based** - škálovatelnost přes queue systém
4. **State-Driven** - workflow řízený stavovým strojem
5. **API-First** - všechny komponenty komunikují přes API
6. **Multi-Tenant** - podpora pro desítky kanálů současně
7. **Quality-Focused** - validace a quality checks na každé úrovni

---

## 📈 Roadmap implementace

### **Fáze 1: Core Script Layer**
- Multi-AI assistant system
- Script structure a JSON schema
- Basic orchestration

### **Fáze 2: Production Layer**
- ElevenLabs integration
- Audio assembly
- Basic video rendering

### **Fáze 3: Visual Layer**
- DALL-E integration
- Ken Burns effects
- Visual composition

### **Fáze 4: Distribution Layer**
- YouTube API integration
- Multi-channel support
- Scheduling system

### **Fáze 5: Scale & Optimize**
- Queue system
- Worker pools
- Caching & optimization
- Analytics & monitoring

---

**Verze:** 1.0  
**Datum:** 2025-01-15  
**Status:** Cílová architektura




