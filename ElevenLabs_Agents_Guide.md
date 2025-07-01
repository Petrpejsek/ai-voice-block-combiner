# 🤖 ElevenLabs Agents API - Průvodce

## 📝 Přehled

Váš AI Voice Block Combiner nyní podporuje **ElevenLabs Agents API** pomocí `agent_id` kromě klasického `voice_id`. To vám umožňuje používat pokročilejší AI agenty pro generování hlasů.

## 🆚 Rozdíl mezi Voice ID a Agent ID

| **Voice ID** | **Agent ID** |
|-------------|-------------|
| Klasické text-to-speech | Pokročilí AI agenti |
| `voice_id: "pNInz6obpgD..."` | `agent_id: "agent_01jysn..."` |
| Endpoint: `/v1/text-to-speech/{voice_id}` | Endpoint: `/v1/agents/{agent_id}/stream` |
| Statický hlas | Konverzační režim |

## 📊 Formát JSON

### ✅ Správné použití - Agent ID

```json
{
  "Tesla_1": {
    "text": "Sokratesi, co je to pravda v očích dnešní vědy?",
    "agent_id": "agent_01jysnj4zgfqgsncz1ww8t6eyd"
  },
  "Socrates_1": {
    "text": "Nikolo, pravda není o tom, co víš, ale proč tomu věříš.",
    "agent_id": "agent_01jysp1gvmfe8s696kdhbmgzg8"
  }
}
```

### ✅ Správné použití - Voice ID (zpětná kompatibilita)

```json
{
  "Tesla_1": {
    "text": "Dobrý den, já jsem Nikola Tesla.",
    "voice_id": "pNInz6obpgDQGcFmaJgB"
  },
  "Socrates_1": {
    "text": "Zdravím vás, já jsem Socrates.",
    "voice_id": "ErXwobaYiN019PkySvjV"
  }
}
```

### ✅ Správné použití - Smíšené bloky

```json
{
  "Tesla_1": {
    "text": "Tento blok používá klasický voice_id",
    "voice_id": "pNInz6obpgDQGcFmaJgB"
  },
  "Socrates_1": {
    "text": "Tento blok používá pokročilý agent_id",
    "agent_id": "agent_01jysp1gvmfe8s696kdhbmgzg8"
  }
}
```

### ❌ Chybné použití - Současně oba parametry

```json
{
  "Tesla_1": {
    "text": "Toto je chyba!",
    "voice_id": "pNInz6obpgDQGcFmaJgB",
    "agent_id": "agent_01jysnj4zgfqgsncz1ww8t6eyd"
  }
}
```

**Chybová zpráva:** `"Blok 'Tesla_1': nesmí obsahovat současně voice_id a agent_id"`

## 🔧 Technické detaily

### Agent API parametry
- **URL:** `https://api.elevenlabs.io/v1/agents/{agent_id}/stream`
- **Method:** POST
- **Headers:** 
  - `xi-api-key: YOUR_API_KEY`
  - `Content-Type: application/json`
- **Body:**
  ```json
  {
    "text": "...",
    "mode": "conversation"
  }
  ```

### Výstup
- Stejný jako u voice_id: MP3 soubory s názvy podle JSON klíčů
- Příklad: `Tesla_1.mp3`, `Socrates_1.mp3`

## 🎯 Použití v aplikaci

1. **Otevřete VoiceGenerator komponentu**
2. **Vložte JSON** s `agent_id` místo `voice_id`
3. **Zadejte ElevenLabs API klíč**
4. **Klikněte "Generate Voices"**
5. **Hlasy se vygenerují** pomocí Agents API

## 🔒 Validace

Systém automaticky kontroluje:
- ✅ Každý blok má buď `voice_id` NEBO `agent_id`
- ❌ Blok nesmí mít současně oba parametry
- ✅ Text je vždy povinný
- ✅ API klíč je vždy povinný

## 🔄 Zpětná kompatibilita

- **Stávající JSON s `voice_id` funguje** bez změn
- **Nové JSON s `agent_id` používá** Agents API
- **UI se nezmění** - vše funguje transparentně
- **Můžete kombinovat** oba typy v jednom JSON

## 🚀 Výhody Agent ID

1. **Pokročilejší konverzace** - agenti jsou trénováni pro specifické role
2. **Lepší kontextové pochopení** - režim "conversation"
3. **Přirozenější projev** - agenti reagují kontextově na text
4. **Flexibilnější nastavení** - možnost konfigurace agenta v ElevenLabs rozhraní

---

**💡 Tip:** Agent ID získáte v ElevenLabs dashboard v sekci "Agents" - každý agent má unikátní identifikátor začínající `agent_`. 