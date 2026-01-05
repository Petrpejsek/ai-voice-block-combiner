# FDA v2.7 Golden Contract Tests

## 📋 Přehled

Tento testovací modul (`test_fda_golden_contracts.py`) obsahuje **golden contract tests** pro FDA v2.7, které ověřují klíčové kontrakty validátoru a generátorů.

## 🎯 Testované Kontrakty

### TEST A: Object-Type Overlap Detection

**Účel:** Ověřit, že validátor správně detekuje multi-word object types jako JEDEN typ, ne více.

**Test Cases:**
1. **City Map:** `"Moscow 1812 historical city map"` → 1 object type (ne "map" + "city map")
2. **Burned Ruins:** `"Moscow 1812 burned ruins"` → 1 object type (ne "ruins" + "burned ruins")
3. **Route Map:** `"Napoleon 1812 route map retreat"` → 1 object type (ne "map" + "route map")

**Implementace:**
- Funkce `_count_object_types` matchuje multi-word typy PŘED single-word typy
- Používá overlap detection pro prevenci duplicit
- Sortuje podle `(len(x.split()), len(x))` pro správné pořadí

### TEST B: Generator No Double Object Types

**Účel:** Ověřit, že generátor `_generate_deterministic_queries_v27` NIKDY nevytvoří query se 2 object types.

**Test Cases:**
- Leaders scene: Napoleon, Tsar, commanders
- Fire/ruins scene: fires, destruction, burned ruins
- Waiting/negotiation: diplomatic letters, dispatches
- Movement: retreat, route maps
- Generic: mixed content

**Očekávání:**
- Všech 5 queries pro každý scene type má EXACTLY 1 object type
- Žádné queries jako `"Moscow 1812 burned ruins historical engraving"` (2 typy!)

**Oprava:**
```python
# ❌ ŠPATNĚ (2 object types)
queries.append(f"Moscow 1812 burned ruins historical engraving")

# ✅ SPRÁVNĚ (1 object type)
queries.append(f"Moscow 1812 burned ruins view historical")
```

### TEST C: Salvage Broken LLM Output

**Účel:** Ověřit, že pipeline dokáže opravit broken LLM output pomocí deterministických generátorů.

**Input (broken):**
```json
{
  "narration_summary": "These events unfolded in Moscow",  // ❌ Starts with "These"
  "keywords": ["the Moscow", "a city", "these events"],    // ❌ Forbidden tokens
  "shot_strategy": {
    "source_preference": "archive_org"                     // ❌ String instead of array
  },
  "search_queries": [
    "These Moscow events 1812",                            // ❌ Starts with "These"
    "The city of Moscow 1812",                             // ❌ Starts with "The"
    "Moscow fires"                                         // ❌ No object type
  ]
}
```

**Expected Output (after `apply_deterministic_generators_v27`):**
```json
{
  "narration_summary": "Napoleon entered Moscow in 1812 after...",  // ✅ Clean
  "keywords": ["Napoleon military map", "Moscow historical document", ...],  // ✅ No forbidden tokens
  "shot_strategy": {
    "source_preference": ["archive_org"]                            // ✅ Array
  },
  "search_queries": [
    "Moscow 1812 historical city map",                              // ✅ Clean + 1 object type
    "Moscow city 1812 period engraving",                            // ✅ Clean + 1 object type
    ...
  ]
}
```

**Validace:**
- `validate_fda_hard_v27` projde bez errors
- Všechny keywords bez forbidden tokens
- Všechny queries začínají správně (ne These/The/A/An)
- Všechny queries mají exactly 1 object type

## 🚀 Spuštění Testů

```bash
cd backend
python3 test_fda_golden_contracts.py
```

**Očekávaný výstup:**
```
======================================================================
FDA v2.7 GOLDEN CONTRACT TESTS
======================================================================

✅ TEST A: City Map Overlap: PASSED
✅ TEST A (variant): Burned Ruins Overlap: PASSED
✅ TEST A (variant): Route Map Overlap: PASSED
✅ TEST B: Generator No Double Object Types: PASSED
✅ TEST C: Salvage Broken LLM Output: PASSED

======================================================================
Total: 5 | Passed: 5 | Failed: 0 | Errors: 0
======================================================================

🎉 ALL TESTS PASSED!
```

## 🔧 Integrace s CI/CD

### Pytest

Testy jsou kompatibilní s pytest:

```bash
pytest test_fda_golden_contracts.py -v
```

### Pre-commit Hook

Přidej do `.git/hooks/pre-commit`:

```bash
#!/bin/bash
cd backend
python3 test_fda_golden_contracts.py
if [ $? -ne 0 ]; then
    echo "❌ FDA golden contract tests failed!"
    exit 1
fi
```

## 📊 Coverage

Testy pokrývají:
- ✅ Object-type overlap detection (`_count_object_types`)
- ✅ Query generator (`_generate_deterministic_queries_v27`)
- ✅ Keyword generator (`_generate_deterministic_keywords_v27`)
- ✅ Summary generator (`_generate_deterministic_summary_v27`)
- ✅ Shot strategy fixer (`_fix_shot_strategy_v27`)
- ✅ Hard validator (`validate_fda_hard_v27`)
- ✅ Full pipeline (`apply_deterministic_generators_v27`)

## 🐛 Debugging

Pokud test failne, zkontroluj:

1. **TEST A fail:** `_count_object_types` nesprávně matchuje overlapping types
   - Zkontroluj sorting: `sorted(object_types, key=lambda x: (len(x.split()), len(x)), reverse=True)`
   - Zkontroluj overlap detection logic

2. **TEST B fail:** Generátor vytváří query se 2 object types
   - Zkontroluj hardcoded queries v `_generate_deterministic_queries_v27`
   - Ujisti se, že žádná query neobsahuje 2 object types (např. "burned ruins engraving")

3. **TEST C fail:** Pipeline nesprávně opravuje broken output
   - Zkontroluj `apply_deterministic_generators_v27` - volá všechny generátory?
   - Zkontroluj `_fix_shot_strategy_v27` - opravuje `source_preference` na array?

## 📝 Přidání Nových Testů

```python
def test_d_new_contract():
    """
    TEST D: Popis nového kontraktu
    """
    print("\n" + "="*70)
    print("TEST D: New Contract")
    print("="*70)
    
    # Test logic here
    
    assert condition, "Error message"
    
    print("✅ TEST D PASSED")
    return True

# Přidej do run_all_tests():
tests = [
    # ... existing tests ...
    ("TEST D: New Contract", test_d_new_contract),
]
```

## 🔒 Kritická Pravidla

1. **Multi-word types FIRST:** Vždy matchuj "city map" před "map"
2. **ONE object type per query:** Nikdy 2+ object types v jednom query
3. **No overlap:** Pokud "city map" matchne, "map" už nesmí matchnout
4. **Deterministic:** Všechny generátory musí být deterministické (no random, no LLM)

## 📚 Reference

- **Spec:** FDA v2.7 Hardening Spec (user query)
- **Implementation:** `backend/footage_director.py`
- **Object Types:** `FDA_V27_QUERY_OBJECT_TYPES` (lines 2853-2871)
- **Validators:** `validate_fda_hard_v27` (lines 3000+)

---

**Last Updated:** December 2024  
**Maintainer:** FDA Pipeline Team  
**Status:** ✅ All tests passing



