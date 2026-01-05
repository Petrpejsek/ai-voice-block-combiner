# 🔐 Secrets Directory

Tento adresář obsahuje citlivé soubory, které **NESMÍ** být v gitu.

## 📋 Co sem patří

### Google Cloud Service Account JSON

Umístěte sem váš Google Cloud service account JSON klíč:

```
backend/secrets/google-tts-service-account.json
```

**Nebo pojmenujte soubor libovolně:**
- `google-tts-key.json`
- `service-account.json`
- `my-project-key.json`

Setup script automaticky najde **první .json soubor** v tomto adresáři.

## 🚀 Jak získat Service Account JSON

1. Jděte na [Google Cloud Console](https://console.cloud.google.com)
2. Vyberte projekt nebo vytvořte nový
3. Zapněte **Cloud Text-to-Speech API**
   - APIs & Services → Enable APIs and Services
   - Hledejte "Cloud Text-to-Speech API"
   - Klikněte Enable
4. Vytvořte Service Account:
   - IAM & Admin → Service Accounts
   - Create Service Account
   - Name: `tts-service-account`
   - Role: `Cloud Text-to-Speech User` (nebo `Editor`)
   - Create and continue
5. Vygenerujte klíč:
   - V seznamu service accounts klikněte na nově vytvořený account
   - Keys → Add Key → Create New Key
   - Vyberte **JSON**
   - Stáhněte soubor
6. Přesuňte sem:
   ```bash
   mv ~/Downloads/your-project-*.json backend/secrets/google-tts-service-account.json
   ```

## ✅ Po přidání JSON souboru

Spusťte setup script:

```bash
python3 setup_google_tts.py
```

Script automaticky:
- ✅ Najde JSON soubor v secrets/
- ✅ Aktualizuje backend/.env s GOOGLE_APPLICATION_CREDENTIALS
- ✅ Restartuje backend
- ✅ Spustí E2E smoke test
- ✅ Vypíše PASS/FAIL

## 🔒 Security

**NIKDY** necommitujte tento adresář do gitu!

- ✅ `backend/secrets/` je v `.gitignore`
- ✅ Všechny `.json` soubory jsou ignorovány
- ✅ Tento README je jediný soubor, který smí do gitu

## 🧪 Test bez credentials

Pokud ještě nemáte JSON klíč, E2E test bude SKIPPED s jasnou instrukcí.



