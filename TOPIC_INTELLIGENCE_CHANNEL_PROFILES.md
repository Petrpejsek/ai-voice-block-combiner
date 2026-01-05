# Topic Intelligence Assistant - Channel Profiles

## ✅ Co bylo přidáno

Přidána funkcionalita **Channel Profiles** do Topic Intelligence Assistant - možnost výběru kanálového profilu, který řídí typ doporučených témat.

### 🎯 Nové funkce

1. **Dropdown "Channel Profile"** v hlavním panelu
2. **Tlačítko "View profile details"** - zobrazí detaily profilů
3. **2 default profily:**
   - **US History Docs** (historické dokumenty)
   - **US True Crime** (skutečné zločiny)
4. **Profile-aware LLM prompting** - profil se vkládá do promptu
5. **100% isolováno** od farmy/pipeline

---

## 🎨 UI změny

### Hlavní panel (Topic Intelligence)

```
┌────────────────────────────────────────────────────┐
│ 🔬 Topic Intelligence (US)     [⚙️ LLM Settings]  │
│ Manual research only • USA/EN focused              │
├────────────────────────────────────────────────────┤
│ [Channel Profile ▼] [Count] [Window] [Start]      │
│  └─ View profile details                           │
└────────────────────────────────────────────────────┘
```

### Profile Details Modal

- Seznam všech dostupných profilů
- Zobrazení základních info (name, content_type, style_notes)
- Možnost rychle přepnout profil
- Zvýrazněný aktuálně vybraný profil

---

## 📊 Datová struktura profilu

Každý profil obsahuje:

```json
{
  "id": "us_history_docs",
  "name": "US History Docs",
  "locale": "US",
  "language": "en-US",
  "content_type": "history_docs",
  "must_fit_topics": [
    "turning points",
    "empires",
    "betrayals",
    "disasters",
    "trials",
    "mysteries"
  ],
  "must_avoid_topics": [
    "graphic gore",
    "extremist propaganda",
    "explicit violence details"
  ],
  "style_notes": "Documentary style with thriller/mystery framing...",
  "archetype_weights": {
    "Final Days / Last Hours": 1.0,
    "Betrayal & Power": 1.0,
    "Mystery / Vanished": 1.0,
    ...
  },
  "avoid_topics": [
    "Holocaust denial",
    "genocide glorification",
    "extremist ideologies"
  ]
}
```

### Význam polí:

| Pole | Popis |
|------|-------|
| `must_fit_topics` | Pozitivní mantinely - témata MUSÍ se dotýkat těchto oblastí |
| `must_avoid_topics` | Soft blacklist - témata by neměla obsahovat tyto prvky |
| `avoid_topics` | **Hard blacklist** - absolutní zákaz těchto témat |
| `archetype_weights` | Preference archetypů (0.0-1.0), vyšší = preferovanější |
| `style_notes` | Tón vyprávění, framing (předává se LLM) |

---

## 🚀 Jak používat

### 1. Výběr profilu

1. Otevři Topic Intelligence panel (dole na stránce)
2. **V dropdownu "Channel Profile"** vyber:
   - `US History Docs` (default)
   - `US True Crime`
3. Klikni **"View profile details"** pro zobrazení plného profilu

### 2. Spuštění research

1. Vyber profil
2. Nastav počet doporučení (5-50)
3. Nastav časové okno (7d / 30d)
4. Klikni **"Start Research"**

LLM automaticky dostane profil a generuje témata podle něj.

### 3. Výsledky podle profilu

**US History Docs:**
- ✅ "The Last Hours of Cleopatra"
- ✅ "The Collapse of the Roman Empire"
- ✅ "Betrayal at Pearl Harbor"
- ❌ "Modern Political Scandals" (off-topic)

**US True Crime:**
- ✅ "The Zodiac Killer Investigation Timeline"
- ✅ "Forensic Breakthrough: Golden State Killer"
- ✅ "The Disappearance of Amelia Earhart"
- ❌ "Ancient Historical Murders" (wrong content type)

