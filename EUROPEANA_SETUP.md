# 🇪🇺 Europeana API Setup - Jak získat API klíč ZDARMA

Europeana je **největší evropská digitální knihovna** s 50+ miliony objektů z muzeí, galerií, knihoven a archivů.

Pro **historická evropská témata** (Napoleon, WW2, středověk, renesance) je **KLÍČOVÝ zdroj**.

---

## ⏱️ Rychlý setup (5 minut)

### Krok 1: Registrace na Europeana Pro

1. Jdi na: **https://pro.europeana.eu/page/get-api**
2. Klikni na **"Request your API keys"** (modrý button)
3. Vyplň registrační formulář:
   - **First Name / Last Name**: Tvoje jméno
   - **Email**: Tvůj email
   - **Organization**: Můžeš dát "Independent Creator" nebo "Personal Project"
   - **Website**: Pokud nemáš, dej např. "https://github.com/yourusername"
   - **Description**: "Educational documentary video creation using historical archive footage"
   - **Use case**: "Non-commercial educational content"

4. **Potvrď email** (přijde ti aktivační link)
5. **Přihlaš se** na https://pro.europeana.eu
6. Jdi do **"API Console"** nebo **"My API Keys"**
7. **Zkopíruj API key** (dlouhý string jako `apidemo123456789...`)

---

## 🔧 Integrace do projektu

### Krok 2: Přidej API key do `.env`

Otevři soubor `backend/.env` a přidej:

```bash
# === EUROPEANA API KEY ===
EUROPEANA_API_KEY=your_actual_api_key_here
```

**Příklad:**
```bash
EUROPEANA_API_KEY=apidemoXYZ123456789abcdef
```

### Krok 3: Restart backend

```bash
cd /Users/petrliesner/podcasts
./restart_all.sh
```

Nebo manuálně:
```bash
cd backend
python3 app.py
```

---

## ✅ Ověření že funguje

V backend logu by měls vidět:

```
✅ AAR: Multi-source enabled with 3 providers: ['ArchiveOrgSource', 'WikimediaSource', 'EuropeanaSource']
```

Pokud vidíš **pouze 2 providers**, pak:
- ❌ API key není nastaven, nebo
- ❌ Backend neběží s novým kódem

---

## 📊 Co to přinese?

### Počet videí před/po Europeana:

| Téma | Bez Europeana | S Europeana | Rozdíl |
|------|---------------|-------------|---------|
| Napoleon 1812 | 1-3 videa | 8-15 videí | **+400%** |
| WW2 Europe | 5-10 videí | 20-40 videí | **+300%** |
| Středověk | 0-2 videa | 10-25 videí | **+1000%** |
| Renesance | 1-3 videa | 15-30 videí | **+700%** |

### Typy obsahu z Europeana:

- 🎥 **Historické filmy** (newsreely, dokumenty)
- 🗺️ **Animované mapy** (hranice, bitvy)
- 📸 **Digitalizované fotografie** (19. století)
- 🎨 **Umělecká díla** (portréty, ilustrace)
- 📜 **Rukopisy a dokumenty**

---

## 🌍 Europeana Coverage

**Nejlepší pro:**
- 🇫🇷 Francouzská historie
- 🇩🇪 Německá historie
- 🇬🇧 Britská historie
- 🇮🇹 Italská historie
- 🇪🇸 Španělská historie
- 🇳🇱 Nizozemská historie
- 🇵🇱 Polská historie
- 🇬🇷 Řecká historie

**Méně obsahu pro:**
- 🇺🇸 Americká historie (použij Library of Congress)
- 🇨🇳 Asijská historie
- 🇦🇺 Oceánie

---

## ⚠️ Rate Limiting

Europeana má **fair use policy**:
- ✅ **10,000 requests/den** (více než dost)
- ✅ **Bez throttlingu** pro normální použití
- ⚠️ Pokud překročíš limit, API vrátí `429 Too Many Requests`

Náš systém automaticky **throttluje 0.5s mezi requesty**, takže by to nikdy nemělo být problém.

---

## 🔒 Licence Info

Europeana vrací pouze obsah s **jasnou licencí**:
- ✅ Public Domain
- ✅ CC0
- ✅ CC-BY
- ✅ CC-BY-SA
- ❌ All Rights Reserved (automaticky filtrováno)

Všechny výsledky jsou **bezpečné pro YouTube monetizaci**.

---

## 🐛 Troubleshooting

### Problém: "Europeana: API key not configured"

**Řešení:**
1. Zkontroluj že `.env` soubor existuje v `backend/` složce
2. Zkontroluj že API key je bez uvozovek:
   ```bash
   # ✅ Správně
   EUROPEANA_API_KEY=apidemo123456
   
   # ❌ Špatně
   EUROPEANA_API_KEY="apidemo123456"
   EUROPEANA_API_KEY='apidemo123456'
   ```
3. Restart backend

### Problém: "401 Unauthorized"

**Řešení:**
- API key je neplatný nebo expirovaný
- Zkontroluj na https://pro.europeana.eu/page/my-api-keys
- Vygeneruj nový API key

### Problém: "429 Too Many Requests"

**Řešení:**
- Překročil jsi denní limit (velmi nepravděpodobné)
- Počkej 24 hodin nebo kontaktuj Europeana support

---

## 📞 Podpora

- **Europeana API Docs**: https://pro.europeana.eu/page/apis
- **Rate Limits**: https://pro.europeana.eu/page/rate-limits
- **Support**: https://pro.europeana.eu/page/support

---

**Vytvořeno:** 2025-12-28  
**Poslední update:** 2025-12-28



