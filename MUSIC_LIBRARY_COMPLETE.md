# 🎵 Music Library System - Complete

## ✅ Co bylo implementováno

Vytvořili jsme **globální Music Library** systém, který řeší problém s opakovaným hledáním hudby:

### 1. **Global Music Store** (Backend)
- **Lokace:** `backend/global_music_store.py`
- **Funkce:**
  - Centrální úložiště hudby v `uploads/global_music/`
  - Metadata: tags, mood, duration, size, usage statistics
  - Automatický výběr podle kontextu/nálady
  - CRUD operace (upload, update, delete)

### 2. **API Endpointy** (Backend)
- **Lokace:** `backend/app.py`
- **Nové endpointy:**
  ```
  GET  /api/music/library              # Načte všechny tracky
  POST /api/music/library/upload       # Upload nových souborů
  POST /api/music/library/update       # Update metadata (tags, mood, active)
  POST /api/music/library/delete       # Smazat track
  POST /api/music/library/select-auto  # Automatický výběr
  GET  /api/music/library/download/<filename>  # Download souboru
  POST /api/projects/<episode_id>/music/select-global  # Uložit výběr do projektu
  ```

### 3. **Music Library Modal** (Frontend)
- **Lokace:** `frontend/src/components/MusicLibraryModal.js`
- **Features:**
  - ✅ Upload MP3/WAV s preview
  - ✅ Tag management (ambient, cinematic, piano, etc.)
  - ✅ Mood classification (dark, uplifting, peaceful, dramatic, neutral)
  - ✅ Active/inactive toggle
  - ✅ Audio preview přehrávač
  - ✅ Filtrování podle mood/tags/search
  - ✅ Delete tracks
  - ✅ Usage statistics

### 4. **Automatický výběr hudby**
- **Logika:** Systém analyzuje:
  - Téma scénáře (z `scriptState.topic`)
  - Náladu scén (emotions z footage director)
  - Délku voiceoveru
- **Výběr:** Automaticky vybere nejlepší match podle scoring algoritmu

### 5. **Integration do VideoProductionPipeline**
- **Lokace:** `frontend/src/components/VideoProductionPipeline.js`
- **UI Changes:**
  - Nový Background Music section s integrací Music Library
  - Auto-select button 🤖
  - Preview vybrané hudby s audio přehrávačem
  - Persistent storage (uloženo do `script_state.json`)

### 6. **Compilation Builder Update**
- **Lokace:** `backend/compilation_builder.py`
- **Priority:**
  1. User-selected global music (z UI)
  2. Per-episode music (legacy compatibility)
  3. Auto-select from global library

---

## 🎯 Jak to funguje

### Pro uživatele:

1. **Prvotní setup:**
   - Otevřete **Music Library** (tlačítko "📚 Otevřít Music Library")
   - Nahrajte svoje oblíbené podkresové hudby (MP3/WAV)
   - Označte je tags (ambient, cinematic, dramatic, etc.)
   - Nastavte mood (dark, uplifting, peaceful, neutral)

2. **Při tvorbě projektu:**
   - Po vygenerování TTS systém **automaticky vybere** hudbu
   - Výběr je založený na tématu a náladě scénáře
   - Můžete si vybrat jinou v Music Library nebo použít auto-vybranou

3. **Video compilation:**
   - Systém použije vybranou hudbu (nebo auto-vybranou)
   - Hudba je automaticky mixovaná na -30dB s fade-in/out

### Technické detaily:

**Scoring Algorithm (auto-select):**
```python
score = 0
# 1. Mood match (highest priority)
if preferred_mood == track.mood:
    score += 10.0

# 2. Tag match
matching_tags = set(preferred_tags) & set(track.tags)
score += len(matching_tags) * 3.0

# 3. Penalize overused tracks (encourage variety)
score -= track.usage_count * 0.5

# Return best scoring track
```

**Mood Detection Heuristics:**
```javascript
// Frontend (auto-select on TTS done)
if (topic.match(/dark|mystery|crime|war/i)) → mood: "dark", tags: ["cinematic", "dramatic"]
if (topic.match(/hope|future|innovation/i)) → mood: "uplifting", tags: ["ambient", "electronic"]
if (topic.match(/battle|conflict|crisis/i)) → mood: "dramatic", tags: ["orchestral", "cinematic"]
else → mood: "peaceful", tags: ["ambient", "minimal"]

// Backend (compilation builder - scene emotions)
if (predominant_emotion in ["tension", "tragedy", "mystery"]) → mood: "dark"
if (predominant_emotion in ["hope", "victory"]) → mood: "uplifting"
else → mood: "peaceful"
```

---

## 📂 File Structure

```
podcasts/
├── backend/
│   ├── global_music_store.py       ← NEW: Global music library logic
│   ├── app.py                       ← UPDATED: 7 new API endpoints
│   ├── compilation_builder.py      ← UPDATED: Auto-select integration
│   └── music_store.py              ← KEPT: Legacy per-episode music
├── frontend/
│   └── src/
│       └── components/
│           ├── MusicLibraryModal.js        ← NEW: Music library UI
│           └── VideoProductionPipeline.js  ← UPDATED: Integration
└── uploads/
    └── global_music/               ← NEW: Centrální úložiště
        ├── music_001_ambient.mp3
        ├── music_002_dark_piano.mp3
        └── music_manifest.json
```

---

## 🎨 UI Screenshots (konceptuální)