---

## 📁 Kde jsou profily uloženy

### Backend soubor

```
backend/topic_intel_profiles.json
```

Obsahuje všechny profily v JSON formátu.

### Načítání profilů

**Backend endpoint:**
```
GET /api/topic-intel/profiles
```

**Response:**
```json
{
  "success": true,
  "profiles": [
    {
      "id": "us_history_docs",
      "name": "US History Docs",
      "content_type": "history_docs",
      "style_notes": "..."
    },
    {
      "id": "us_true_crime",
      "name": "US True Crime",
      "content_type": "true_crime",
      "style_notes": "..."
    }
  ]
}
```

---

## 🔧 Backend implementace

### Request format

```json
{
  "count": 20,
  "window_days": 7,
  "profile_id": "us_history_docs",
  "llm_config": {
    "provider": "openrouter",
    "model": "openai/gpt-4o",
    "temperature": 0.7,
    "custom_prompt": null
  }
}
```

### Prompt composition

LLM dostane tento blok **CHANNEL PROFILE** v promptu:

```
**CHANNEL PROFILE:**
- Name: US History Docs
- Audience: US
- Language: en-US
- Content type: history_docs
- Must-fit topics: turning points, empires, betrayals, disasters...
- Must-avoid topics: graphic gore, extremist propaganda...
- Style notes: Documentary style with thriller/mystery framing...
- Archetype weights (0-1): {...}
- Hard blacklist (avoid_topics): [...]

**Current Trending Seeds (US):**
- [seed topics...]

**Task:** Generate 20 topics that FIT THE CHANNEL PROFILE.

**CRITICAL REQUIREMENTS:**
1. ALL topics MUST fit the "Must-fit topics" list
2. NEVER suggest topics from "Must-avoid topics" or "Hard blacklist"
3. Follow the style notes exactly
4. Prefer archetypes with higher weights
...
```

### Priorita pravidel (sestupně):

1. **avoid_topics** (hard blacklist) → absolutní zákaz
2. **must_fit_topics** → musí se dotýkat
3. **style_notes** → tón, framing
4. **archetype_weights** → preference archetypů
5. **must_avoid_topics** → soft blacklist

---

## 🔒 Izolace od farmy

**Profily jsou ZCELA ODDĚLENÉ od pipeline:**

✅ **Žádné vazby:**
- Nepřístupné z `script_pipeline.py`
- Nepřístupné z `project_store.py`
- Žádný vliv na automatické feedy
- Žádný vliv na tvorbu epizod

✅ **Samostatný config:**
- `backend/topic_intel_profiles.json` (izolovaný soubor)
- Nedotýká se `config/llm_defaults.json`
- Nedotýká se profile v farmě

✅ **Pouze Topic Intel:**
- Používáno POUZE v `/api/topic-intel/research`
- NIKDE JINDE v aplikaci

---

## 📝 Default profily (ready-to-use)

### A) US History Docs

**Zaměření:**
- Historické zlomové body
- Impéria a jejich pády
- Zrady a moc
- Katastrofy jako thriller
- Soudy, popravy, skandály
- Záhady a zmizení

**Styl:**
- Dokumentární s thriller/mystery framingem
- "Untold" úhly pohledu
- Lidský příběh za historickými událostmi

**Archetype weights:**
- Final Days / Last Hours: **1.0**
- Betrayal & Power: **1.0**
- Disaster as Thriller: **1.0**
- Mystery / Vanished: **1.0**
- Empire Collapse: **1.0**

### B) US True Crime

**Zaměření:**
- Vyšetřování, časové osy
- Soudní síň, případy
- Zmizení, podvody
- Kulty, studené případy
- Forenzní věda

**Styl:**
- Investigativní žurnalistika
- Rekonstrukce timeline
- "How they caught them" úhel
- Respekt k obětem

