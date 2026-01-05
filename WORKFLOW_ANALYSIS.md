# 🎬 Video Production Workflow - Current State

**Date:** December 27, 2025

---

## 📊 Současný stav

### ✅ Co funguje

1. **Script Generation Pipeline:**
   ```
   Topic → Research → Writing → Validation → Packaging → TTS Formatting → ✅ HOTOVO
   ```
   - Výstup: `tts_ready_package` s `narration_blocks[]`
   - Preview: Zobrazuje TTS-ready segments
   - Tlačítko: "📄 Show Script" / "🎤 Show TTS-ready"

2. **Google TTS Backend:**
   ```
   POST /api/tts/generate → Narrator_0001.mp3, 0002.mp3, ...
   ```
   - ✅ Token refresh funguje
   - ✅ en-US-Neural2-D hlas
   - ✅ MP3 generation OK

3. **Audio Playback (existující komponenta):**
   ```jsx
   <audio controls>
     <source src="/api/download/Narrator_0001.mp3" />
   </audio>
   ```
   - Komponenta: `VoiceGenerationQueue` (má přehrávače)
   - ✅ Download buttons
   - ✅ Preview textu

---

## ❌ Co chybí

### Missing Link: TTS Generation Button

**Problem:**
- `VideoProductionPipeline` končí na **TTS Formatting**
- **Neklikne se** automaticky na TTS generování
- Uživatel **nevidí tlačítko** "Vygenerovat Voice-over"

**Current End State:**
```
TTS Formatting… ✅ DONE
└─> Preview: Shows tts_ready_package
    └─> [????] <-- KDE JE TLAČÍTKO?
```

---

## 🎯 Navržené řešení

### Přidat sekci "Voice-over Generation"

Po dokončení TTS formátování zobrazit:

```
┌─────────────────────────────────────────────┐
│ 🎙️ Voice-over Generation                    │
├─────────────────────────────────────────────┤
│ Status: Ready                                │
│ Blocks to generate: 45                       │
│ Estimated time: ~2-3 minutes                 │
│                                              │
│ [ 🎙️ Vygenerovat Voice-over ]               │
└─────────────────────────────────────────────┘
```

### Po kliknutí:

```
┌─────────────────────────────────────────────┐
│ 🎙️ Generuji audio...                        │
├─────────────────────────────────────────────┤
│ Progress: [████████░░░░░░░░] 45%            │
│ Block 20/45: "In the early 20th century..." │
│                                              │
│ ⏱️ Zbývá ~1 minuta                           │
└─────────────────────────────────────────────┘
```

### Po dokončení:

```
┌─────────────────────────────────────────────┐
│ ✅ Voice-over vygenerován!                   │
├─────────────────────────────────────────────┤
│ Vygenerováno: 45 MP3 souborů                 │
│ Celková délka: ~15 minut                     │
│                                              │
│ 🎵 Audio Preview:                            │
│ ┌───────────────────────────────────────┐   │
│ │ Narrator_0001.mp3                      │   │
│ │ [▶️ =========>----] 0:05 / 0:12       │   │
│ │ 💾 Download                            │   │
│ └───────────────────────────────────────┘   │
│ ┌───────────────────────────────────────┐   │
│ │ Narrator_0002.mp3                      │   │
│ │ [⏸️ ------] 0:00 / 0:08                │   │
│ │ 💾 Download                            │   │
│ └───────────────────────────────────────┘   │
│ ... (43 more files)                          │
│                                              │
│ [ 📥 Stáhnout všechny MP3 ]                  │
│ [ 🎬 Pokračovat na Video generování ]        │
└─────────────────────────────────────────────┘
```

---

## 🔧 Implementační detaily

### 1. State Management

```javascript
const [ttsState, setTtsState] = useState({
  status: 'idle', // idle | generating | done | error
  progress: 0,
  currentBlock: 0,
  totalBlocks: 0,
  generatedFiles: [],
  error: null
});
```

### 2. TTS Generation Function

