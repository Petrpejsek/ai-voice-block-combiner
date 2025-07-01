# 🎤 ElevenLabs Průvodce

## 🚀 Jak používat generování hlasů

### 1. Získání API klíče
1. Jděte na [elevenlabs.io](https://elevenlabs.io)
2. Zaregistrujte se nebo se přihlaste
3. Jděte do **Settings** → **API Keys**
4. Zkopírujte váš API klíč (začíná `sk-...`)

### 2. Nalezení Voice ID
1. V ElevenLabs jděte do **Voice Library**
2. Vyberte hlas nebo vytvořte vlastní
3. Klikněte na hlas a zkopírujte **Voice ID**

#### 🎭 Doporučené hlasy:
- **Rachel** (Female, American): `21m00Tcm4TlvDq8ikWAM`
- **Drew** (Male, American): `29vD33N1CtxCmqQRPOHJ`
- **Clyde** (Male, American): `2EiwWnXFnvU5JabPnv8n`
- **Bella** (Female, American): `EXAVITQu4vr4xnSDxMaL`

### 3. JSON Formát

#### Základní formát:
```json
{
  "nazev_bloku": {
    "text": "Text k namluvení",
    "voice_id": "Voice ID z ElevenLabs"
  }
}
```

#### 📝 Praktický příklad:
```json
{
  "Tesla_1": {
    "text": "Dobrý den, já jsem Nikola Tesla. Dnes budu mluvit o elektřině a jejích zázračných vlastnostech.",
    "voice_id": "21m00Tcm4TlvDq8ikWAM"
  },
  "Socrates_1": {
    "text": "Zdravím vás, přátelé. Já jsem Socrates a rád bych s vámi filosofoval o podstatě poznání.",
    "voice_id": "29vD33N1CtxCmqQRPOHJ"  
  },
  "Tesla_2": {
    "text": "Bezdrátový přenos energie není jen snem - je to budoucnost lidstva!",
    "voice_id": "21m00Tcm4TlvDq8ikWAM"
  },
  "Socrates_2": {
    "text": "Vím jen to, že nic nevím. A právě tato pokora je začátkem veškeré moudrosti.",
    "voice_id": "29vD33N1CtxCmqQRPOHJ"
  }
}
```

### 4. Tipy pro lepší výsledky

#### 📝 Psaní textu:
- **Používejte krátké věty** (5-15 slov)
- **Přidejte interpunkci** (tečky, čárky, otazníky)
- **Vyhněte se zkratkám** - pište celá slova
- **Používejte pauzky** `...` pro dramatický efekt

#### 🎭 Názvy hlasových bloků:
- **Konzistentní pojmenování**: `Tesla_1`, `Tesla_2`, `Tesla_3`
- **Logické řazení**: aplikace automaticky seřadí podle čísel
- **Jasné označení**: `Intro_Tesla`, `Main_Socrates`, `Outro_Tesla`

#### ⚡ Optimalizace rychlosti:
- **Kratší texty** se generují rychleji
- **Méně bloků najednou** = rychlejší zpracování
- **Testujte nejdřív s jedním blokem**

### 5. Rozšířené možnosti

#### 🎚️ Vlastní nastavení hlasu:
Pro pokročilejší uživatele můžete upravit `voice_settings` v backendu:

```python
"voice_settings": {
    "stability": 0.5,        # 0-1 (stabilita hlasu)
    "similarity_boost": 0.5, # 0-1 (podobnost s originálem)
    "style": 0.0,           # 0-1 (styl/emoce)
    "use_speaker_boost": True # zlepšení kvality
}
```

### 6. Příklady scénářů

#### 🎓 Vzdělávací podcast:
```json
{
  "Intro": {
    "text": "Vítejte u další epizody našeho vzdělávacího podcastu!",
    "voice_id": "EXAVITQu4vr4xnSDxMaL"
  },
  "Lektor_1": {
    "text": "Dnes si povíme o kvantové fyzice a jejích základních principech.",
    "voice_id": "21m00Tcm4TlvDq8ikWAM"
  },
  "Otazka": {
    "text": "Ale co to vlastně kvantová fyzika je?",
    "voice_id": "29vD33N1CtxCmqQRPOHJ"
  }
}
```

#### 🎭 Dramatický příběh:
```json
{
  "Vypravec": {
    "text": "Bylo nejtemnější hodin noci, když se Holmes vrátil do Baker Street.",
    "voice_id": "2EiwWnXFnvU5JabPnv8n"
  },
  "Holmes": {
    "text": "Watson, máme případ! Hra může začít.",
    "voice_id": "21m00Tcm4TlvDq8ikWAM"
  },
  "Watson": {
    "text": "Holmes, co jste zase objevil?",
    "voice_id": "29vD33N1CtxCmqQRPOHJ"
  }
}
```

### 7. Řešení problémů

#### ❌ Časté chyby:
- **API klíč neplatný**: Zkontrolujte, že začíná `sk-`
- **Voice ID neplatné**: Ověřte ve Voice Library
- **Text příliš dlouhý**: Rozdělte na kratší bloky
- **Špatný JSON**: Zkontrolujte syntaxi (čárky, uvozovky)

#### ⚡ Řešení:
1. **Použijte "Načíst ukázku"** pro správný formát
2. **Testujte s malým množstvím textu**
3. **Zkopírujte Voice ID přesně**
4. **Zkontrolujte zbývající kredity na ElevenLabs**

### 8. Ceny a limity

- **Free účet**: 10,000 znaků/měsíc
- **Starter**: $5/měsíc = 30,000 znaků
- **Creator**: $22/měsíc = 100,000 znaků
- **Pro**: $99/měsíc = 500,000 znaků

💡 **Tip**: Jeden průměrný blok (~100 slov) = ~500 znaků

---

## 🎯 Rychlý start

1. **Zkopírujte ukázkový JSON** tlačítkem "Načíst ukázku"
2. **Vložte svůj API klíč** z ElevenLabs
3. **Upravte texty** podle svých potřeb
4. **Klikněte "Generovat hlasy"**
5. **Počkejte na dokončení** a pokračujte ke kombinování

**Tip**: Začněte s jedním nebo dvěma bloky pro testování!

---

*Vytvořeno s ❤️ pro snadné generování kvalitních hlasů* 