**Archetype weights:**
- Trial / Execution / Scandal: **1.0**
- Mystery / Vanished: **1.0**
- Conspiracy (Evidence-based): **0.9**
- Survival Stories: **0.9**

---

## 🛠️ Přidání vlastního profilu (budoucnost)

**MVP: Read-only** (profily v JSON souboru)

**Budoucí rozšíření:**
1. UI editor profilů
2. Přidávání/úprava/mazání profilů
3. Import/export profilů
4. Sdílení profilů mezi uživateli

### Jak přidat profil ručně (MVP):

1. Otevři `backend/topic_intel_profiles.json`
2. Zkopíruj existující profil
3. Uprav všechna pole podle potřeby
4. Ulož soubor
5. Restart backendu
6. Profil se objeví v UI dropdownu

**Příklad:**

```json
{
  "id": "us_science_docs",
  "name": "US Science Documentaries",
  "locale": "US",
  "language": "en-US",
  "content_type": "science_docs",
  "must_fit_topics": [
    "scientific discoveries",
    "technological breakthroughs",
    "space exploration",
    "medical advances"
  ],
  "must_avoid_topics": [
    "pseudoscience",
    "conspiracy theories without evidence"
  ],
  "style_notes": "Scientific documentary with accessible explanations. Focus on 'eureka moments' and human stories behind discoveries.",
  "archetype_weights": {
    "Genius vs. System": 1.0,
    "Forbidden / Hidden History": 0.9,
    "Mystery / Vanished": 0.8,
    ...
  },
  "avoid_topics": [
    "flat earth theories",
    "anti-vaccination propaganda"
  ]
}
```

---

## 🧪 Testování

### Test 1: Profile selection

1. Otevři Topic Intelligence panel
2. Klikni dropdown "Channel Profile"
3. Vyber "US True Crime"
4. Klikni "Start Research"
5. **Očekávání:** Témata o zločinech, vyšetřování, soudech

### Test 2: Profile details

1. Klikni "View profile details"
2. **Očekávání:** Modal s oběma profily
3. Klikni "Select" u druhého profilu
4. **Očekávání:** Modal se zavře, profil se přepne

### Test 3: Profile filtering

**US History Docs:**
- ✅ Mělo by vrátit historická témata
- ❌ Nemělo by vrátit true crime témata

**US True Crime:**
- ✅ Mělo by vrátit kriminální případy
- ❌ Nemělo by vrátit starověkou historii

---

## 📊 Srovnání profilů

| Feature | US History Docs | US True Crime |
|---------|----------------|---------------|
| **Časová éra** | Jakákoliv historie | Především 20.-21. století |
| **Styl** | Thriller/mystery | Investigativní |
| **Archetypes** | Empire, Betrayal, Final Days | Trial, Mystery, Conspiracy |
| **Must-fit** | Turning points, empires | Investigations, courtroom |
| **Avoid** | Graphic gore, propaganda | Gore, victim-blaming |

---

## ✅ Done kritéria (splněno)

- [x] Dropdown "Channel Profile" v UI
- [x] Tlačítko "View profile details"
- [x] Modal s detaily profilů
- [x] Backend endpoint `/api/topic-intel/profiles`
- [x] Profile loading v service
- [x] Profile block v LLM promptu
- [x] 2 default profily (History Docs + True Crime)
- [x] Profile-aware topic generation
- [x] 100% izolace od pipeline
- [x] Žádné automatické feedy
- [x] Dokumentace

---

## 🎉 Výsledek

**Profily fungují!**

Nyní můžeš:
1. ✅ Vybrat profil kanálu
2. ✅ LLM generuje on-topic témata
3. ✅ Témata odpovídají stylu profilu
4. ✅ Žádný vliv na farmu/pipeline
5. ✅ Snadno rozšiřitelné o nové profily

**Off-topic témata minimalizována díky must-fit/avoid pravidlům!** 🎯

---

**Implementováno:** Leden 2026  
**Profily:** 2 default (History Docs, True Crime)  
**Izolace:** 100% ✅  
**Status:** Ready to use



