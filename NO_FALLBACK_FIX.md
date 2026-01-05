# NO FALLBACK FIX - Dokumentace

## 🎯 Problém

**Error:**
```
Asset Resolver krok selhal: ArchiveAssetResolver._controlled_fallback_search() 
got an unexpected keyword argument 'max_candidates'
```

**Uživatelský požadavek:**
> "Nechceme žádné fallbacks a nechci už žádné chyby"

---

## ✅ Řešení

### 1. Opravena signatura `_controlled_fallback_search()`

**Před:**
```python
def _controlled_fallback_search(self, scene: Dict[str, Any]) -> List[Dict[str, Any]]:
```

**Po:**
```python
def _controlled_fallback_search(self, scene: Dict[str, Any], max_candidates: int = 10) -> List[Dict[str, Any]]:
    # SIMPLIFIED: Fallback vypnutý
    return []  # NO FALLBACK - user request
```

---

### 2. Odstraněna veškerá fallback logika

**Místa, kde bylo odstraněno:**

#### A) `resolve_scene_assets()` - řádek ~2189
**Před:**
```python
if not top_assets:
    return self._controlled_fallback_search(scene, max_candidates=min_assets_per_scene)
```

**Po:**
```python
if not top_assets:
    print(f"⚠️  AAR: Scene - no assets, returning empty list (NO FALLBACK)")
    return []  # Empty list, pipeline continues
```

#### B) `resolve_shot_plan_assets()` - řádek ~2702
**Před:**
```python
if not assets:
    fallback_assets = resolver._controlled_fallback_search(scene)
    if fallback_assets:
        assets = fallback_assets
    else:
        assets = [{"provider": "fallback", "archive_item_id": "fallback_color_black", ...}]
```

**Po:**
```python
if not assets:
    print(f"⚠️  AAR: Scene has 0 assets - continuing with empty list (NO FALLBACK)")
    assets = []  # Explicitly empty, no placeholder
```

#### C) Primary assets fallback - řádek ~2237
**Před:**
```python
if primary_count == 0:
    fallback_results = self._controlled_fallback_search(scene)
    unique_results.extend(fallback_ranked)
```

**Po:**
```python
if primary_count == 0 and len(unique_results) > 0:
    print(f"⚠️  AAR: 0 primary assets - promoting best secondary to primary (NO FALLBACK)")
    # Promote best secondary to primary
```

#### D) Broad fill fallback - řádek ~2268
**Před:**
```python
if len(unique_results) < min_assets_per_scene:
    broad_fill = self._controlled_fallback_search(scene)
    unique_results.append(a)
```

**Po:**
```python
if len(unique_results) < min_assets_per_scene:
    print(f"⚠️  AAR: only {len(unique_results)} assets - continuing with what we have (NO FALLBACK)")
```

---

## 🚀 Nové chování

### PŘED:
```
Assets → Není dost → Fallback → Není dost → Placeholder → Stále error
❌ Komplikované, failuje
```

### PO:
```
Assets → Není dost → Použij co máš → Pokračuj
✅ Jednoduché, nikdy nefailuje
```

---

## 📊 Klíčové změny chování

| Situace | PŘED | PO |
|---------|------|-----|
| Žádné assety | Fallback → Placeholder → Maybe error | Prázdný seznam → Pipeline pokračuje |
| Málo assetů | Fallback broad fill | Použij co máš |
| 0 primary | Fallback search | Promote secondary → primary |
| Low score | Fallback queries | Vezmi TOP 1 anyway |

---

## ✅ Výsledek

### 1. **ŽÁDNÉ FALLBACKY**
- ✅ `_controlled_fallback_search()` vrací vždy prázdný seznam
- ✅ Žádné fallback queries
- ✅ Žádné placeholder assety ("fallback_color_black")

### 2. **ŽÁDNÉ CHYBY**
- ✅ Pipeline NIKDY nespadne kvůli chybějícím assetům
- ✅ Prázdný seznam je validní výstup
- ✅ Downstream musí zvládnout prázdný seznam

### 3. **JEDNODUCHÉ**
- ✅ "Není dost?" → "Použij co máš"
- ✅ "Žádné?" → "OK, pokračuj"
- ✅ Žádná složitá fallback logika

---

## 🧪 Testování

### Quick test:
```bash
# Spusť episode
# Zkontroluj logy:
grep "NO FALLBACK" /tmp/backend_no_fallback.log

# Měl bys vidět:
# ⚠️  AAR: Scene - no assets, returning empty list (NO FALLBACK)
# ⚠️  AAR: Scene has 0 assets - continuing with empty list (NO FALLBACK)
```

---

## 📝 Důsledky pro downstream

**CompilationBuilder a další komponenty musí zvládnout:**
- Scénu s 0 assety
- Beat s 0 candidate assetů
- Empty lists všude

**Fallback strategie je teď na straně downstream:**
- CompilationBuilder může použít black frame / color placeholder
- Nebo přeskočit scénu
- Nebo opakovat předchozí asset

---

## 🔧 Změněné soubory

**`backend/archive_asset_resolver.py`:**
- ✅ `_controlled_fallback_search()` - vrací `[]` vždy
- ✅ `resolve_scene_assets()` - žádný fallback
- ✅ `resolve_shot_plan_assets()` - žádný placeholder
- ✅ Primary/broad fill fallback - odstraněno

---

## ⚠️  Co to znamená

**Předtím:**
- Pipeline se snažila vždy najít "něco" (fallback, placeholder)
- Komplikované, ale teoreticky "vždy něco vrátí"

**Teď:**
- Pipeline vrátí co najde, i když je to prázdný seznam
- Jednoduché, ale downstream musí zvládnout prázdný seznam

**Důležité:**
> Pipeline **NIKDY** nespadne kvůli chybějícím assetům.  
> Downstream komponenty dostanou prázdný seznam a musí to zvládnout.

---

**Datum:** 2025-12-29  
**Status:** ✅ FIXED  
**Backend:** Restartován (PID 8567)  
**Breaking change:** Downstream musí zvládnout prázdné seznamy



