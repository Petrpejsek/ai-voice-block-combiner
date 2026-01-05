# 🎬 End-to-End Integration Guide

**Google TTS → Video Pipeline**

Tento dokument popisuje, jak propojit TTS generování s video pipeline pro automatický end-to-end flow.

---

## 📋 Complete Flow Overview

```
1. User Input → Topic
2. LLM1: Research → research_report
3. LLM2: Narrative → draft_script
4. LLM3: Validation → validation_result
5. LLM4: Composer → script_package
6. LLM5: TTS Format → tts_ready_package
7. 🆕 TTS Generate → Narrator_XXXX.mp3     ← NOVÝ KROK
8. Video Generate → final_video.mp4
```

---

## 🔌 Integration Points

### Option A: Manual (test/debug)

**Krok 1:** Vygeneruj script (LLM1-5)
```bash
# Spusť script pipeline přes API nebo frontend
POST /api/script/generate
{
  "topic": "your topic",
  "language": "en",
  "target_minutes": 5
}

# Počkej na dokončení, získej episode_id
```

**Krok 2:** Vygeneruj audio
```bash
# Zavolej TTS endpoint s výsledkem z pipeline
curl -X POST http://localhost:50000/api/tts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tts_ready_package": {
      "narration_blocks": [...]  # z script_state.json
    }
  }'
```

**Krok 3:** Vygeneruj video
```bash
# Automaticky najde Narrator_*.mp3 v uploads/
curl -X POST http://localhost:50000/api/generate-video-with-audio \
  -H "Content-Type: application/json" \
  -d '{
    "images": [...],  # z DALL-E nebo existující
    "project_name": "my_video"
  }'
```

---

### Option B: Semi-automatic (frontend/backend integration)

**Backend přidání do script_pipeline.py:**

```python
# V script_pipeline.py po TTS formatting (LLM5)
def _run_script_pipeline(state, episode_id, ...):
    # ... existující LLM1-5 kroky ...
    
    # TTS Formatting (step 5)
    if state['steps']['tts_format']['status'] == 'DONE':
        _run_tts_formatting(...)
        
        # 🆕 NOVÝ KROK: Generate audio
        if state.get('tts_ready_package'):
            try:
                print(f"🎤 Spouštím TTS generování pro {episode_id}")
                tts_result = _generate_tts_audio(
                    state['tts_ready_package'], 
                    episode_id
                )
                
                # Ulož výsledek do state
                state['tts_audio_result'] = {
                    'generated_blocks': tts_result.get('generated_blocks', 0),
                    'failed_blocks': tts_result.get('failed_blocks_count', 0),
                    'timestamp': _now_iso(),
                    'output_files': tts_result.get('generated_files', [])
                }
                
                self.store.write_script_state(episode_id, state)
                print(f"✅ TTS audio vygenerováno: {tts_result['generated_blocks']} bloků")
                
            except Exception as e:
                print(f"⚠️ TTS generování selhalo: {e}")
                # Pokračuj dál (video lze vytvořit i bez audio)
```

**Helper funkce (přidej do script_pipeline.py):**

```python
def _generate_tts_audio(tts_package: dict, episode_id: str) -> dict:
    """
    Volá /api/tts/generate endpoint interně
    Returns: JSON response z endpointu
    """
    import requests
    
    try:
        response = requests.post(
            'http://localhost:50000/api/tts/generate',
            json={'tts_ready_package': tts_package},
            timeout=600  # 10 minut pro dlouhé dokumenty
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"TTS endpoint error: {response.status_code} - {response.text}")
            
    except requests.exceptions.Timeout:
        raise Exception("TTS generování trvalo příliš dlouho (>10 min)")
    except requests.exceptions.ConnectionError:
        raise Exception("Backend není dostupný na http://localhost:50000")
```

---

### Option C: Fully automatic (recommended)

**Frontend změny (App.js nebo VideoProductionPipeline.js):**

