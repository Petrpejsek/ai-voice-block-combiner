# ✅ UI Změny Dokončeny!

## Co bylo implementováno:

### 1. Frontend (VideoProductionPipeline.js)

#### Přidány state proměnné:
- `showAudioFiles` - pro collapsible audio sekci (defaultně zavřená)
- `videoCompilationState` - tracking video generování (idle/running/done/error)

#### Přidána funkce `generateVideoCompilation()`:
- Volá `/api/video/compile` backend endpoint
- Polluje `/api/script/state/<episode_id>` každé 3 sekundy
- Trackuje progress: AAR (40%) → CB (70%) → Done (100%)
- Timeout: 20 minut

#### UI změny:
✅ Audio soubory jsou **collapsible** (klikací, defaultně zavřené)
✅ Nová sekce **"🎬 Video Compilation"** se zobrazí po vygenerování audio
✅ Tlačítko **"🎬 Vygenerovat Video"**
✅ Progress bar s real-time updates
✅ Video player po dokončení

### 2. Backend (app.py)

#### Nový endpoint: `/api/video/compile`
```python
POST /api/video/compile
Body: { "episode_id": "ep_xxx" }
```

**Co dělá:**
1. Ověří, že shot_plan existuje
2. Spustí AAR + CB v background threadu
3. Vrátí okamžitou odpověď
4. Frontend polluje progress přes `/api/script/state/<episode_id>`

## Jak to použít:

### 1. Vygeneruj scénář a audio
- Zadej téma → "Vygenerovat scénář"
- Počkej na dokončení všech kroků (Research → FDA)
- Zmáčkni "🎙️ Vygenerovat Voice-over"

### 2. Vygeneruj video
- Po dokončení audio se objeví sekce **"🎬 Video Compilation"**
- Zmáčkni **"🎬 Vygenerovat Video"**
- Progress bar ukáže:
  - 10%: Starting...
  - 40%: Archive Asset Resolver...
  - 70%: Compilation Builder...
  - 100%: Complete! → Video player

### 3. Stáhni video
- Po dokončení se zobrazí video player
- Klikni na **"📥 Stáhnout video"**

## Časové odhady:

- **Research → FDA:** 1-3 minuty
- **Voice-over generation:** 2-5 minut (7 bloků)
- **Video Compilation:** 5-15 minut
  - AAR: 1-2 minuty (search + manifest)
  - CB: 4-13 minut (download 94MB+ videa + FFmpeg)

## Stavy v UI:

### Voice-over Generation:
✅ DONE → Audio soubory collapsible (zavřené)

### Video Compilation:
- **idle**: Tlačítko "Vygenerovat Video"
- **running**: Progress bar (3s polling)
- **done**: Video player + download
- **error**: Error message + retry button

## Backend Changes:

✅ Backend restartován s novými změnami
✅ Endpoint `/api/video/compile` aktivní
✅ Žádné linter errors

Frontend změny budou aktivní po refreshi prohlížeče.

