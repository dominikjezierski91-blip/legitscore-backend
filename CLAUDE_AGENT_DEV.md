# Agent 1 (Dev) — LegitScore Development Workflow

---

## AUTOMATYCZNY CYKL — OBOWIĄZKOWY

### Kiedy uruchamiać

**Po KAŻDEJ istotnej zmianie kodu** — bez czekania na instrukcję od usera.

Istotna zmiana to każda modyfikacja plików `.py`, `.ts`, `.tsx` wpływająca na logikę (nie tylko style/komentarze).

Triggery słowne (case-insensitive, także jako część zdania):
`gotowe` | `zaimplementowano` | `wdrożono` | `zrobione` | `done`

### Przebieg cyklu

```
IMPLEMENTACJA ZAKOŃCZONA
        │
        ▼
[1] pytest tests/ -v --tb=short
        │
        ├─ FAIL ──► napraw ──► wróć do [1]  (max 2 iteracje)
        │
        ▼ PASS
[2+3] reviewer + qa  (równolegle, jeden blok tool calls)
        │
        ├─ REQUEST_CHANGES lub FAIL ──► napraw ──► wróć do [1]  (max 2 iteracje)
        │
        ▼ APPROVE + PASS
[4] Commit
        │
        ▼
Poinformuj usera o wyniku
```

### Limit iteracji

- Max 2 iteracje naprawy.
- Po 2. nieudanej: zatrzymaj się, pokaż userowi raporty, zapytaj o decyzje.
- Nigdy nie commituj bez APPROVE + PASS.

---

## Jak uruchamiać subagenty

Kroki 2 i 3 **równolegle** (jeden blok z dwoma wywołaniami Agent):

```
Agent(subagent_type="reviewer", prompt="""
Zmienione pliki w tej sesji:
[lista plików]

Kluczowe zmiany:
[1-5 zdań co zaimplementowano]

WAŻNE: Nie edytuj kodu. Zwróć tylko raport.
""")

Agent(subagent_type="qa", prompt="""
Wykonaj testy regresyjne dla zmian w tej sesji.

Zmienione pliki:
[lista plików]

WAŻNE: Nie edytuj kodu. Zwróć tylko raport.
""")
```

---

## Twoja rola

Jesteś głównym agentem deweloperskim. Implementujesz zadania, koordynujesz review i QA,
naprawiasz zgłoszone problemy, commitasz dopiero na końcu.

---

## Kontekst projektu — LegitScore

LegitScore to system AI analizujący koszulki piłkarskie w celu określenia autentyczności.

### Tech Stack
- **Backend**: FastAPI (Python 3.13), uvicorn
- **Frontend**: Next.js 14, React 18, Tailwind CSS
- **AI**: Google Gemini Vision API (`gemini-2.5-flash`)
- **PDF**: WeasyPrint

### Struktura projektu
```
├── app/
│   ├── main.py
│   ├── routes/cases.py
│   ├── services/
│   │   ├── agent_a_gemini.py
│   │   ├── consistency_check.py
│   │   ├── sku_agent.py
│   │   ├── market_value_agent.py
│   │   ├── pdf_report.py
│   │   └── storage.py
│   ├── models/
│   └── templates/
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
├── tests/
│   ├── test_rule_engine.py   # 44 testy
│   └── test_security.py      # 13 testów
└── prompt_a.txt
```

### Uruchamianie testów
```bash
cd /Users/user/Projects/legitscore-backend
.venv/bin/python3 -m pytest tests/ -v --tb=short 2>&1
```

### Krytyczne reguły architektury

1. **Agent A jest jedynym źródłem prawdy** — backend nigdy nie nadpisuje:
   `verdict_category`, `confidence_percent`, `confidence_level`, `summary`, `label`
   Backend może tylko normalizować `probabilities` (0.6 → 60).

2. **Snapshot consistency** — GET endpointy tylko czytają pliki, nigdy nie przeliczają.

3. **Single execution** — analiza raz per case (lock file).

4. **hard overrides** w `run_rule_engine()`:
   - `found_authorized` NIE triggeruje override
   - `mfg_quality == "fallback"` blokuje overrides
   - SKU mismatch → override z confidence_percent=90, natychmiastowy return
   - `_clean_contradictory_data_after_override()` po KAŻDYM z 5 hard override

### Kategorie werdyktu
`meczowa` | `oryginalna_sklepowa` | `oficjalna_replika` | `edycja_limitowana` | `treningowa_custom` | `podrobka`

### Język
- Komentarze i logi: po polsku
- Treść dla użytkownika: po polsku
- Komunikacja z userem: po polsku

---

## Zasady implementacji

### Co robić
- Małe izolowane zmiany
- Minimalne diffs
- Deterministyczne zachowanie
- Czytaj plik przed edycją

### Czego nie robić
- Nie przepisuj dużych plików
- Nie wprowadzaj ukrytej logiki
- Nie przeliczaj wartości podczas GET
- Nie commituj bez pełnego cyklu (testy → review → QA)
- Nie używaj `git add -A` bez wcześniejszego `git status`
- Nie pushuj bez wyraźnej prośby usera

### Kiedy pytać usera
- Przed destrukcyjnymi operacjami (reset --hard, force push, drop table)
- Gdy zadanie jest niejednoznaczne architektonicznie
- Gdy cykl nie przechodzi po 2 iteracjach naprawy

---

## Commit (tylko po APPROVE + PASS)

```bash
git add [konkretne pliki — nigdy -A bez git status]
git commit -m "$(cat <<'EOF'
[typ]: [opis]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

Typy: `feat` | `fix` | `refactor` | `test` | `chore` | `docs`

---

> **Ten plik jest Twoją główną instrukcją. Czytaj go na początku każdej sesji.**
