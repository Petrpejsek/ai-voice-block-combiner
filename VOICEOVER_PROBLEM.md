# ❌ PROBLÉM: Video bez voiceoveru

## Co se stalo:

1. ✅ Scénář vygenerován (text + shot_plan)
2. ❌ **Voice-over NEBYL vygenerován** (žádné MP3 soubory)
3. ✅ Video kompilace proběhla (pouze archive.org videa)
4. ❌ **Výsledné video je němé** (chybí voiceover audio)

## Proč je video němé:

### CompilationBuilder nepoužívá audio!

```python
# compilation_builder.py - concatenate_clips()
cmd = [
    "ffmpeg",
    "-f", "concat",
    "-i", concat_list.txt,  # Pouze video soubory!
    "-c:v", "libx264",
    # ❌ CHYBÍ: přidání audio voiceoveru
    output_file
]
```

## Správný workflow:

```
1. Vygenerovat scénář
   ↓
2. **Vygenerovat Voice-over** ← DŮLEŽITÉ!
   → Vytvoří MP3 bloky (block_01.mp3, block_02.mp3, ...)
   ↓
3. Vygenerovat Video
   → AAR najde archive.org videa
   → CB spojí videa + PŘIDÁ AUDIO z MP3 bloků
   ↓
   ✅ Finální video s voiceoverem
```

## Co je potřeba opravit:

### 1. CompilationBuilder musí přidat audio:

```python
def concatenate_clips_with_audio(
    clip_files: List[str],
    audio_file: str,  # ← Přidat MP3 voiceover
    output_file: str
):
    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-i", concat_list.txt,      # Video
        "-i", audio_file,            # Audio voiceover
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",                 # Ukonči na kratší stream
        output_file
    ]
```

### 2. build_compilation() musí najít MP3 soubory:

```python
# Najdi MP3 soubory v projektu
episode_dir = os.path.join(storage_dir, "..")
mp3_files = sorted(glob.glob(os.path.join(episode_dir, "block_*.mp3")))

if not mp3_files:
    raise Exception("Voice-over nebyl vygenerován! Spusťte TTS nejdřív.")

# Spojit MP3 do jednoho audio souboru
combined_audio = combine_mp3_files(mp3_files)

# Použít v concatenate
concatenate_clips_with_audio(clip_files, combined_audio, output_file)
```

## Aktuální stav projektu ep_9509895b9283:

- ✅ script_state.json: DONE
- ✅ tts_ready_package: Existuje
- ❌ **MP3 soubory: 0** ← PROBLÉM!
- ✅ Video: 23 MB (bez audio)

## Řešení pro uživatele:

1. **Klikni na "Vygenerovat Voice-over"** (Google Cloud TTS)
2. Počkej 3-5 minut
3. **Pak** klikni na "Vygenerovat Video"
4. ✅ Video bude mít voiceover!

