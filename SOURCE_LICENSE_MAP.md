# Video Sources & License Audit Map

**Datum:** 3. ledna 2025  
**Účel:** Kompletní přehled všech zdrojů médií a validace licencí  
**Compliance:** YouTube monetization-safe (Public Domain / CC-BY / CC-BY-SA only)

---

## Přehled Zdrojů

| Zdroj | Typ Licence | API/Scraping | Metadata Tracking | Licence Check Místo | Fail Behavior |
|-------|-------------|--------------|-------------------|---------------------|---------------|
| **Archive.org** | PD / CC-BY / CC-BY-SA / Unknown | API (JSON) | ✅ Full | AAR: `_normalize_license()` | Skip unsafe, optional unknown fallback |
| **Wikimedia Commons** | PD / CC-BY / CC-BY-SA | API (MediaWiki) | ✅ Full | AAR: `_normalize_license()` | Skip unsafe (hard gate) |
| **Europeana** | PD / CC-BY / CC-BY-SA | API (REST) | ✅ Full | AAR: `_normalize_license()` | Skip unsafe (hard gate) |
| **Pexels** | Pexels License | API (REST) | ✅ Full | AAR: hardcoded "pexels" | Requires API key (opt-in) |
| **Pixabay** | Pixabay License | API (REST) | ✅ Full | AAR: hardcoded "pixabay" | Requires API key (opt-in) |
| **Local Safety Pack** | Public Domain | Local Files | ✅ Full | CB: hardcoded "local_safety_pack" | Always available (repo fallback) |

---

## Detailní Audit per Zdroj

### 1. Archive.org (movies/movingimage + image + texts)

**Typ:** Public Domain / Creative Commons  
**URL:** `https://archive.org/`  
**API Endpoint:** `https://archive.org/advancedsearch.php`

#### Jak se získává metadata

- **Search API:**
  ```python
  params = {
      "q": "(query) AND mediatype:(movies OR movingimage)",
      "fl[]": ["identifier", "title", "description", "licenseurl", "downloads", "date"],
      "rows": 50,
      "output": "json"
  }
  response = requests.get("https://archive.org/advancedsearch.php", params=params)
  ```

- **Metadata API (per-item):**
  ```python
  url = f"https://archive.org/metadata/{item_id}"
  response = requests.get(url)
  # Returns: files[], duration, format, size, license
  ```

#### Co se ukládá

| Field | Type | Storage Location | Example Value |
|-------|------|------------------|---------------|
| `archive_item_id` | string | `archive_manifest.json` → `episode_pool.videos[].archive_item_id` | `"prelinger-video-1234"` |
| `source_url` | string | `episode_pool.videos[].url` | `"https://archive.org/details/prelinger-video-1234"` |
| `asset_url` | string | `episode_pool.videos[].asset_url` | `"https://archive.org/download/prelinger-video-1234/prelinger-video-1234.mp4"` |
| `license` | string | `episode_pool.videos[].license` | `"public_domain"` |
| `license_raw` | string | `episode_pool.videos[].license_raw` | `"http://creativecommons.org/publicdomain/mark/1.0/"` |
| `attribution` | string? | `episode_pool.videos[].attribution` | `null` (usually PD, no attribution required) |
| `thumbnail_url` | string | `episode_pool.videos[].thumbnail_url` | `"https://archive.org/services/img/prelinger-video-1234"` |
| `retrieved_at` | ISO timestamp | `episode_pool.search_completed_at` | `"2025-01-03T14:22:11Z"` |
| `downloads` | int | `episode_pool.videos[].downloads` | `45123` (popularity proxy) |
| `duration_sec` | float? | `episode_pool.videos[].duration_sec` | `180.5` (fetched from metadata API) |

#### Kde probíhá licence check

**Modul:** `backend/video_sources.py` → `ArchiveOrgSource._normalize_license()`  
**Řádek:** ~278-296

```python
def _normalize_license(self, license_url: str) -> str:
    if not license_url:
        return "unknown"
    
    l = license_url.lower()
    
    if "publicdomain" in l or "public-domain" in l or "pd" in l:
        return "public_domain"
    if "cc0" in l or "zero" in l:
        return "cc0"
    if "creativecommons.org/licenses/by-sa" in l:
        return "cc-by-sa"
    if "creativecommons.org/licenses/by" in l:
        return "cc-by"
    
    return "unknown"
```

