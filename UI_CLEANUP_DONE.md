# ✅ UI Cleanup Dokončen!

## Co bylo skryto (deprecated sekce):

### 1. Voice Generation Queue (ElevenLabs)
- **Řádek:** ~1580-1588
- **Co to bylo:** Stará fronta pro generování hlasů pomocí ElevenLabs API
- **Proč skryt:** Nyní používáme Google Cloud TTS v VideoProductionPipeline

### 2. Video Generation Studio
- **Řádek:** ~1590-1612  
- **Co to bylo:** Purple banner pro generování videí s DALL-E obrázky a Ken Burns efekty
- **Proč skryt:** Nahrazeno novým Video Compilation v VideoProductionPipeline

### 3. Voice Generator Card
- **Řádek:** ~1614-1619
- **Co to bylo:** Ruční generování hlasů z JSON 
- **Proč skryt:** Nyní používáme automatickou pipeline

### 4. DALL-E Test Section
- **Řádek:** ~1621-1720
- **Co to bylo:** Testovací sekce pro generování obrázků pomocí DALL-E 3
- **Proč skryt:** Nyní používáme archive.org videa místo statických obrázků

### 5. Main Processing Card
- **Řádek:** ~1723-2231
- **Co to bylo:** Stará kombinace audio souborů (upload + intro/outro + export)
- **Proč skryt:** Nahrazeno automatickou pipeline (Research → FDA → AAR → CB)

## Co zůstalo viditelné:

✅ **VideoProductionPipeline** - hlavní komponenta pro:
- Generování scénáře (Research → Writing → Validation → Packaging → TTS → FDA)
- Voice-over generation (Google Cloud TTS)
- Video Compilation (AAR + CB)

✅ **API Management modal** - pro nastavení OpenAI/OpenRouter klíčů

## Před/Po:

**PŘED:**
- 5 různých sekcí pro různé způsoby generování
- ElevenLabs fronta
- DALL-E test
- Ruční kombinace audio
- Video studio s Ken Burns

**PO:**
- 1 čistá pipeline: Téma → Scénář → Audio → Video
- Žádné zombie orphan komponenty
- Jednoduchá UX

## Jak teď vypadá UI:

```
Header
  └─ AI Voice Block Combiner

VideoProductionPipeline
  ├─ Generování textu
  │   ├─ Téma input
  │   ├─ Language / Target minutes
  │   ├─ Vygenerovat scénář [button]
  │   └─ Průběh (Research → FDA)
  │
  ├─ Voice-over Generation
  │   ├─ Vygenerovat Voice-over [button]
  │   └─ Audio soubory (collapsible)
  │
  └─ Video Compilation
      ├─ Vygenerovat Video [button]
      ├─ Progress bar (AAR → CB)
      └─ Video player + download
```

Vše ostatní skryto pomocí `{false && (...)}`

