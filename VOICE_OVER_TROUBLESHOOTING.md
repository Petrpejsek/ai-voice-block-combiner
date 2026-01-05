# 🔍 Voice-over sekce zmizela - Troubleshooting

## ❓ Co se stalo?

Voice-over sekce je stále v kódu a funguje! Ale zobrazuje se **jen za určitých podmínek**.

## ✅ Kdy se Voice-over sekce zobrazí:

Voice-over Generation sekce se zobrazí **JEN když**:

1. ✅ Existuje `scriptState` (máte načtený/vygenerovaný projekt)
2. ✅ `script_status === 'DONE'` (všechny kroky pipeline jsou hotové)
3. ✅ `tts_ready_package` existuje (TTS Formatting krok byl dokončen)

## 🔧 Možné příčiny, proč to nevidíte:

### 1. **Načetli jste starý projekt (před TTS formattingem)**
   - **Řešení:** Vygenerujte nový projekt (pipeline má nyní TTS Formatting krok)

### 2. **Script není dokončený (status ≠ DONE)**
   - **Řešení:** Počkejte, až všechny kroky budou ✅

### 3. **TTS Formatting krok selhal**
   - **Řešení:** Zkontrolujte errory, případně retry

### 4. **Browser cache (stará verze)**
   - **Řešení:** Hard refresh (Ctrl+Shift+R / Cmd+Shift+R)

## 🧪 Jak ověřit, co je problém:

### Test 1: Otevřete Developer Console (F12)

V console spusťte:
```javascript
// Zkontrolujte stav
console.log('Script State:', window.scriptState);
console.log('Script Status:', window.scriptState?.script_status);
console.log('TTS Package exists:', !!window.scriptState?.tts_ready_package);
```

### Test 2: Zkontrolujte sekce na stránce

Scrollujte dolů a hledejte:
```
✅ MĚLO BY být vidět:
├─ 📝 Generování textu (vždy viditelné)
├─ 🎙️ Voice-over Generation (JEN když status=DONE && tts_package)
├─ 🎵 Background Music (JEN když status=DONE)
└─ 🎬 Video Compilation (JEN když status=DONE && shot_plan && tts=done)
```

## 🔄 Quick Fix - Vygenerujte nový projekt:

1. **Otevřete:** http://localhost:4000
2. **Zadejte téma:** (např. "Test TTS")
3. **Klikněte:** "Vygenerovat scénář"
4. **Počkejte na všechny kroky:**
   - Research... ✅
   - Writing... ✅
   - Validating... ✅
   - Packaging... ✅
   - **TTS Formatting...** ✅ ← Důležité!
   - Footage Director... ✅

5. **Po dokončení se zobrazí:**
   ```
   ┌──────────────────────────────────────┐
   │ 🎙️ Voice-over Generation            │
   │ Ready to generate                    │
   │ [🎙️ Vygenerovat Voice-over]         │
   └──────────────────────────────────────┘
   ```

## 📊 Kontrola existujícího projektu:

Pokud používáte existující projekt, zkontrolujte `script_state.json`:

```bash
# Najděte váš projekt
ls /Users/petrliesner/podcasts/projects/

# Zkontrolujte script_state
cat /Users/petrliesner/podcasts/projects/ep_XXX/script_state.json | jq '.script_status, .tts_ready_package' 

# Mělo by vrátit:
# "DONE"
# { ... tts_ready_package data ... }
```

Pokud `tts_ready_package` chybí nebo je `null`, projekt je **před TTS Formatting upgradem** a potřebujete vygenerovat nový.

## 🆕 Nové projekty vs. Staré projekty:

### Staré projekty (před 27.12.2025):
- ❌ **NEMAJÍ** TTS Formatting krok
- ❌ **NEMAJÍ** `tts_ready_package`
- ❌ Voice-over sekce se **NEZOBRAZÍ**

### Nové projekty (po 27.12.2025):
- ✅ **MAJÍ** TTS Formatting krok (krok 5)
- ✅ **MAJÍ** `tts_ready_package`
- ✅ Voice-over sekce se **ZOBRAZÍ**

## ✅ Verifikace že kód funguje:

Voice-over sekce je v kódu na řádcích **1620-1800** v `VideoProductionPipeline.js`:

```javascript
// Řádek 1620-1621
{/* TTS Voice-over Generation Section */}
{scriptState && scriptState.script_status === 'DONE' && scriptState.tts_ready_package && (
  <div className="mt-6 p-4 border border-purple-200 rounded-lg bg-purple-50">
    <h3>🎙️ Voice-over Generation</h3>
    <button onClick={generateVoiceOver}>
      🎙️ Vygenerovat Voice-over
    </button>
  </div>
)}
```

✅ **Kód je v pořádku!** Jen čekáme na správné podmínky.

## 🎯 Rychlé řešení:

**Vygenerujte nový testovací projekt:**

1. http://localhost:4000
2. Téma: "Quick TTS Test"
3. Vygenerovat scénář
4. Počkejte 2-5 minut
5. Voice-over sekce se **automaticky zobrazí**! ✅

---

**Frontend běží:** http://localhost:4000 ✅  
**Backend běží:** http://localhost:50000 ✅  
**Kód je OK:** Voice-over sekce existuje! ✅

**Tip:** Pokud stále nevidíte, použijte Developer Console (F12) a zkontrolujte `scriptState` object.