```javascript
// Po dokončení script generation
const handleScriptGeneration = async () => {
  // 1. Generate script (LLM1-5)
  const scriptResponse = await axios.post('/api/script/generate', {
    topic,
    language,
    target_minutes
  });
  
  const episodeId = scriptResponse.data.episode_id;
  
  // 2. Poll for completion
  let scriptState;
  while (true) {
    const stateResponse = await axios.get(`/api/script/state/${episodeId}`);
    scriptState = stateResponse.data.data;
    
    if (scriptState.script_status === 'DONE') break;
    if (scriptState.script_status === 'ERROR') throw new Error('Script failed');
    
    await sleep(2000); // Wait 2s
  }
  
  // 3. 🆕 Generate TTS audio
  console.log('🎤 Generating audio...');
  const ttsResponse = await axios.post('/api/tts/generate', {
    tts_ready_package: scriptState.tts_ready_package
  });
  
  if (!ttsResponse.data.success) {
    throw new Error('TTS generation failed');
  }
  
  console.log(`✅ Audio ready: ${ttsResponse.data.generated_blocks} blocks`);
  
  // 4. Generate images (DALL-E)
  console.log('🎨 Generating images...');
  const imagesResponse = await axios.post('/api/generate-images', {
    prompts: generatePromptsFromScript(scriptState)
  });
  
  // 5. Generate video with audio
  console.log('🎬 Generating video...');
  const videoResponse = await axios.post('/api/generate-video-with-audio', {
    images: imagesResponse.data.data.generated_images,
    project_name: episodeId
  });
  
  console.log('✅ Video ready!', videoResponse.data.download_url);
};
```

---

## 🔄 State Management

**script_state.json rozšíření:**

```json
{
  "episode_id": "ep_xxx",
  "script_status": "DONE",
  "steps": {
    "research": { "status": "DONE" },
    "narrative": { "status": "DONE" },
    "validation": { "status": "DONE" },
    "composer": { "status": "DONE" },
    "tts_format": { "status": "DONE" }
  },
  "tts_ready_package": { ... },
  
  "tts_audio_result": {
    "generated_blocks": 200,
    "failed_blocks": 0,
    "timestamp": "2024-12-26T20:00:00Z",
    "output_files": [
      "Narrator_0001.mp3",
      "Narrator_0002.mp3",
      "..."
    ],
    "total_duration_seconds": 2400
  }
}
```

---

## 🛡️ Error Handling

### Strategie pro partial failures

**Pokud některé TTS bloky failnou:**

```python
# V pipeline
tts_result = _generate_tts_audio(...)

if tts_result['failed_blocks_count'] > 0:
    failed_ratio = tts_result['failed_blocks_count'] / tts_result['total_blocks']
    
    if failed_ratio > 0.1:  # Více než 10% failů
        print(f"⚠️ WARNING: {failed_ratio*100:.1f}% bloků selhalo")
        # Upozorni uživatele nebo retry
    else:
        print(f"✅ Audio OK ({tts_result['generated_blocks']} bloků)")
        # Pokračuj na video
```

### Recovery flow

**Pokud TTS úplně selže:**

```python
try:
    tts_result = _generate_tts_audio(...)
except Exception as e:
    print(f"❌ TTS generování selhalo: {e}")
    
    # Option 1: Vytvořit video bez audio
    print("ℹ️  Vytvářím video bez audio")
    video_result = _generate_video_without_audio(...)
    
    # Option 2: Použít ElevenLabs fallback (pokud dostupné)
    # ...
    
    # Option 3: Stop pipeline a notify user
    raise Exception("TTS required but failed")
```

---

## 📊 Performance Monitoring

**Přidej tracking do pipeline:**

```python
import time

def _run_script_pipeline_with_metrics(state, episode_id, ...):
    metrics = {
        'start_time': time.time(),
        'steps_duration': {}
    }
    
    # Research
    step_start = time.time()
    _run_research(...)
    metrics['steps_duration']['research'] = time.time() - step_start
    
    # ... další kroky ...
    
    # TTS
    step_start = time.time()
    tts_result = _generate_tts_audio(...)
    metrics['steps_duration']['tts'] = time.time() - step_start
    metrics['tts_blocks'] = tts_result['generated_blocks']
    
    # Total
    metrics['total_duration'] = time.time() - metrics['start_time']
    
    # Log metrics
    print(f"📊 Pipeline metrics:")
    print(f"  Total: {metrics['total_duration']:.1f}s")
    print(f"  TTS: {metrics['steps_duration']['tts']:.1f}s ({metrics['tts_blocks']} blocks)")
    
    # Ulož do state
    state['pipeline_metrics'] = metrics
```

