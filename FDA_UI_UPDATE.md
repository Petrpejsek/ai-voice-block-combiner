# ✅ FDA přidán do "Pokročilé nastavení" v UI

## Změna

**Před:**
```
Zobrazit pokročilé nastavení (LLM kroky 1–3)
├── 1) Research (LLM)
├── 2) Writing / Narrative (LLM)
├── 3) Fact Validation (LLM)
└── 5) TTS Formatting (LLM)
```
❌ Chybí krok 6 (FDA)  
❌ Zavádějící název ("LLM kroky 1-3" ale obsahuje i krok 5)

**Po:**
```
Zobrazit pokročilé nastavení (Pipeline kroky 1–6)
├── 1) Research (LLM)
├── 2) Writing / Narrative (LLM)
├── 3) Fact Validation (LLM)
├── 5) TTS Formatting (LLM)
└── 6) Footage Director (Deterministický) ← NOVÝ!
```
✅ Obsahuje všechny kroky 1-6  
✅ Jasný název "Pipeline kroky 1-6"  
✅ FDA je viditelný s popisem

---

## Co je v UI nové

### Sekce: 6) Footage Director (Deterministický)

**Popis:**
```
Generuje shot_plan (scény, keywords, shot_types) ze tts_ready_package.
Žádné LLM, žádné externí API - čistě deterministický algoritmus.
```

**Parametry (fixed MVP):**
- words_per_minute: 150
- target_scene_duration: 20-35s
- blocks_per_scene: 3-8
- emotion: neutral/tension/tragedy/hope/victory/mystery
- shot_types: 9 povolených typů (archival, maps, speeches, ...)
- cut_rhythm: slow/medium/fast

**Poznámka:**
```
💡 FDA je automatický krok bez nastavení. 
   Shot_plan se ukládá do script_state.json.
```

---

## Proč FDA není nastavitelný?

FDA je **MVP verze** - parametry jsou **fixed** (žádné uživatelské nastavení):

| Parametr | Hodnota | Důvod |
|----------|---------|-------|
| `words_per_minute` | 150 | Standard pro anglickou řeč |
| `target_scene_duration` | 20-35s | Optimální pro storytelling |
| `shot_types` | 9 fixed hodnot | MVP allowlist |
| `emotion` | 6 fixed hodnot | MVP allowlist |
| `cut_rhythm` | slow/medium/fast | MVP allowlist |

**Budoucnost:** V další verzi by se mohly přidat:
- Konfigurovatelné `words_per_minute` per jazyk
- Dynamické allowlisty (custom shot_types)
- Konfigurovatelná délka scén
- API pro validaci shot_plan

---

## Jak to vypadá v UI

### 1. Collapsed (default)
```
🔽 Zobrazit pokročilé nastavení (Pipeline kroky 1–6)
```

### 2. Expanded
```
🔼 Skrýt pokročilé nastavení (Pipeline kroky 1–6)

┌─────────────────────────────────────────────┐
│ 1) Research (LLM)                           │
│   Provider: openai / Model: gpt-4o         │
│   Temperature: 0.4                          │
│   Prompt template: (custom nebo default)   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 2) Writing / Narrative (LLM)                │
│   Provider: openai / Model: gpt-4o         │
│   Temperature: 0.4                          │
│   Prompt template: (custom nebo default)   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 3) Fact Validation (LLM)                    │
│   Provider: openai / Model: gpt-4o         │
│   Temperature: 0.4                          │
│   Prompt template: (custom nebo default)   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 5) TTS Formatting (LLM)                     │
│   Provider: openai / Model: gpt-4o         │
│   Temperature: 0.4                          │
│   Prompt template: (custom nebo default)   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 6) Footage Director (Deterministický) ✨NEW │
│                                             │
│ Generuje shot_plan ze tts_ready_package.   │
│ Žádné LLM, žádné externí API.              │
│                                             │
│ Parametry (fixed MVP):                     │
│ • words_per_minute: 150                    │
│ • target_scene_duration: 20-35s            │
│ • blocks_per_scene: 3-8                    │
│ • emotion: neutral/tension/tragedy/...     │
│ • shot_types: 9 povolených typů            │
│ • cut_rhythm: slow/medium/fast             │
│                                             │
│ 💡 FDA je automatický krok bez nastavení.  │
│    Shot_plan se ukládá do script_state.    │
└─────────────────────────────────────────────┘
```

---

## Soubory změněny

### `frontend/src/components/VideoProductionPipeline.js`

**Změna 1:** Název sekce (řádek 733)
```javascript
// Před:
{showAdvanced ? 'Skrýt' : 'Zobrazit'} pokročilé nastavení (LLM kroky 1–3)

// Po:
{showAdvanced ? 'Skrýt' : 'Zobrazit'} pokročilé nastavení (Pipeline kroky 1–6)
```

**Změna 2:** Přidána sekce FDA (po řádku 1014)
```javascript
{/* Footage Director Assistant (FDA) */}
<div className="bg-blue-50 border border-blue-200 rounded p-3">
  <div className="text-sm font-semibold text-gray-800 mb-3">
    6) Footage Director (Deterministický)
  </div>
  <div className="text-xs text-gray-500 mb-3">
    Generuje shot_plan (scény, keywords, shot_types) ze tts_ready_package. 
    <span className="font-semibold"> Žádné LLM, žádné externí API</span> 
    - čistě deterministický algoritmus.
  </div>
  {/* ... parametry ... */}
</div>
```

---

## Restart potřeba?

**Ano, restart frontendu:**
```bash
# Zastav frontend
kill $(lsof -ti:4000)

# Spusť znovu
cd /Users/petrliesner/podcasts/frontend
PORT=4000 npm start
```

Po restartu **uvidíš FDA v pokročilých nastaveních!** 🎉

---

## ✅ Shrnutí

- ✅ Název sekce: "Pipeline kroky 1–6" (místo "LLM kroky 1-3")
- ✅ FDA přidán jako 6) Footage Director (Deterministický)
- ✅ Popis co FDA dělá
- ✅ Seznam fixed parametrů (MVP)
- ✅ Poznámka že je automatický bez nastavení
- ✅ Vizuálně odlišený (modré pozadí = deterministický, ne LLM)

**Po restartu frontendu bude FDA viditelný v pokročilých nastaveních!** 🚀