**Gate location:** `backend/video_sources.py` → `ArchiveOrgSource.search()` line ~194

```python
if license_normalized not in YOUTUBE_SAFE_LICENSES:
    if license_normalized == "unknown":
        unknown_results.append({...})  # Collect separately
        continue
    if self.verbose:
        print(f"⚠️  Archive.org: Skipping {item_id} (unsafe license: {license_normalized})")
    continue
```

#### Co se stane když licence chybí/nejasná

- **Default behavior:** Skip asset (nevrátí se v results)
- **Optional fallback:** Env var `AAR_ALLOW_UNKNOWN_ARCHIVE_LICENSE=1` → vrátí unknown, ale s warning
- **User visibility:** Logováno do `archive_manifest.json` → `episode_pool.rejected_items[]` (debug mode)

#### Proof/Screenshot

- **Stored:** ❌ Ne (Archive.org license URL je stabilní, neukládáme screenshot)
- **Audit trail:** `license_raw` field v manifestu je auditovatelný

---

### 2. Wikimedia Commons

**Typ:** Public Domain / Creative Commons  
**URL:** `https://commons.wikimedia.org/`  
**API Endpoint:** `https://commons.wikimedia.org/w/api.php`

#### Jak se získává metadata

- **Search API:**
  ```python
  params = {
      "action": "query",
      "format": "json",
      "generator": "search",
      "gsrnamespace": "6",  # File: namespace
      "gsrsearch": f"filetype:video {query}",
      "gsrlimit": max_results,
      "prop": "imageinfo",
      "iiprop": "url|size|extmetadata|mediatype",
      "iiurlwidth": 320
  }
  response = requests.get("https://commons.wikimedia.org/w/api.php", params=params)
  ```

#### Co se ukládá

| Field | Type | Storage Location | Example Value |
|-------|------|------------------|---------------|
| `archive_item_id` | string | `episode_pool.videos[].archive_item_id` | `"wikimedia:File:Tesla_wireless_demo.webm"` |
| `source_url` | string | `episode_pool.videos[].url` | `"https://commons.wikimedia.org/wiki/File:Tesla_wireless_demo.webm"` |
| `asset_url` | string | `episode_pool.videos[].asset_url` | Direct CDN URL z `imageinfo[0].url` |
| `license` | string | `episode_pool.videos[].license` | `"cc-by-sa"` |
| `license_raw` | string | `episode_pool.videos[].license_raw` | `"CC BY-SA 4.0"` (z extmetadata.LicenseShortName) |
| `attribution` | string | `episode_pool.videos[].attribution` | `"Wikimedia user JohnDoe123"` (z extmetadata.Artist) |
| `license_url` | string | `episode_pool.videos[].license_url` | `"https://creativecommons.org/licenses/by-sa/4.0/"` (z extmetadata.LicenseUrl) |
| `thumbnail_url` | string | `episode_pool.videos[].thumbnail_url` | CDN thumbnail URL z `imageinfo[0].thumburl` |
| `retrieved_at` | ISO timestamp | `episode_pool.search_completed_at` | `"2025-01-03T14:22:11Z"` |
| `duration_sec` | float? | `episode_pool.videos[].duration_sec` | `45.2` (z `imageinfo[0].duration`) |

#### Kde probíhá licence check

**Modul:** `backend/video_sources.py` → `WikimediaSource._normalize_license()`  
**Řádek:** ~433-450

```python
def _normalize_license(self, license_short: str) -> str:
    if not license_short:
        return "unknown"
    
    l = license_short.lower()
    
    if "public domain" in l or "pd" in l:
        return "public_domain"
    if "cc0" in l or "cc-zero" in l:
        return "cc0"
    if "cc by-sa" in l or "cc-by-sa" in l:
        return "cc-by-sa"
    if "cc by" in l or "cc-by" in l:
        return "cc-by"
    
    return "unknown"
```

**Gate location:** `backend/video_sources.py` → `WikimediaSource.search()` line ~359

```python
if license_normalized not in YOUTUBE_SAFE_LICENSES:
    if self.verbose:
        print(f"⚠️  Wikimedia: Skipping {title} (unsafe license: {license_normalized})")
    continue
```