---

## 🧪 Testing End-to-End

**Test skript:**

```bash
#!/bin/bash
# test_e2e.sh

echo "🧪 End-to-End Test"
echo ""

# 1. Generate script
echo "1️⃣ Generating script..."
RESPONSE=$(curl -s -X POST http://localhost:50000/api/script/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "test topic",
    "language": "en",
    "target_minutes": 1
  }')

EPISODE_ID=$(echo "$RESPONSE" | jq -r '.episode_id')
echo "   Episode ID: $EPISODE_ID"

# 2. Wait for completion
echo "2️⃣ Waiting for script..."
while true; do
  STATE=$(curl -s http://localhost:50000/api/script/state/$EPISODE_ID)
  STATUS=$(echo "$STATE" | jq -r '.data.script_status')
  
  if [ "$STATUS" = "DONE" ]; then
    echo "   ✅ Script ready"
    break
  fi
  
  sleep 2
done

# 3. Generate TTS
echo "3️⃣ Generating audio..."
TTS_RESPONSE=$(curl -s -X POST http://localhost:50000/api/tts/generate \
  -H "Content-Type: application/json" \
  -d "$STATE")

TTS_SUCCESS=$(echo "$TTS_RESPONSE" | jq -r '.success')
if [ "$TTS_SUCCESS" = "true" ]; then
  BLOCKS=$(echo "$TTS_RESPONSE" | jq -r '.generated_blocks')
  echo "   ✅ Audio ready ($BLOCKS blocks)"
else
  echo "   ❌ Audio failed"
  exit 1
fi

# 4. Verify files
echo "4️⃣ Verifying files..."
COUNT=$(ls uploads/Narrator_*.mp3 2>/dev/null | wc -l)
echo "   Found $COUNT MP3 files"

if [ $COUNT -eq $BLOCKS ]; then
  echo "   ✅ All files present"
else
  echo "   ❌ File count mismatch"
  exit 1
fi

echo ""
echo "✅ End-to-End test passed!"
```

---

## 📚 Best Practices

### 1. Async Processing (pro long documents)

```python
from threading import Thread

def generate_tts_async(tts_package, episode_id, callback):
    """Background TTS generation"""
    def worker():
        try:
            result = _generate_tts_audio(tts_package, episode_id)
            callback(success=True, result=result)
        except Exception as e:
            callback(success=False, error=str(e))
    
    thread = Thread(target=worker)
    thread.start()
    return thread
```

### 2. Progress Tracking

```python
# V endpointu přidej WebSocket/SSE pro progress
def generate_tts():
    # ...
    for i, block in enumerate(narration_blocks):
        # Generate block
        # ...
        
        # Emit progress
        progress = {
            'current': i + 1,
            'total': len(narration_blocks),
            'percent': ((i + 1) / len(narration_blocks)) * 100
        }
        emit_progress(episode_id, progress)
```

### 3. Caching (pro development)

```python
# Cache TTS results pro rychlejší iteraci
import hashlib

def get_tts_cache_key(text):
    return hashlib.md5(text.encode()).hexdigest()

def generate_with_cache(text_tts, voice_name):
    cache_key = get_tts_cache_key(f"{text_tts}:{voice_name}")
    cache_path = f"cache/tts_{cache_key}.mp3"
    
    if os.path.exists(cache_path):
        print(f"  ♻️  Cache hit: {cache_key[:8]}")
        return open(cache_path, 'rb').read()
    
    # Generate fresh
    audio_content = synthesize_speech(text_tts)
    
    # Save to cache
    with open(cache_path, 'wb') as f:
        f.write(audio_content)
    
    return audio_content
```

---

## ✅ Checklist před deployment

- [ ] Backend běží stabilně
- [ ] TTS endpoint funguje s test data
- [ ] Video pipeline najde Narrator_*.mp3
- [ ] Error handling je robustní
- [ ] State management ukládá TTS results
- [ ] Frontend/pipeline volá TTS endpoint
- [ ] Logging je srozumitelné
- [ ] Performance je přijatelná (<10s per 10 bloků)
- [ ] End-to-end test projde

---

**Status:** ✅ Integration ready  
**Next:** Implementuj jednu z Option A/B/C podle tvých potřeb

🎉 **Happy integrating!**



