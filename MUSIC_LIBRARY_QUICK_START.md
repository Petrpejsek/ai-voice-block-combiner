# 🎵 Music Library - Quick Start Guide

## 🚀 Rychlý návod (5 minut)

### Krok 1: Nahrajte hudbu do knihovny

1. Otevřete aplikaci (http://localhost:4000)
2. V sekci **Background Music** klikněte na **📚 Otevřít Music Library**
3. V modalu:
   - Klikněte na **Choose Files** a vyberte MP3/WAV soubory
   - **Před uploadem** vyberte:
     - **Tags:** (např. `ambient`, `cinematic`, `piano`)
     - **Mood:** (např. `peaceful`, `dark`, `uplifting`)
   - Upload se provede automaticky po výběru souborů

**Tip:** Nahrajte aspoň 3-5 různých hudeb s různými moods pro lepší auto-výběr.

---

### Krok 2: Vygenerujte projekt

1. Zadejte téma (např. "Tajemství Nikoly Tesly")
2. Klikněte **Vygenerovat scénář**
3. Počkejte na dokončení všech kroků (Research → Writing → Validation → Packaging → TTS → Footage Director)
4. Klikněte **Vygenerovat Voice-over** (Google TTS)

---

### Krok 3: Automatický výběr hudby

Po vygenerování voice-over systém **automaticky** vybere hudbu:

- Analyzuje **téma** scénáře
- Vyhodnotí **náladu** podle klíčových slov
- Vybere nejlepší match z vaší knihovny

**Příklad:**
```
Téma: "Tajemství Nikoly Tesly" 
→ Mood: dark (obsahuje mystery)
→ Tags: ["cinematic", "dramatic"]
→ Vybraná hudba: dark_piano.mp3
```

---

### Krok 4: Preview & Úpravy (volitelné)

V sekci **Background Music** vidíte:

```
✅ Vybraná hudba
   dark_piano.mp3
   🌑 dark • cinematic, dramatic • 3:24

   ▶ [Audio preview]              [🗑️ Zrušit]

💡 Tip: Systém automaticky vybral podle tématu...
```

**Možnosti:**
- **Poslechnout si** preview pomocí audio přehrávače
- **Zrušit výběr** a nechat systém vybrat znovu
- **Změnit výběr** kliknutím na "📚 Otevřít Music Library" a výběrem jiné hudby

---

### Krok 5: Vygenerujte video

1. Klikněte **🎬 Vygenerovat Video**
2. Systém automaticky:
   - Stáhne archive.org videa podle shot planu
   - Spojí je s voice-overem
   - **Přidá vybranou hudbu** (mixovanou na -30dB s fade-in/out)
   - Vytvoří finální video

**Výsledek:** Video s profesionální podkresovou hudbou! 🎉

---

## 📚 Správa knihovny

### Přidat novou hudbu:
1. Otevřít Music Library
2. Upload MP3/WAV
3. Vybrat tags + mood
4. Hotovo!

### Filtrování:
- **Podle mood:** Dark, Uplifting, Peaceful...
- **Podle tagu:** Ambient, Cinematic, Piano...
- **Hledat:** Název souboru nebo tag

### Edit metadata:
- **Aktivní/Neaktivní:** Checkboxem (neaktivní se nepoužívají pro auto-select)
- **Tags:** Nelze editovat po uploadu (feature pro budoucnost)
- **Delete:** 🗑️ Smazat (nevratné!)

---

## 🎯 Best Practices

### Doporučení pro hudbu:

1. **Délka:** 2-5 minut (pokrývá většinu videí)
2. **Typ:** "Pad" hudba (ambient, atmospheric, bez výrazného rytmu)
3. **Mood diversity:** Nahrajte aspoň:
   - 2× **dark** (mystery, tension)
   - 2× **uplifting** (hopeful, positive)
   - 2× **peaceful** (calm, ambient)
   - 1× **dramatic** (intense, action)

4. **Tags:** Buďte konzistentní:
   - ✅ `ambient`, `cinematic`, `piano`
   - ❌ `Ambient Music`, `amb`, `AMBIENT`

### Naming convention:
```
✅ ambient_pad_01.mp3
✅ dark_cinematic_tension.mp3
✅ uplifting_electronic_hope.mp3

❌ track_1.mp3  (není popisné)
❌ my song.mp3  (mezery problematické)
```

---

## ❓ FAQ

### Q: Můžu použít stejnou hudbu pro více projektů?
**A:** Ano! To je celý smysl global library. Jednou nahrajete, používáte vždy.

### Q: Co když systém vybere špatnou hudbu?
**A:** Klikněte na "📚 Otevřít Music Library" a vyberte si manuálně. Váš výběr se uloží do projektu.

### Q: Jak systém určuje mood?
**A:** Podle klíčových slov v tématu:
- `dark`, `mystery`, `crime`, `war` → **dark**
- `hope`, `future`, `innovation` → **uplifting**
- `battle`, `conflict`, `crisis` → **dramatic**
- Ostatní → **peaceful**

### Q: Můžu přegenerovat video s jinou hudbou?
**A:** Ano! Změňte hudbu v Music Library a klikněte "🔁 Přegenerovat video".

### Q: Kde se ukládají soubory?
**A:** V `uploads/global_music/` (backend). Metadata v `uploads/global_music/music_manifest.json`.

### Q: Podporuje formáty jiné než MP3/WAV?
**A:** Ne, v současnosti jen MP3 a WAV. OGG, FLAC, etc. nejsou podporované.

---

## 🛠️ Troubleshooting

### Hudba se nepřehrává:
- Zkontrolujte, že backend běží (http://localhost:50000)
- Zkontrolujte console (F12) pro chyby

### Auto-select nefunguje:
- Nahrajte aspoň 3 hudby s různými moods
- Zkontrolujte, že jsou označené jako **Aktivní**
- Zkontrolujte backend logs (`backend/backend_server.log`)

### Upload selhal:
- Max velikost: **100MB** per soubor
- Povolené formáty: `.mp3`, `.wav`
- Zkontrolujte disk space

### Video nemá hudbu:
- Zkontrolujte, že jste vybrali hudbu (nebo použili auto-select)
- Zkontrolujte compilation report v `output/compilation_report_*.json`
  - Hledejte: `"music_report": { "enabled": true }`

---

## ✅ Checklist před prvním použitím

- [ ] Backend běží (port 50000)
- [ ] Frontend běží (port 4000)
- [ ] Nahráno aspoň 5 hudeb do knihovny
- [ ] Každá hudba má nastavený mood + tags
- [ ] Všechny hudby jsou označené jako "Aktivní"
- [ ] Vygenerován testovací projekt s TTS
- [ ] Zkouška auto-select (měl by vybrat hudbu)
- [ ] Zkouška video compilation (mělo by mít hudbu)

---

🎉 **Nyní jste připraveni vytvářet videa s profesionální podkresovou hudbou!**

Pro podrobnosti viz: `MUSIC_LIBRARY_COMPLETE.md`