```javascript
const generateVoiceOver = async () => {
  if (!scriptState?.tts_ready_package) {
    alert('Nejprve vygenerujte scénář');
    return;
  }

  setTtsState(prev => ({ ...prev, status: 'generating', progress: 0 }));

  try {
    const response = await axios.post('/api/tts/generate', {
      tts_ready_package: scriptState.tts_ready_package
    }, {
      timeout: 1800000 // 30 minut
    });

    if (response.data.success) {
      setTtsState({
        status: 'done',
        progress: 100,
        currentBlock: response.data.total_blocks,
        totalBlocks: response.data.total_blocks,
        generatedFiles: response.data.generated_files || [],
        error: null
      });
    } else {
      throw new Error(response.data.error);
    }
  } catch (error) {
    setTtsState(prev => ({
      ...prev,
      status: 'error',
      error: error.message
    }));
  }
};
```

### 3. Audio Player Component

```jsx
{ttsState.status === 'done' && ttsState.generatedFiles.length > 0 && (
  <div className="mt-4 space-y-3">
    <h4 className="font-medium text-gray-900">🎵 Vygenerované audio soubory</h4>
    {ttsState.generatedFiles.slice(0, 5).map((file, index) => (
      <div key={index} className="p-3 border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">{file}</span>
          <a
            href={`/api/download/${file}`}
            download
            className="text-blue-600 hover:text-blue-700 text-sm"
          >
            💾 Download
          </a>
        </div>
        <audio
          controls
          className="w-full"
          preload="metadata"
        >
          <source src={`/api/download/${file}`} type="audio/mpeg" />
        </audio>
      </div>
    ))}
    {ttsState.generatedFiles.length > 5 && (
      <div className="text-sm text-gray-600 text-center">
        ... a {ttsState.generatedFiles.length - 5} dalších souborů
      </div>
    )}
  </div>
)}
```

---

## 🎯 User Flow (po implementaci)

### Krok 1: Generování scénáře
```
User: Klikne "Vygenerovat scénář"
      ↓
App:  Research → Writing → Validation → Packaging → TTS Formatting
      ↓
      ✅ TTS-ready package hotovo
```

### Krok 2: Preview & Voice-over button
```
User: Vidí preview TTS segments
      Vidí tlačítko "🎙️ Vygenerovat Voice-over"
      ↓
User: Klikne "Vygenerovat Voice-over"
```

### Krok 3: TTS generování
```
App:  Volá POST /api/tts/generate
      ↓
      Progress: [████████████] 100%
      ↓
      ✅ Vygenerováno 45 MP3 souborů
```

### Krok 4: Audio preview
```
User: Vidí seznam MP3 souborů
      Může přehrát každý soubor
      Může stáhnout jednotlivě nebo všechny
      ↓
User: Spokojený s audio?
      ├─> ANO: Klikne "🎬 Pokračovat na Video"
      └─> NE:  Regeneruje script nebo upraví parametry
```

### Krok 5: Video generování
```
User: Klikne "🎬 Pokračovat na Video"
      ↓
App:  Přepne na Video generation tab
      Automaticky načte Narrator_*.mp3 soubory
      ↓
User: Vygeneruje finální video s audio
```

---

## ✅ Benefits

1. **Clear workflow:** User vidí jasný postup
2. **Preview možnost:** Před videem si poslechne audio
3. **Kontrolní bod:** Může zastavit před drahým video renderingem
4. **Debugging:** Pokud audio je špatné, nemusí generovat video
5. **Iterace:** Může rychle regenerovat jen audio bez nového scriptu

---

## 🚀 Next Actions

**Option A: Automatické pokračování**
- Po TTS formátování automaticky spustit TTS generování
- Žádný stop, jede to až do audio MP3

**Option B: Manuální krok (DOPORUČENO)**
- Zobrazit tlačítko "🎙️ Vygenerovat Voice-over"
- User má kontrolu, kdy spustit TTS
- Může si prohlédnout TTS segments před generováním

**Option C: Optional preview**
- Po TTS formátování nabídnout:
  - "🎙️ Vygenerovat Voice-over" (běžný flow)
  - "👁️ Preview TTS segments" (pro power users)

---

**Recommendation:** **Option B** (Manuální krok s tlačítkem)

**Proč:**
- User má kontrolu
- Může si přečíst TTS-ready text před generováním
- Debugging friendly (vidí, co půjde do TTS)
- Jasný workflow s checkpointy

---

**Status:** Čeká na implementaci  
**Priority:** HIGH (missing critical link v workflow)  
**Effort:** Medium (~1-2 hodiny)



