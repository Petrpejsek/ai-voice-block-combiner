# 🎵 Kde najdu Music Library?

## ✅ Frontend restartován - Music Library je nyní dostupná!

### 📍 Kde to najdu:

1. **Otevřete aplikaci:** http://localhost:4000

2. **Vygenerujte nebo načtěte projekt:**
   - Zadejte téma a klikněte "Vygenerovat scénář"
   - NEBO načtěte existující projekt (pokud už nějaký máte)

3. **Počkejte, až script status = DONE** (všechny kroky zelené ✅)

4. **Scrollujte dolů** k sekci:
   ```
   🎵 Background Music
   ════════════════════════════════════════
   Systém automaticky vybírá hudbu z globální knihovny...
   
   [📚 Otevřít Music Library]  ← TADY!
   ```

5. **Klikněte na tlačítko "📚 Otevřít Music Library"**

6. **Modal se otevře:**
   ```
   ┌────────────────────────────────────────┐
   │ 🎵 Music Library              ✕        │
   │ Globální knihovna podkresové hudby     │
   ├────────────────────────────────────────┤
   │ Nahrát novou hudbu                     │
   │ [Choose Files: MP3/WAV] 📎            │
   │                                        │
   │ Tags (vyberte před uploadem):          │
   │ [ambient] [cinematic] [piano]...       │
   │                                        │
   │ Mood:                                  │
   │ [😐 Neutral] [🌑 Dark] [✨ Uplifting] │
   └────────────────────────────────────────┘
   ```

---

## 🎯 Quick Test (ověření, že to funguje):

1. Otevřete http://localhost:4000
2. Zadejte **jakékoliv téma** (např. "Test")
3. Klikněte **Vygenerovat scénář**
4. Počkejte na všechny kroky (může trvat 2-5 minut)
5. Po dokončení se **objeví sekce "🎵 Background Music"**
6. Klikněte **"📚 Otevřít Music Library"**
7. ✅ **Modal by se měl otevřít!**

---

## ❗ Pokud nevidíte tlačítko:

### Možné příčiny:

1. **Script není hotový** → Počkejte, až všechny kroky budou zelené ✅

2. **Nevidíte sekci Background Music** → Scrollujte dolů (je až za TTS Voice-over sekcí)

3. **Chyba v konzoli** → Otevřete Developer Tools (F12) a zkontrolujte errory

4. **Stará verze v cache** → Hard refresh:
   - **Windows/Linux:** `Ctrl + Shift + R`
   - **Mac:** `Cmd + Shift + R`

---

## 🎨 Screenshot kde to hledat:

```
╔══════════════════════════════════════════════════╗
║  📝 Generování textu                             ║
║  Status: DONE ✅                                 ║
╠══════════════════════════════════════════════════╣
║  🎙️ Voice-over Generation                       ║
║  ✅ Voice-over vygenerován! (120 souborů)       ║
╠══════════════════════════════════════════════════╣
║  🎵 Background Music        [📚 Otevřít Music]  ║  ← TADY!
║  ════════════════════════════════════════        ║
║  Systém automaticky vybírá hudbu z knihovny...  ║
║                                                  ║
║  Zatím není vybraná žádná hudba                 ║
║  [🤖 Auto-vybrat hudbu]                         ║
╠══════════════════════════════════════════════════╣
║  🎬 Video Compilation                            ║
║  ...                                             ║
╚══════════════════════════════════════════════════╝
```

---

## 🚀 První upload:

Po otevření Music Library:

1. **Klikněte na "Choose Files"** nebo přetáhněte soubor
2. **Vyberte MP3 nebo WAV** z vašeho počítače
3. **Před uploadem vyberte:**
   - **Tags:** Označte relevantní (např. `ambient`, `cinematic`)
   - **Mood:** Vyberte náladu (např. `🌊 Peaceful`)
4. **Soubory se nahrají automaticky**
5. **Vidíte je v seznamu** s audio přehrávačem

---

## 💡 Tip:

Pokud **ještě nemáte hotový projekt**, můžete zkusit:

1. Načíst existující projekt:
   - V konzoli: `ls /Users/petrliesner/podcasts/projects/`
   - Najděte nějaký `ep_*` s `script_state.json`
   - V UI zadejte episode_id do URL: `?episode=ep_abc123`

2. Nebo jednoduše **vygenerovat nový testovací projekt** (rychlejší než čekat)

---

✅ **Frontend běží na http://localhost:4000**  
✅ **Backend běží na http://localhost:50000**  
✅ **Music Library je připravena!**

Stačí otevřít aplikaci a najít tlačítko "📚 Otevřít Music Library" 🎉



