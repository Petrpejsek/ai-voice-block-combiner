# 📹 Návod: Jak vygenerovat video

## 🎯 Tříkrokový proces:

### Krok 1: Vygenerovat scénář ✅
```
[Téma input] → [Vygenerovat scénář]
↓
Research → Writing → Validation → Packaging → TTS Formatting → FDA
↓
✅ Scénář hotový (script_status: DONE)
```

### Krok 2: Vygenerovat Voice-over 🎤
```
Po dokončení scénáře se objeví sekce:

┌─────────────────────────────────────┐
│ 🎤 Voice-over Generation            │
│                                     │
│ [Vygenerovat Voice-over] ← KLIKNI  │
│                                     │
│ ⏳ Generování MP3 bloků...          │
│                                     │
│ ✅ Audio soubory (collapsible ▼)   │
│    ├─ block_01.mp3                 │
│    ├─ block_02.mp3                 │
│    └─ ...                           │
└─────────────────────────────────────┘
```

### Krok 3: Vygenerovat Video 🎬
```
Po dokončení Voice-over se objeví sekce:

┌─────────────────────────────────────┐
│ 🎬 Video Compilation                │
│                                     │
│ [Vygenerovat Video] ← KLIKNI        │
│                                     │
│ ⏳ AAR (Archive Asset Resolver)     │
│ ⏳ CB (Compilation Builder)         │
│                                     │
│ ✅ Video hotovo!                    │
│ [Video player]                      │
│ [📥 Stáhnout video]                 │
└─────────────────────────────────────┘
```

---

## ⚠️ Proč nevidím tlačítko "Vygenerovat Video"?

Tlačítko se zobrazí POUZE když jsou splněny **VŠECHNY** podmínky:

1. ✅ Scénář vygenerován (`script_status: DONE`)
2. ✅ FDA vytvořil shot_plan (`shot_plan` existuje)
3. ✅ **Voice-over dokončen** (`ttsState.status: done`) ⭐ KLÍČOVÉ!

---

## 🔍 Jak zjistit stav projektu:

### Backend API:
```bash
# Zkontroluj status projektu
curl http://localhost:50000/api/projects/ep_XXXXX | jq '.script_status'

# Výstup:
# "DONE" = scénář hotový
# "RUNNING_TTS" = generování MP3
# "RUNNING_ASSET_RESOLVER" = AAR běží
# "RUNNING_COMPILATION_BUILDER" = CB běží
```

### Filesystem:
```bash
# Zkontroluj MP3 soubory
ls projects/ep_XXXXX/*.mp3

# Pokud vidíš soubory → Voice-over hotový
# Pokud prázdno → musíš spustit Voice-over generování
```

---

## 🎓 Příklad kompletního workflow:

```
1. Téma: "Tesla vs Socrates"
   ↓
2. [Vygenerovat scénář]
   ⏳ 2-3 minuty
   ✅ Scénář hotový
   ↓
3. [Vygenerovat Voice-over]
   ⏳ 3-5 minut (Google Cloud TTS)
   ✅ 8 MP3 bloků vygenerováno
   ↓
4. [Vygenerovat Video] ← TEPRVE TEĎ SE OBJEVÍ!
   ⏳ 5-15 minut (AAR + CB)
   ✅ episode_*.mp4 hotové!
```

---

## 📊 Současný stav tvého projektu:

**ep_9509895b9283:**
- ✅ Scénář: DONE
- ✅ Shot plan: Ano
- ❌ **MP3 bloky: 0 souborů** ← CHYBÍ!

**→ Akce:** Klikni na "Vygenerovat Voice-over" nejdřív!

