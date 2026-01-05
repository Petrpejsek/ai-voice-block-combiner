# ✅ OPRAVA: Video teď má voiceover!

## Co jsem opravil:

### 1. CompilationBuilder nyní přidává audio voiceover

**Před:**
```python
# concatenate_clips() - pouze video
ffmpeg -f concat -i clips.txt -c:v libx264 output.mp4
# ❌ Žádné audio!
```

**Po:**
```python
# concatenate_clips() - video + audio
ffmpeg -f concat -i clips.txt \     # Video klipy
       -i combined_audio.mp3 \      # Voiceover audio
       -map 0:v:0 -map 1:a:0 \      # Map video + audio
       -shortest output.mp4          # Ukonči na kratší stream
# ✅ Video s voiceoverem!
```

### 2. build_compilation() hledá MP3 soubory

```python
# Najdi MP3 soubory v projektu
mp3_files = glob.glob("projects/ep_xxx/block_*.mp3")

if mp3_files:
    # Spojit MP3 do jednoho
    ffmpeg -f concat -i audio_list.txt combined_audio.mp3
    
    # Použít v concatenate
    concatenate_clips(clips, output, audio_file=combined_audio.mp3)
else:
    print("⚠️ No MP3 files - video will be silent!")
```

### 3. Hydratace UI stavu po refreshi

**Frontend teď načítá:**
- ✅ TTS stav (pokud existují MP3 soubory)
- ✅ Video compilation stav (pokud existuje video)
- ✅ Zobrazuje existující MP3 a videa

---

## 🎯 Správný workflow:

```
1. Vygenerovat scénář
   → Creates: tts_ready_package + shot_plan
   ↓
2. Vygenerovat Voice-over 🎤
   → Creates: block_01.mp3, block_02.mp3, ...
   ↓
3. Vygenerovat Video 🎬
   → AAR: Finds archive.org videos
   → CB: Combines videos + adds voiceover audio
   ↓
   ✅ Final video WITH voiceover!
```

---

## ⚠️ DŮLEŽITÉ:

**Voice-over MUSÍ být vygenerován PŘED video compilation!**

Pokud klikneš na "Vygenerovat Video" bez voice-overu:
- ✅ Video se vygeneruje (archive.org klipy)
- ❌ Video bude NĚMÉ (bez voiceoveru)

**Řešení:**
1. Klikni "Vygenerovat Voice-over" NEJDŘÍV
2. Počkej až se vytvoří MP3 soubory (3-5 min)
3. Pak klikni "Vygenerovat Video"

---

## 📊 Pro tvůj projekt ep_9509895b9283:

**Aktuální stav:**
- ✅ Scénář: DONE
- ✅ Shot plan: DONE
- ❌ **MP3 soubory: 0** ← Musíš vygenerovat!
- ✅ Video: Existuje (ale je němé)

**Co dělat:**
1. Klikni "Vygenerovat Voice-over"
2. Počkej 3-5 minut
3. Klikni "Vygenerovat Video" znovu
4. ✅ Nové video bude mít voiceover!

---

## 🔧 Technické detaily:

### FFmpeg command s audio:
```bash
ffmpeg -y \
  -f concat -safe 0 -i concat_list.txt \  # Video clips
  -i combined_voiceover.mp3 \             # Audio
  -map 0:v:0 \                            # Map video stream
  -map 1:a:0 \                            # Map audio stream
  -c:v libx264 -preset medium -crf 23 \  # Video codec
  -c:a aac -b:a 128k \                    # Audio codec
  -shortest \                             # End on shorter stream
  output.mp4
```

### Combine MP3 files:
```bash
# Create concat list
echo "file 'block_01.mp3'" > audio_list.txt
echo "file 'block_02.mp3'" >> audio_list.txt
...

# Combine
ffmpeg -f concat -safe 0 -i audio_list.txt -c copy combined.mp3
```

