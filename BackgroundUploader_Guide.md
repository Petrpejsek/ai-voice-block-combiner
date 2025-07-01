# 🖼️ Průvodce správou obrázků pozadí

Tato funkcionalita umožňuje nahrávat vlastní obrázky pozadí (např. z Midjourney, DALL-E) a používat je místo waveform vizualizace při generování videí.

## 🎯 Funkce

### ✅ Co umí:
- **Drag & Drop nahrávání** obrázků (PNG, JPG, JPEG)
- **Automatická správa souborů** s timestamp pro jedinečnost
- **Náhled galerie** všech nahraných obrázků
- **Výběr pozadí** pro video generování
- **Bezpečnostní kontroly** - pouze povolené typy souborů

### 🚫 Omezení:
- **Maximální velikost**: 10MB na obrázek
- **Podporované formáty**: PNG, JPG, JPEG
- **Rozlišení**: Doporučeno 1920x1080 nebo 16:9 poměr

## 📁 Struktura souborů

```
podcasts/
├── uploads/
│   └── backgrounds/           # Obrázky pozadí
│       ├── nature_20250627_143022.jpg
│       ├── space_20250627_143045.png
│       └── abstract_20250627_143112.jpg
├── backend/
│   └── app.py                 # 3 nové endpointy
└── frontend/
    └── src/components/
        └── BackgroundUploader.js    # Nová komponenta
```

## 🔌 Backend API Endpointy

### 1. POST `/api/upload-background`
**Nahrává nový obrázek pozadí**

```bash
curl -X POST http://localhost:5000/api/upload-background \
  -F "background_file=@my_image.jpg"
```

**Odpověď:**
```json
{
  "success": true,
  "filename": "my_image_20250627_143022.jpg",
  "original_name": "my_image.jpg", 
  "size": 1024768,
  "url": "/api/backgrounds/my_image_20250627_143022.jpg",
  "message": "Obrázek pozadí byl úspěšně nahrán"
}
```

### 2. GET `/api/list-backgrounds`
**Vrací seznam všech dostupných pozadí**

```bash
curl http://localhost:5000/api/list-backgrounds
```

**Odpověď:**
```json
{
  "backgrounds": [
    {
      "filename": "nature_20250627_143022.jpg",
      "size": 2048576,
      "modified": 1674825022.5,
      "url": "/api/backgrounds/nature_20250627_143022.jpg",
      "thumbnail_url": "/api/backgrounds/nature_20250627_143022.jpg"
    }
  ],
  "count": 1
}
```

### 3. GET `/api/backgrounds/<filename>`
**Servuje obrázek pozadí**

```bash
curl http://localhost:5000/api/backgrounds/nature_20250627_143022.jpg
```

## 🎬 Video generování s pozadím

### Bez pozadí (původní):
```
Audio → Waveform vizualizace → MP4 video
```

### S pozadím (nové):
```
Audio + Obrázek pozadí → Statický obrázek s audiem → MP4 video
```

### FFmpeg příkazy:

**S pozadím:**
```bash
ffmpeg -y -loop 1 -i background.jpg -i audio.mp3 \
  -c:v libx264 -c:a aac -shortest -preset medium \
  -crf 23 -r 30 -pix_fmt yuv420p output.mp4
```

**Titulky s pozadím:**
```bash
ffmpeg -y -i video.mp4 \
  -vf "subtitles=subtitles.srt:force_style='FontSize=32,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=3,Shadow=2'" \
  -c:a copy final_video.mp4
```

## 🎨 Použití ve frontend

### 1. Import komponenty:
```jsx
import BackgroundUploader from './components/BackgroundUploader';
```

### 2. Přidání do aplikace:
```jsx
<BackgroundUploader 
  onBackgroundSelected={handleBackgroundSelected}
/>
```

### 3. Zpracování vybraného pozadí:
```jsx
const handleBackgroundSelected = (background) => {
  setSelectedBackground(background);
  console.log('Vybrané pozadí:', background);
};
```

### 4. Odeslání s formulářem:
```jsx
if (selectedBackground) {
  formData.append('background_filename', selectedBackground.filename);
}
```

## 💡 Tipy pro nejlepší výsledky

### 🖼️ Optimální obrázky:
- **Rozlišení**: 1920x1080 nebo 1280x720
- **Poměr stran**: 16:9 
- **Formát**: JPG pro fotografie, PNG pro grafiku
- **Velikost**: 2-5MB pro nejlepší poměr kvality/rychlosti

### 🎯 Doporučené styly:
- **Jednoduché pozadí** - titulky budou lépe čitelné
- **Tmavší dolní část** - pro bílé titulky
- **Minimální detaily** - aby nerušily text
- **Kontrastní barvy** - pro lepší čitelnost

### 🚀 Workflow:
1. **Vygenerujte obrázky** v Midjourney/DALL-E
2. **Nahrajte do aplikace** přes Drag & Drop
3. **Vyberte pozadí** kliknutím na náhled  
4. **Zpracujte audio** s titulky a videem
5. **Výsledek**: MP4 s vaším pozadím!

## 🔧 Technické detaily

### Bezpečnost:
- **Secure filename** - ochrana proti path traversal
- **Typ souborů** - pouze povolené obrázky
- **Velikost limit** - max 10MB
- **Timestamp names** - prevence kolizí

### Performance:
- **Lazy loading** - obrázky se načítájí postupně  
- **Optimalizace** - FFmpeg s balanced nastavením
- **Background processing** - neblokuje UI

### Error handling:
- **Frontend validation** - kontrola před nahráním
- **Backend validation** - dvojitá kontrola
- **Graceful fallback** - při chybě použije waveform

## ❓ FAQ

**Q: Mohu nahrát více obrázků najednou?**  
A: Ne, nyní pouze jeden po druhém. Drag & Drop více souborů nahraje pouze první.

**Q: Jak smažu nahrané pozadí?**  
A: Momentálně pouze ručně ze složky `uploads/backgrounds/`. Smazání přes UI není implementováno.

**Q: Podporuje animované GIF?**  
A: Ne, pouze statické obrázky PNG, JPG, JPEG.

**Q: Mohu použít vlastní titulky styling?**  
A: Ano, styling titulků je optimalizován pro pozadí (větší font, stín, outline).

---

**📞 Potřebujete pomoc?** Otevřete issue nebo se podívejte do logů backendu pro detailní chybové zprávy. 