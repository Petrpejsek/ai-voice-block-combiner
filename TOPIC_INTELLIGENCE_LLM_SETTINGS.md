# Topic Intelligence Assistant - LLM Settings Update

## ✅ Co bylo přidáno

Přidána **konfigurace LLM nastavení** pro Topic Intelligence Assistant, stejně jako u ostatních asistentů v aplikaci.

### Nové funkce

1. **Tlačítko ⚙️ LLM Settings** v hlavičce Topic Intelligence panelu
2. **Modal okno** s nastavením:
   - **Provider:** OpenRouter (jediný podporovaný)
   - **Model:** Výběr z populárních modelů (GPT-4o, Claude, Gemini, Llama...)
   - **Temperature:** Slider 0.0-2.0 (deterministic → creative)
   - **Custom Prompt:** Volitelné dodatečné instrukce

### Změny v kódu

**Frontend (`TopicIntelligencePanel.js`):**
- Přidán state `llmConfig` s výchozími hodnotami
- Přidáno tlačítko "⚙️ LLM Settings" vedle nadpisu
- Přidán modal s formulářem pro nastavení
- Konfigurace se posílá v requestu na backend

**Backend (`app.py`):**
- Endpoint `/api/topic-intel/research` přijímá nový parametr `llm_config`
- Validace OpenRouter API klíče (místo OpenAI)
- Předání konfigurace do service

**Backend Service (`topic_intel_service.py`):**
- Nová funkce `call_openai_openrouter()` pro volání OpenRouter API
- `research()` metoda přijímá LLM parametry
- `_expand_topics()` používá konfiguraci a custom prompt

## 🚀 Jak používat

### 1. Otevřít nastavení

1. Otevři frontend: `http://localhost:4000`
2. Scrolluj dolů k "🔬 Topic Intelligence (US)" panelu
3. Klikni na tlačítko **"⚙️ LLM Settings"** vpravo nahoře

### 2. Nastavit LLM

**Provider:**
- Pouze OpenRouter (automaticky)

**Model (výběr):**
- `openai/gpt-4o` (doporučeno) - nejlepší kvalita
- `openai/gpt-4o-mini` - rychlejší, levnější
- `anthropic/claude-3.5-sonnet` - alternativa
- `anthropic/claude-3-opus` - nejvyšší kvalita
- `google/gemini-pro-1.5` - Google model
- `meta-llama/llama-3.1-70b-instruct` - open-source

**Temperature (0.0-2.0):**
- **0.0-0.5:** Deterministický, konzistentní výsledky
- **0.5-1.0:** Vyvážený (doporučeno: 0.7)
- **1.0-2.0:** Kreativní, rozmanité výsledky

**Custom Prompt (volitelné):**
```
Focus on 20th century topics
```
nebo
```
Emphasize scientific discoveries and technological breakthroughs
```

### 3. Uložit a spustit research

1. Klikni "Save Settings"
2. Nastav počet doporučení a časové okno
3. Klikni "Start Research"
4. LLM použije tvou konfiguraci

## 📋 Požadavky

### API Klíče

**OpenRouter API klíč (povinný):**

```bash
# backend/.env
OPENROUTER_API_KEY=sk-or-v1-...your-key...
```

Získej na: https://openrouter.ai/keys

### Feature Flag

```bash
# backend/.env
TOPIC_INTEL_ENABLED=true
```

### Restart backendu

```bash
cd backend
python3 app.py
```

## 🎯 Příklady použití

### Základní research (výchozí nastavení)

- Model: `openai/gpt-4o`
- Temperature: `0.7`
- Custom prompt: (prázdné)

→ Vyvážený mix témat s thriller/mystery framing

### Kreativní research

- Model: `anthropic/claude-3.5-sonnet`
- Temperature: `1.2`
- Custom prompt: "Focus on untold stories and conspiracy theories"

→ Neobvyklé, kreativní témata

### Zaměřený research

- Model: `openai/gpt-4o-mini`
- Temperature: `0.3`
- Custom prompt: "Only topics from World War 2 era"

→ Specifická, konzistentní témata

### Levný/rychlý research

- Model: `openai/gpt-4o-mini`
- Temperature: `0.7`
- Custom prompt: (prázdné)

→ Rychlejší odpověď, nižší cena

## 🔧 Technické detaily

### OpenRouter API

```python
# Endpoint
POST https://openrouter.ai/api/v1/chat/completions

# Headers
Authorization: Bearer sk-or-v1-...
Content-Type: application/json

# Body
{
  "model": "openai/gpt-4o",
  "messages": [...],
  "temperature": 0.7
}
```

### Request formát (frontend → backend)

```json
{
  "count": 20,
  "window_days": 7,
  "llm_config": {
    "provider": "openrouter",
    "model": "openai/gpt-4o",
    "temperature": 0.7,
    "custom_prompt": "Focus on 20th century"
  }
}
```

### Custom Prompt integrace

Custom prompt se přidá na konec základního promptu:

```
[Základní prompt s archetypes, seeds, requirements...]

**Additional Instructions:**
{custom_prompt}

[Output format...]
```

## 💡 Tipy

1. **Začni s výchozím nastavením** (GPT-4o, temp 0.7)
2. **Zvyš temperature** (→ 1.0-1.5) pokud chceš diverzitu
3. **Sniž temperature** (→ 0.3-0.5) pro konzistentní výsledky
4. **Použij custom prompt** pro specifická témata
5. **Zkus různé modely** - každý má jiný "styl"

## 🐛 Troubleshooting

### "OpenRouter API key not configured"

**Fix:**
```bash
# Přidej do backend/.env
OPENROUTER_API_KEY=sk-or-v1-...

# Restart backend
cd backend && python3 app.py
```

### LLM vrací prázdné výsledky

**Možné příčiny:**
- Custom prompt je příliš restriktivní
- Temperature je příliš nízko (0.0-0.1)
- Model nepodporuje JSON output

**Fix:**
- Zkus zvýšit temperature na 0.5+
- Odstraň/zmírni custom prompt
- Použij `openai/gpt-4o` (nejspolehlivější)

### Výsledky jsou "off-topic"

**Fix:**
- Sniž temperature na 0.5 nebo níž
- Přidej specifický custom prompt:
  ```
  Only suggest topics that are directly related to documented historical events.
  Avoid speculative or conspiracy-focused topics.
  ```

## 📊 Srovnání modelů

| Model | Rychlost | Kvalita | Cena | Doporučení |
|-------|----------|---------|------|------------|
| openai/gpt-4o | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | $$ | **Best overall** |
| openai/gpt-4o-mini | ⚡⚡⚡⚡⚡ | ⭐⭐⭐⭐ | $ | Best value |
| claude-3.5-sonnet | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | $$$ | Most creative |
| claude-3-opus | ⚡⚡ | ⭐⭐⭐⭐⭐ | $$$$ | Highest quality |
| gemini-pro-1.5 | ⚡⚡⚡⚡ | ⭐⭐⭐⭐ | $$ | Good alternative |
| llama-3.1-70b | ⚡⚡⚡⚡ | ⭐⭐⭐ | $ | Budget option |

## ✅ Hotovo!

Nyní máš plnou kontrolu nad LLM generováním témat:
- ✅ Výběr modelu
- ✅ Nastavení temperature
- ✅ Custom instrukce
- ✅ OpenRouter API integrace

Stejně jako u ostatních asistentů v aplikaci! 🎉

---

**Aktualizováno:** Leden 2026  
**Verze:** 1.1  
**Provider:** OpenRouter only



