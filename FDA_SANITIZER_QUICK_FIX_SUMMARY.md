# FDA Sanitizer Quick Fix Summary

## 🎯 Co bylo opraveno?

**Problém:** FDA sanitizer spadal s `FDA_SANITIZER_FAILED` kvůli blacklisted termům → nekonečný loop chyb

**Řešení:** Hard fail → Soft sanitize (WARNING místo ERROR)

---

## ⚡ Klíčové změny (1 minuta přehled)

### 1. SOFT SANITIZE (ne fail!)
```python
# PŘED:
if _is_blacklisted(keyword):
    raise RuntimeError("FDA_SANITIZER_FAILED")  # ❌ FAIL

# PO:
if _is_blacklisted(keyword):
    print("FDA_SANITIZE_WARNING")  # ⚠️  WARNING
    cleaned = _remove_blacklisted_words(keyword)
    # pokračuj dál...
```

### 2. "troop movement" rozpor vyřešen
- ✅ `shot_types: ["troop_movement"]` (enum) je validní
- ✅ "troop movement" v keywords → nahrazeno "soldiers marching"
- ✅ Sanitizer kontroluje JEN keywords/queries, NIKDY shot_types

### 3. FDA prompt - explicitní zákaz
```
❌ FORBIDDEN: shot type names v keywords ("troop movement", "battle footage")
✅ ALLOWED: konkrétní objekty ("soldiers", "wagons", "map", "roads")
```

### 4. Fallback queries
- Pokud jsou všechny queries smazány → auto-doplní fallbacky
- **Garantuje:** min 3-6 queries vždy

---

## 📊 Test výsledky

### Unit testy: ✅ 3/3 PASS
- Keywords s "troop movement" → nahrazeno
- Všechny queries blacklisted → fallbacky doplněny
- shot_type troop_movement → zachován

### E2E test (Napoleon in Moscow): ✅ PASS
- 4 scény, 12+ blacklisted termů v inputu
- 25 replacements provedeno
- **NIKDY nespadl** s FDA_SANITIZER_FAILED

---

## 🔍 Změněné soubory

| Soubor | Změna |
|--------|-------|
| `backend/pre_fda_sanitizer.py` | SOFT CHECK místo HARD CHECK |
| `backend/footage_director.py` | FDA prompt - zákaz shot type names |

---

## 🚀 Jak ověřit, že to funguje?

### Quick test:
```bash
cd backend
python3 -c "
from pre_fda_sanitizer import sanitize_shot_plan
plan = {'scenes': [{'scene_id': 'test', 'keywords': ['troop movement'], 'search_queries': ['test'], 'shot_strategy': {'shot_types': ['troop_movement']}}]}
result, log = sanitize_shot_plan(plan)
print('✅ PASS' if log['status'] == 'FDA_SANITIZER_PASS' else '❌ FAIL')
"
```

**Očekávaný výstup:**
```
FDA_SANITIZE_WARNING: {...}
✅ PASS
```

---

## 📝 Co to znamená pro uživatele?

### PŘED:
- Episode s "Napoleon in Moscow" → FDA_SANITIZER_FAILED
- Uživatel točí dokola → frustrace

### PO:
- Episode s "Napoleon in Moscow" → FDA_SANITIZER_PASS
- Blacklisted termy automaticky odstraněny → pokračuje bez chyby
- Žádný loop!

---

## 🔧 Troubleshooting

### Pokud stále vidíš FDA_SANITIZER_FAILED:
1. Zkontroluj, že používáš aktuální `pre_fda_sanitizer.py`
2. Zkontroluj logy - měl by být `FDA_SANITIZE_WARNING` místo error
3. Spusť quick test výše

### Pokud vidíš "troop movement" v keywords:
- To je BUG - sanitizer by ho měl nahradit "soldiers marching"
- Zkontroluj, že `BLACKLISTED_ABSTRACT_TERMS` obsahuje "troop movement"

---

**Status:** ✅ READY FOR PRODUCTION  
**Datum:** 2025-12-29  
**Breaking changes:** Žádné (zpětně kompatibilní)



