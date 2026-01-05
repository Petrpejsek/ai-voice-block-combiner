import os
import json
import requests
from dotenv import load_dotenv

# Načte environment variables z .env souboru
# Farm-proof: pokud .env není dostupný (např. sandbox/permissions), backend nesmí spadnout.
try:
    load_dotenv()
except Exception as e:
    print(f"⚠️  gpt_utils: load_dotenv skipped: {e}")

def call_openai(prompt: str, model: str = "gpt-4o") -> dict:
    """
    Volá OpenAI API pro generování textu a vrátí odpověď jako JSON
    
    Args:
        prompt (str): Text promptu pro GPT model
        model (str): Název modelu (výchozí: gpt-4o)
    
    Returns:
        dict: Odpověď z OpenAI API nebo chybová zpráva
    """
    try:
        # Získá API klíč z environment proměnných
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return {"error": "OpenAI API klíč není nastaven v .env souboru"}
        
        # OpenAI API endpoint
        url = "https://api.openai.com/v1/chat/completions"
        
        # Headers pro API request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Data pro OpenAI API
        data = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional documentary writer. Always return valid JSON in the requested format."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "temperature": 0.7,  # Kreativita modelu
            "max_tokens": 4000,  # Maximum tokenů pro odpověď
            "response_format": {"type": "json_object"}  # Vynucuje JSON odpověď
        }
        
        print(f"🤖 Volám OpenAI API s modelem: {model}")
        print(f"📝 Prompt délka: {len(prompt)} znaků")
        
        # Volání OpenAI API s timeoutem
        response = requests.post(url, json=data, headers=headers, timeout=60)
        
        if response.status_code == 200:
            # Parsuje odpověď
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Pokusí se parsovat obsah jako JSON
            try:
                narration_json = json.loads(content)
                print(f"✅ OpenAI úspěšně vygeneroval naraci")
                print(f"📊 Počet bloků: {len(narration_json)}")
                return {"success": True, "data": narration_json}
            except json.JSONDecodeError as e:
                print(f"❌ Chyba při parsování JSON odpovědi: {e}")
                return {"error": f"Nepodařilo se parsovat JSON odpověď: {e}", "raw_content": content}
                
        else:
            error_msg = f"OpenAI API chyba: {response.status_code} - {response.text}"
            print(f"❌ {error_msg}")
            return {"error": error_msg}
            
    except requests.exceptions.Timeout:
        error_msg = "Časový limit OpenAI API volání byl překročen"
        print(f"❌ {error_msg}")
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Neočekávaná chyba při volání OpenAI: {str(e)}"
        print(f"❌ {error_msg}")
        return {"error": error_msg}


def create_narration_prompt(topic: str, style: str = "Cinematic, BBC-style, serious tone") -> str:
    """
    Vytvoří prompt pro generování dokumentární narrace
    
    Args:
        topic (str): Téma dokumentu
        style (str): Styl dokumentu
    
    Returns:
        str: Připravený prompt pro OpenAI
    """
    prompt = f"""You are a historical documentary writer. Your goal is to create a 20-minute single-narrator documentary for YouTube narration.

Output must be a flat JSON in this exact format:
{{
  "Narrator_01": {{"voice_id": "YOUR_VOICE_ID", "text": "First narration block..."}},
  "Narrator_02": {{"voice_id": "YOUR_VOICE_ID", "text": "Second narration block..."}},
  ...
  "Narrator_40": {{"voice_id": "YOUR_VOICE_ID", "text": "Final narration block..."}}
}}

IMPORTANT REQUIREMENTS:
- Exactly 40 blocks (Narrator_01 to Narrator_40)
- Each block: 2-4 sentences, approximately 150-200 words
- Tone: {style}
- Narrative must feel like one flowing voiceover, not chaptered
- Use dramatic pauses and emotional language
- Include historical facts and engaging storytelling
- Make it suitable for YouTube audience
- Write in English language

End the last block (Narrator_40) with:
"This documentary is fictional and generated using AI. It is intended for entertainment and educational purposes only."

Topic: {topic}

Create an engaging, cinematic documentary script about this topic."""

    return prompt 


def generate_dalle_images(prompt: str, n: int = 1, size: str = "1792x1024", model: str = "dall-e-3") -> dict:
    """
    Generuje obrázky pomocí DALL-E 3 API
    
    Args:
        prompt (str): Popis obrázku pro DALL-E
        n (int): Počet obrázků (DALL-E 3 podporuje pouze 1)
        size (str): Velikost obrázku (1024x1024, 1792x1024, 1024x1792)
        model (str): Model (dall-e-3 nebo dall-e-2)
    
    Returns:
        dict: Odpověď s URL obrázků nebo chybová zpráva
    """
    try:
        # Získá API klíč z environment proměnných
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return {"error": "OpenAI API klíč není nastaven v .env souboru"}
        
        print(f"🎨 Generuji obrázek pomocí DALL-E: {prompt[:50]}...")
        
        # DALL-E API endpoint
        url = "https://api.openai.com/v1/images/generations"
        
        # Headers pro API request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Data pro DALL-E API
        data = {
            "model": model,
            "prompt": prompt,
            "n": 1 if model == "dall-e-3" else min(n, 10),  # DALL-E 3 podporuje pouze 1 obrázek
            "size": size,
            "quality": "hd" if model == "dall-e-3" else "standard",
            "response_format": "url"
        }
        
        # Volání OpenAI API
        print(f"🔄 Odesílám požadavek na DALL-E API...")
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            images = result.get('data', [])
            print(f"✅ DALL-E úspěšně vygeneroval {len(images)} obrázků")
            
            return {
                "success": True,
                "images": images,
                "prompt": prompt,
                "model": model,
                "size": size
            }
        else:
            error_msg = f"DALL-E API chyba {response.status_code}: {response.text}"
            print(f"❌ {error_msg}")
            return {"error": error_msg}
            
    except requests.exceptions.Timeout:
        error_msg = "Časový limit DALL-E API volání byl překročen"
        print(f"❌ {error_msg}")
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Neočekávaná chyba při volání DALL-E: {str(e)}"
        print(f"❌ {error_msg}")
        return {"error": error_msg}


def download_image_from_url(image_url: str, filename: str, folder_path: str) -> dict:
    """
    Stáhne obrázek z URL a uloží ho do složky
    
    Args:
        image_url (str): URL obrázku
        filename (str): Název souboru
        folder_path (str): Cesta ke složce
    
    Returns:
        dict: Informace o úspěchu stažení
    """
    try:
        print(f"⬇️ Stahuji obrázek: {filename}")
        
        # Stáhni obrázek
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # Vytvoř složku pokud neexistuje
        os.makedirs(folder_path, exist_ok=True)
        
        # Ulož obrázek
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        file_size = len(response.content)
        print(f"✅ Obrázek uložen: {file_path} ({file_size} bytes)")
        
        return {
            "success": True,
            "file_path": file_path,
            "file_size": file_size,
            "filename": filename
        }
        
    except Exception as e:
        error_msg = f"Chyba při stahování obrázku: {str(e)}"
        print(f"❌ {error_msg}")
        return {"error": error_msg} 