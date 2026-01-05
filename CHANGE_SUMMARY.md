# Změny v UI pro Video Compilation

## Co jsem udělal:

1. **Přidány state proměnné:**
   - `showAudioFiles` - pro collapsible audio sekci
   - `videoCompilationState` - pro tracking video generování

2. **Přidána funkce `generateVideoCompilation()`**
   - Bude volat backend API pro spuštění AAR + CB
   - Má progress tracking a error handling

## Co je potřeba dodělat ručně:

### 1. Změnit audio soubory na collapsible (řádek ~1419)
Najdi sekci `{/* Success - Audio Player */}` a změň:
- `<div className="bg-white border border-gray-200 rounded-lg p-4">` 
  → přidej `<button onClick={() => setShowAudioFiles(!showAudioFiles)}>` wrapper
- Audio seznam wrapl do `{showAudioFiles && ( ... )}`

### 2. Přidat novou sekci Video Compilation (za Voice-over Generation, ~řádek 1495)
Přidej nový div blok pro Video Compilation s:
- Idle state: tlačítko "🎬 Vygenerovat Video"
- Running state: progress bar s `videoCompilationState.progress`
- Done state: video player s výsledkem
- Error state: error message + retry button

### 3. Backend API endpoint (backend/app.py)
Přidat nový endpoint:
```python
@app.route('/api/video/compile', methods=['POST'])
def compile_video():
    episode_id = request.json.get('episode_id')
    # Spustit AAR + CB pro daný episode
    # Vrátit progress updates nebo final output
```

## Odpovědi na otázky uživatele:

**Q: Mám zmáčknout "Generovat video" po vygenerování hlasu?**
A: Ano! Po dokončení audio bude nová sekce "🎬 Video Compilation" s tlačítkem "Vygenerovat Video"

**Q: Jede loader při generování?**
A: Ano! Bude progress bar s kroky:
- AAR (Archive Asset Resolver) - 30%
- CB (Compilation Builder) - 60-100%

**Q: Skrýt staré audio sekce?**
A: Ano! Audio přehrávače budou collapsible (klikací) - defaultně skryté