### Music Library Modal:
```
┌────────────────────────────────────────────────────────┐
│ 🎵 Music Library                         ✕             │
│ Globální knihovna podkresové hudby • 12 tracks        │
├────────────────────────────────────────────────────────┤
│ ❌ Chyba...                                            │ (jen když error)
├────────────────────────────────────────────────────────┤
│ 📤 Upload Section:                                     │
│   [Choose Files: MP3/WAV]  [📎 Browse...]             │
│   Tags: [ambient] [cinematic] [piano] [electronic]    │
│   Mood: [😐 Neutral] [🌑 Dark] [✨ Uplifting]         │
├────────────────────────────────────────────────────────┤
│ 🔍 Filters:                                            │
│   Mood: [All ▼]  Tag: [All ▼]  Search: [_______]     │
├────────────────────────────────────────────────────────┤
│ Tracks (12):                                           │
│ ┌──────────────────────────────────────────────────┐  │
│ │ ambient_pad.mp3 (3:24 • 5.2MB)                   │  │
│ │ [🌊 Peaceful] [ambient] [minimal] [Použito 3×]   │  │
│ │ ▶ Audio player...                                 │  │
│ │ [✓ Aktivní] [Vybrat] [🗑️ Smazat]                 │  │
│ └──────────────────────────────────────────────────┘  │
│ ... (další tracky)                                     │
└────────────────────────────────────────────────────────┘
```

### Background Music Section (VideoProductionPipeline):
```
┌────────────────────────────────────────────────────────┐
│ 🎵 Background Music         [📚 Otevřít Music Library] │
│ Systém automaticky vybírá hudbu podle tématu...       │
├────────────────────────────────────────────────────────┤
│ ✅ Vybraná hudba:                                      │
│   ambient_pad.mp3                                      │
│   [🌊 peaceful] [ambient] [minimal] (3:24 • 5.2MB)    │
│   ▶ Audio preview...                          [🗑️]    │
│                                                        │
│ 💡 Tip: Systém automaticky vybral tuto hudbu podle    │
│    tématu "Nikola Tesla". Můžete si vybrat jinou.     │
└────────────────────────────────────────────────────────┘
```

---

## 🔧 Testing & Debugging

### Testovací postup:

1. **Upload hudby do knihovny:**
   ```bash
   # curl test
   curl -X POST http://localhost:50000/api/music/library/upload \
     -F "music_files=@ambient_pad.mp3" \
     -F "tags=[\"ambient\",\"minimal\"]" \
     -F "mood=peaceful"
   ```

2. **Auto-select test:**
   ```bash
   curl -X POST http://localhost:50000/api/music/library/select-auto \
     -H "Content-Type: application/json" \
     -d '{
       "preferred_mood": "dark",
       "preferred_tags": ["cinematic", "dramatic"],
       "min_duration_sec": 120
     }'
   ```

3. **UI workflow:**
   - Otevřít Music Library
   - Upload několik různých hudeb s různými moods
   - Vygenerovat scénář (např. "Tajemství Nikoly Tesly")
   - Zkontrolovat, jestli systém vybral "dark" hudbu

### Debug logging:
```python
# Backend (compilation_builder.py)
print(f"🎵 CB: Using user-selected global music: {filename}")
print(f"🎵 CB: Using per-episode music: {filename}")
print(f"🎵 CB: Auto-selected global music: {filename} (mood={mood})")
print(f"🎵 CB: Background music mixed in: {filename}")
```

---

## 🚀 Benefits

### Před (starý systém):
❌ Musíte **pokaždé** hledat soubory v počítači  
❌ Žádné tagy/metadata  
❌ Žádný automatický výběr  
❌ Per-project duplicity  
❌ Žádné preview  

### Po (nový Music Library):
✅ **Jednou nahrajte**, používejte vždy  
✅ Tagy + mood klasifikace  
✅ **Automatický výběr** podle kontextu  
✅ Centrální knihovna (sdílená všemi projekty)  
✅ Audio preview + statistics  
✅ Filtrování a vyhledávání  
✅ Usage tracking (které hudby se nejvíc používají)  

---

## 🎓 Advanced Features (pro budoucnost)

Možná rozšíření:
- [ ] BPM detection & filtering
- [ ] Waveform visualization
- [ ] Batch tag editing
- [ ] Export/import library
- [ ] Cloud sync (Dropbox/Google Drive)
- [ ] AI-powered mood detection (místo heuristik)
- [ ] Music trimming/editing in-app
- [ ] Royalty-free music marketplace integration

---

## 📊 Data Model

### Global Music Track:
```json
{
  "filename": "music_001_ambient_pad.mp3",
  "original_name": "ambient_pad.mp3",
  "duration_sec": 204.5,
  "size_mb": 5.2,
  "active": true,
  "tags": ["ambient", "minimal"],
  "mood": "peaceful",
  "uploaded_at": "2025-12-27T20:30:00Z",
  "usage_count": 3
}
```

### Script State (selected music):
```json
{
  "episode_id": "ep_abc123",
  "selected_global_music": {
    "filename": "music_001_ambient_pad.mp3",
    "mood": "peaceful",
    "tags": ["ambient", "minimal"]
  }
}
```

---

## ✅ Všechno hotovo!

Systém je **production-ready** a řeší všechny problémy, které jste měli:

1. ✅ **Žádné hledání souborů** - jednou nahrajete, používáte vždy
2. ✅ **Automatický výběr** - systém sám vybírá podle kontextu
3. ✅ **Centrální správa** - Music Library modal pro všechno
4. ✅ **Metadata & tags** - organizace a filtrování
5. ✅ **Persistent** - výběr se ukládá do projektu

**Nyní můžete:**
- Nahrát svoje oblíbené podkresové hudby do knihovny
- Nechat systém automaticky vybírat podle nálady
- Nebo si manuálně vybrat z knihovny
- Všechno bez nutnosti hledat soubory na disku! 🎉



