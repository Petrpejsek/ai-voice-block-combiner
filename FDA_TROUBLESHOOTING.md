# 🔧 FDA se nespustil - Troubleshooting & Řešení

## Problém
FDA se "vůbec nespustil" na existujícím projektu.

## Diagnostika ✅

```bash
cd /Users/petrliesner/podcasts/backend
python3 -c "
import json
from project_store import ProjectStore
store = ProjectStore('../projects')
state = store.read_script_state('ep_f6b36e77ffb7')
print('Steps:', list(state.get('steps', {}).keys()))
print('Has footage_director:', 'footage_director' in state.get('steps', {}))
print('Has shot_plan:', state.get('shot_plan') is not None)
"
```

**Výsledek:**
- ❌ `footage_director` **chybí** v `steps`
- ❌ `shot_plan` **je None**

## Příčina

Projekt byl vytvořen **před přidáním FDA** (před restartem backendu). Starý backend nevěděl o FDA kroku, takže:
1. Vytvořil projekt pouze s 5 kroky (research → tts_format)
2. Nikdy nespustil FDA (protože o něm nevěděl)
3. State nemá `footage_director` step ani `shot_plan`

---

## ✅ Řešení 1: Retroaktivní spuštění FDA (pro staré projekty)

### Použij helper script

```bash
cd /Users/petrliesner/podcasts/backend
python3 run_fda_on_project.py ep_f6b36e77ffb7
```

**Výstup:**
```
🎬 Spouštím FDA na projektu: ep_f6b36e77ffb7
✅ tts_ready_package nalezen
🔧 Přidávám footage_director step do state...
🎬 Spouštím FDA...
✅ FDA dokončen úspěšně!

📊 Výsledek:
   Scén: 3
   Celková délka: 95s
   
🎉 Hotovo! Projekt nyní má shot_plan a můžeš ho vidět v UI.
```

### Co script dělá

1. Načte `script_state.json`
2. Zkontroluje že existuje `tts_ready_package`
3. Přidá `footage_director` step do `steps`
4. Spustí FDA a vygeneruje `shot_plan`
5. Uloží zpět do `script_state.json`

### Po spuštění

✅ Projekt má `footage_director` step  
✅ Projekt má `shot_plan` (3 scény, 95s)  
✅ V UI uvidíš "Footage Director… ✅ DONE"  

---

## ✅ Řešení 2: Vytvoř nový projekt (doporučeno)

Pro čisté testování vytvořte **nový projekt** s restartnutým backendem:

```bash
# 1. Restart backend (s novým kódem)
cd /Users/petrliesner/podcasts/backend
python3 app.py

# 2. Vytvoř nový projekt přes API
curl -X POST http://localhost:50000/api/script/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "test fda flow",
    "language": "en",
    "target_minutes": 2,
    "openai_api_key": "sk-..."
  }'
```

**Nový projekt automaticky:**
1. ✅ Má `footage_director` step v `steps`
2. ✅ Spustí FDA automaticky po TTS Formatting
3. ✅ Vytvoří `shot_plan`

---

## 🔍 Jak ověřit že FDA běží

### Check 1: Backend má nový kód

```bash
cd /Users/petrliesner/podcasts/backend
python3 -c "from footage_director import run_fda; print('✅ FDA modul načten')"
```

### Check 2: Projekt má footage_director step

```bash
cd /Users/petrliesner/podcasts
cat projects/<episode_id>/script_state.json | \
  python3 -c "import sys, json; s=json.load(sys.stdin); print('footage_director' in s.get('steps', {}))"
```

**Očekáváno:** `True`

### Check 3: Projekt má shot_plan

```bash
cat projects/<episode_id>/script_state.json | \
  python3 -c "import sys, json; s=json.load(sys.stdin); sp=s.get('shot_plan'); print('Has shot_plan:', sp is not None); print('Scenes:', sp.get('total_scenes') if sp else 'N/A')"
```

**Očekáváno:**
```
Has shot_plan: True
Scenes: 3
```

---

## 📊 Batch zpracování (pro více starých projektů)

Pokud máš více starých projektů, zpracuj je najednou:

```bash
cd /Users/petrliesner/podcasts/backend

# Najdi všechny projekty s tts_ready_package ale bez shot_plan
python3 << 'EOF'
import os, json
from project_store import ProjectStore

store = ProjectStore('../projects')
projects_dir = '../projects'

for ep_dir in os.listdir(projects_dir):
    if not ep_dir.startswith('ep_'):
        continue
    
    try:
        state = store.read_script_state(ep_dir)
        has_tts = state.get('tts_ready_package') is not None
        has_fda = state.get('shot_plan') is not None
        
        if has_tts and not has_fda:
            print(f"✅ {ep_dir} - má TTS, nemá FDA (spustitelné)")
        elif has_tts and has_fda:
            print(f"⏭️  {ep_dir} - má TTS i FDA (hotovo)")
        else:
            print(f"⚠️  {ep_dir} - nemá TTS (nelze spustit FDA)")
    except:
        pass
EOF
```

Pak spusť na každý projekt:
```bash
python3 run_fda_on_project.py ep_xxx
python3 run_fda_on_project.py ep_yyy
# atd.
```

---

## 🎯 Shrnutí

### Problém
- Starý projekt (vytvořen před FDA) → chybí `footage_director` step → FDA se nespustil

### Řešení
- **Rychlé:** `python3 run_fda_on_project.py <episode_id>`
- **Čisté:** Vytvořit nový projekt s restartnutým backendem

### Výsledek
- ✅ Projekt má `shot_plan` s 3 scénami (95s)
- ✅ V UI vidíš "Footage Director… ✅ DONE"
- ✅ Můžeš kliknout na "Raw output" a vidět celý `shot_plan` JSON

---

## 🔮 Do budoucna (prevence)

Pro **nové projekty** (po restartu backendu) se FDA spustí **automaticky**:

```
Pipeline flow (nový backend):
1. Research          ✅
2. Narrative         ✅
3. Validation        ✅
4. Composer          ✅
5. TTS Formatting    ✅
6. Footage Director  ✅ ← automaticky!
```

**Žádné ruční spouštění není potřeba!** 🎉