#### Co se stane když licence chybí

- **Hard gate:** Asset se skipne (není optional fallback)
- **Attribution handling:** Pokud `license.startswith("cc-by")` → attribution povinné (z Artist field)
- **User visibility:** Skipped items nejsou viditelné v UI (nevrátí se z search)

#### Proof/Screenshot

- **Stored:** `license_url` field (odkaz na CC license text)
- **Audit trail:** `license_raw` + `attribution` + `license_url` plně auditovatelné

---

### 3. Europeana (Cultural Heritage)

**Typ:** Public Domain / Creative Commons  
**URL:** `https://www.europeana.eu/`  
**API Endpoint:** `https://api.europeana.eu/record/v2/search.json`

#### Jak se získává metadata

- **Search API (requires API key):**
  ```python
  params = {
      "wskey": api_key,
      "query": query,
      "qf": "TYPE:VIDEO",
      "rows": max_results,
      "profile": "rich"  # Include extended metadata
  }
  response = requests.get("https://api.europeana.eu/record/v2/search.json", params=params)
  ```

- **Requires:** API key (register at https://pro.europeana.eu/page/get-api)

#### Co se ukládá

| Field | Type | Storage Location | Example Value |
|-------|------|------------------|---------------|
| `archive_item_id` | string | `episode_pool.videos[].archive_item_id` | `"europeana:/12345/abcdef"` |
| `source_url` | string | `episode_pool.videos[].url` | `"https://www.europeana.eu/item/12345/abcdef"` |
| `asset_url` | string | `episode_pool.videos[].asset_url` | Z `edmIsShownBy` nebo `edmIsShownAt` |
| `license` | string | `episode_pool.videos[].license` | `"cc-by"` |
| `license_raw` | string | `episode_pool.videos[].license_raw` | `"http://creativecommons.org/licenses/by/4.0/"` (z rights[0]) |
| `attribution` | string? | `episode_pool.videos[].attribution` | Z `dcCreator[0]` (pokud CC-BY) |
| `thumbnail_url` | string | `episode_pool.videos[].thumbnail_url` | Z `edmPreview[0]` |
| `retrieved_at` | ISO timestamp | `episode_pool.search_completed_at` | `"2025-01-03T14:22:11Z"` |

#### Kde probíhá licence check

**Modul:** `backend/video_sources.py` → `EuropeanaSource._normalize_license()`  
**Řádek:** ~780-798

```python
def _normalize_license(self, rights_url: str) -> str:
    if not rights_url:
        return "unknown"
    
    r = rights_url.lower()
    
    if "publicdomain" in r or "public-domain" in r:
        return "public_domain"
    # ... (similar pattern as Archive.org)
    
    return "unknown"
```

**Gate location:** `backend/video_sources.py` → `EuropeanaSource.search()` line ~505

```python
if license_normalized not in YOUTUBE_SAFE_LICENSES:
    if self.verbose:
        print(f"⚠️  Europeana: Skipping {item_id} (unsafe license: {license_normalized})")
    continue
```

#### Co se stane když licence chybí

- **Hard gate:** Asset se skipne (není vrácen)
- **API key chybí:** Source se vůbec nepoužije (disabled)
- **User visibility:** Logováno jako "source disabled (no API key)" v AAR stats

#### Proof/Screenshot

- **Stored:** `license_raw` (rights[0] URL)
- **Audit trail:** rights[0] je standardizovaný Europeana field

---

### 4. Pexels (Stock Video)

**Typ:** Pexels License (free for commercial use, attribution not required)  
**URL:** `https://www.pexels.com/`  
**API Endpoint:** `https://api.pexels.com/videos/search`

#### Jak se získává metadata

- **Search API (requires API key):**
  ```python
  headers = {
      "Authorization": api_key
  }
  params = {
      "query": query,
      "per_page": max_results
  }
  response = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params)
  ```

- **Requires:** API key (free tier: 200 requests/hour)

#### Co se ukládá

| Field | Type | Storage Location | Example Value |
|-------|------|------------------|---------------|
| `archive_item_id` | string | `episode_pool.videos[].archive_item_id` | `"pexels:12345678"` |
| `source_url` | string | `episode_pool.videos[].url` | `"https://www.pexels.com/video/12345678"` |
| `asset_url` | string | `episode_pool.videos[].asset_url` | Direct CDN URL (HD/SD based on `AAR_STOCK_MAX_HEIGHT`) |
| `license` | string | `episode_pool.videos[].license` | `"pexels"` (hardcoded) |
| `license_raw` | string | `episode_pool.videos[].license_raw` | `"Pexels License"` |
| `attribution` | string? | `episode_pool.videos[].attribution` | Photographer name (optional, not required by Pexels) |
| `license_url` | string | `episode_pool.videos[].license_url` | `"https://www.pexels.com/license/"` |
| `thumbnail_url` | string | `episode_pool.videos[].thumbnail_url` | Z `image` field v API response |
| `retrieved_at` | ISO timestamp | `episode_pool.search_completed_at` | `"2025-01-03T14:22:11Z"` |
| `duration_sec` | float | `episode_pool.videos[].duration_sec` | Z `duration` field |

#### Kde probíhá licence check

**Modul:** `backend/video_sources.py` → `PexelsSource` (hardcoded "pexels")  
**Řádek:** ~600-650

- **Licence:** Hardcoded jako `"pexels"` (není runtime check)
- **Whitelist:** `YOUTUBE_SAFE_LICENSES` obsahuje `"pexels"`
- **Gate:** Opt-in (musí existovat `PEXELS_API_KEY` env var)

#### Co se stane když API key chybí

- **Source disabled:** Pexels source se nepřidá do multi-source searcher
- **User visibility:** Není error, pouze není v available sources list

#### Proof/Screenshot

- **Stored:** `license_url` = `"https://www.pexels.com/license/"` (canonical reference)
- **Audit trail:** `source="pexels"` + `license_url` jednoznačně identifikuje licenci

---

### 5. Pixabay (Stock Video + Images)

**Typ:** Pixabay License (free for commercial use, no attribution required)  
**URL:** `https://pixabay.com/`  
**API Endpoint:** `https://pixabay.com/api/videos/` a `https://pixabay.com/api/`

#### Jak se získává metadata

- **Video Search API:**
  ```python
  params = {
      "key": api_key,
      "q": query,
      "per_page": max_results,
      "video_type": "all"
  }
  response = requests.get("https://pixabay.com/api/videos/", params=params)
  ```

- **Image Search API:**
  ```python
  params = {
      "key": api_key,
      "q": query,
      "per_page": max_results,
      "image_type": "photo"
  }
  response = requests.get("https://pixabay.com/api/", params=params)
  ```

#### Co se ukládá

| Field | Type | Storage Location | Example Value |
|-------|------|------------------|---------------|
| `archive_item_id` | string | `episode_pool.videos[].archive_item_id` | `"pixabay:video_98765"` |
| `source_url` | string | `episode_pool.videos[].url` | `"https://pixabay.com/videos/id-98765/"` |
| `asset_url` | string | `episode_pool.videos[].asset_url` | Direct CDN URL (medium/large based on `AAR_PIXABAY_QUALITY`) |
| `license` | string | `episode_pool.videos[].license` | `"pixabay"` (hardcoded) |
| `license_raw` | string | `episode_pool.videos[].license_raw` | `"Pixabay License"` |
| `attribution` | string? | `episode_pool.videos[].attribution` | User name (optional) |
| `license_url` | string | `episode_pool.videos[].license_url` | `"https://pixabay.com/service/license/"` |
| `thumbnail_url` | string | `episode_pool.videos[].thumbnail_url` | Z `userImageURL` (video) nebo `previewURL` (image) |
| `retrieved_at` | ISO timestamp | `episode_pool.search_completed_at` | `"2025-01-03T14:22:11Z"` |
| `duration_sec` | float | `episode_pool.videos[].duration_sec` | Z `duration` field |

#### Kde probíhá licence check

**Modul:** `backend/video_sources.py` → `PixabaySource` (hardcoded "pixabay")  
**Řádek:** ~700-800

- **Licence:** Hardcoded jako `"pixabay"` (není runtime check)
- **Whitelist:** `YOUTUBE_SAFE_LICENSES` obsahuje `"pixabay"`
- **Gate:** Opt-in (musí existovat `PIXABAY_API_KEY` env var)

#### Co se stane když API key chybí

- **Source disabled:** Pixabay source se nepřidá do multi-source searcher
- **User visibility:** Není error, pouze není v available sources

#### Proof/Screenshot

- **Stored:** `license_url` = `"https://pixabay.com/service/license/"` (canonical reference)
- **Audit trail:** `source="pixabay"` + `license_url` plně auditovatelné

---

### 6. Local Safety Pack (Fallback)

**Typ:** Public Domain (repo-bundled assets)  
**Lokace:** `images/` directory v repository root

#### Jak se získává metadata

- **Není externí API:** Lokální filesystem scan
- **Discovery:** `backend/local_safety_pack.py` → `list_safety_pack_files()`
  ```python
  def list_safety_pack_files() -> List[Path]:
      dirs = [repo_root / "images", repo_root / "uploads" / "backgrounds"]
      files = []
      for d in dirs:
          if d.exists():
              files.extend(d.glob("*.png"))
              files.extend(d.glob("*.jpg"))
              files.extend(d.glob("*.jpeg"))
      return files
  ```

#### Co se ukládá

| Field | Type | Storage Location | Example Value |
|-------|------|------------------|---------------|
| `archive_item_id` | string | `archive_manifest.json` → `beats[].asset_candidates[]` | `"local_safety_pack:texture_001.png"` |
| `asset_url` | string | N/A (local_path used) | N/A |
| `local_path` | string | `episode_pool.videos[].local_path` | `"/Users/.../podcasts/images/texture_001.png"` |
| `media_type` | string | `episode_pool.videos[].media_type` | `"image"` (always) |
| `license` | string | `episode_pool.videos[].license` | `"public_domain"` (hardcoded) |
| `source` | string | `episode_pool.videos[].source` | `"local_safety_pack"` |
| `is_fallback` | bool | `episode_pool.videos[].is_fallback` | `true` |
| `reason` | string | `episode_pool.videos[].reason` | `"AAR_EMPTY_RESULTS"` (why fallback used) |

#### Kde probíhá licence check

**Modul:** `backend/local_safety_pack.py` → `make_local_fallback_asset()`  
**Řádek:** ~90-101

- **Licence:** Hardcoded jako `"public_domain"` (repo-bundled, vetted manually)
- **Check:** Není runtime check (trust repo contents)

#### Co se stane když files chybí

- **Degraded mode:** Compilation může failnout (NO BLACK FALLBACKS policy)
- **Expected state:** Repo obsahuje min 10-20 generic textures

#### Proof/Screenshot

- **Stored:** File path je proof (lokální soubor)
- **Audit trail:** `images/video_project_metadata.json` obsahuje manual verification records

---

## Licence Priority Scoring

**Modul:** `backend/video_sources.py` → `LICENSE_PRIORITY`

```python
LICENSE_PRIORITY = {
    "public_domain": 10,  # Nejvyšší priorita
    "cc0": 10,
    "pd": 10,
    "cc-by": 5,
    "cc-by-sa": 5,
    "pexels": 6,  # Stock (high quality, ale ne archival)
    "pixabay": 6,
    "unknown": 0   # Nejnižší priorita (může být filtráno)
}
```

**Použití:** Při duplicate deduplication se preferuje higher priority licence (PD > CC-BY > Unknown).

---

## YouTube Monetization Safety

### Whitelisted Licenses

**Modul:** `backend/video_sources.py` → `YOUTUBE_SAFE_LICENSES`

```python
YOUTUBE_SAFE_LICENSES = {
    "public_domain",
    "cc0",
    "pd",
    "cc-by",
    "cc-by-2.0",
    "cc-by-3.0",
    "cc-by-4.0",
    "cc-by-sa",
    "cc-by-sa-2.0",
    "cc-by-sa-3.0",
    "cc-by-sa-4.0",
    "pexels",
    "pixabay",
}
```

### Blacklisted (auto-rejected)

- CC-BY-NC (non-commercial) → hard reject
- CC-BY-ND (no derivatives) → hard reject
- All Rights Reserved → hard reject
- Unknown (unless explicit fallback enabled) → soft reject

### Attribution Requirements

**CC-BY / CC-BY-SA assets:** Pipeline automaticky trackuje `attribution` field:

```json
{
  "archive_item_id": "wikimedia:File:Example.webm",
  "license": "cc-by-sa",
  "attribution": "John Doe (Wikimedia Commons)",
  "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"
}
```

**Kde se zobrazuje:** End credits v final video (optional, controlled by env var `CB_SHOW_ATTRIBUTION_CREDITS=1`)

---

## Compliance Checklist

### Pre-upload Validation

Před YouTube upload pipeline ověří:

1. ✅ Všechny assets mají `license` field
2. ✅ Všechny licence jsou v `YOUTUBE_SAFE_LICENSES`
3. ✅ CC-BY assets mají `attribution` field
4. ✅ `license_url` je validní (není prázdný)
5. ✅ `source_url` je zpětně auditovatelný

### Audit Trail

**Location:** `archive_manifest.json` → `episode_pool.videos[]`

Pro každý asset v final video existuje:
- `archive_item_id` (traceability)
- `source_url` (odkaz na původní item)
- `license` + `license_raw` (legal compliance)
- `attribution` (pokud CC-BY)
- `retrieved_at` (timestamp pro audit)

### Retention Policy

- **Manifest files:** Persistent (dokud existuje episode)
- **Downloaded assets:** Cached v `projects/<ep>/assets/` (lze smazat pro re-download)
- **License metadata:** Immutable v manifest (pokud se změní upstream, re-run AAR)

---

## Known Gaps & Mitigations

### 1. Archive.org Unknown Licenses

**Gap:** ~30% Archive.org items nemají explicitní licenseurl  
**Mitigation:**
- Default: Skip (hard gate)
- Optional: `AAR_ALLOW_UNKNOWN_ARCHIVE_LICENSE=1` → allow s warningem
- User visibility: UI zobrazuje warning badge "Unverified license"

### 2. Wikimedia License URL Changes

**Gap:** CC license URLs se občas mění (http → https, version upgrades)  
**Mitigation:**
- Ukládáme `license_raw` (exact string z API)
- `license` field je normalizovaný (stable across URL changes)
- Re-audit: Run AAR retry invalidates cache

### 3. Stock Provider Terms Changes

**Gap:** Pexels/Pixabay terms se mohou změnit  
**Mitigation:**
- Pipeline ukládá `license_url` (snapshot k datu stažení)
- Periodic review: Quarterly audit of stock terms
- Fallback: Disable stock sources (`AAR_ENABLE_STOCK_SOURCES=0`)

### 4. Local Safety Pack Provenance

**Gap:** `images/` files nemají embedded metadata  
**Mitigation:**
- Manual verification: `images/video_project_metadata.json` obsahuje source URLs
- Re-verify: Annual audit of safety pack contents
- Policy: Only add PD/CC0 textures (no CC-BY to avoid attribution requirement)

---

## Audit Commands

### Check all licenses in episode

```bash
cd backend
python3 -c "
import json
with open('../projects/<episode_id>/archive_manifest.json') as f:
    manifest = json.load(f)
for item in manifest['episode_pool']['videos']:
    print(f\"{item['archive_item_id']}: {item['license']} ({item.get('license_url', 'N/A')})\")
"
```

### Verify YouTube-safe compliance

```python
from video_sources import YOUTUBE_SAFE_LICENSES
import json

with open('archive_manifest.json') as f:
    manifest = json.load(f)

unsafe = []
for item in manifest['episode_pool']['videos']:
    if item['license'] not in YOUTUBE_SAFE_LICENSES:
        unsafe.append(item)

if unsafe:
    print(f"❌ Found {len(unsafe)} unsafe licenses:")
    for item in unsafe:
        print(f"  - {item['archive_item_id']}: {item['license']}")
else:
    print("✅ All licenses YouTube-safe")
```

### Generate attribution credits

```python
import json

with open('archive_manifest.json') as f:
    manifest = json.load(f)

credits = []
for item in manifest['episode_pool']['videos']:
    if item.get('attribution'):
        credits.append(f"{item['title']} by {item['attribution']} ({item['license']})")

print("\\n".join(credits))
```

---

## Change Log

- **2025-01-03:** Initial audit (FDA v2.7 + AAR v14)
- **2024-12-15:** Added Pexels/Pixabay stock sources
- **2024-11-20:** Added Europeana integration
- **2024-10-10:** Added local safety pack fallback
- **2024-09-01:** Initial multi-source implementation (Archive.org + Wikimedia)


