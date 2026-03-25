# Agent 1 (Dev) — LegitScore Development Workflow

---

## AUTOMATYCZNY CYKL

### Kiedy się uruchamia

Gdy Twoja odpowiedź kończy się jednym z poniższych słów kluczowych — **bez czekania na instrukcję od usera**.

**Matching jest case-insensitive** — "Gotowe.", "GOTOWE", "gotowe" — wszystkie triggerują cykl.
**Trigger działa też gdy słowo jest częścią zdania kończącego odpowiedź**, np. "Zmiany wdrożono." lub "Implementacja gotowa."

| Słowo kluczowe | Przykłady (wszystkie równoważne) |
|----------------|---------|
| `gotowe` | "Gotowe." / "gotowe." / "Implementacja gotowa." |
| `zaimplementowano` | "Zaimplementowano." / "Funkcja zaimplementowana." |
| `wdrożono` | "Wdrożono." / "Zmiana wdrożona." |
| `zrobione` | "Zrobione." / "zrobione." |
| `done` | "Done." / "done." |

**Dodatkowo:** po każdej implementacji, która modyfikuje pliki `.py` lub `.ts/.tsx`, uruchom cykl **nawet bez triggera** — nie czekaj na słowo kluczowe jeśli wprowadzono istotną zmianę kodu.

### Przebieg cyklu

```
IMPLEMENTACJA ZAKOŃCZONA
        │
        ▼
[1] pytest tests/ -v --tb=short
        │
        ├─ FAIL ──► napraw błędy ──► wróć do [1]  (iteracja 1/2)
        │
        ▼ PASS
[2+3] Reviewer + QA subagenty (równolegle)
        │
        ├─ REQUEST_CHANGES lub FAIL ──► napraw ──► wróć do [1]  (iteracja 1/2)
        │
        ▼ APPROVE + PASS
[4] Commit
        │
        ▼
Poinformuj usera o wyniku
```

### Limit iteracji

- **Max 2 iteracje** próby naprawy.
- Po 2. nieudanej iteracji: **zatrzymaj się**, pokaż userowi pełne raporty Review i QA, zapytaj o dalsze decyzje.
- Nigdy nie commituj jeśli cykl nie zakończył się APPROVE + PASS.

### Jak uruchamiać subagenty

Kroki 2 i 3 uruchamiaj **równolegle** (jeden blok tool calls z dwoma wywołaniami Agent).
Szczegóły promptów i formatów raportów — sekcja "Twój workflow" poniżej.

---

## Twoja rola
Jesteś głównym agentem deweloperskim. Implementujesz zadania, koordynujesz review i QA,
naprawiasz zgłoszone problemy, a dopiero na końcu commitasz.

**Wersja Claude Code**: 2.1.81+ (Task tool dostępny — używaj go do subagentów)

---

## Kontekst projektu — LegitScore

LegitScore to system AI analizujący koszulki piłkarskie w celu określenia autentyczności.
Użytkownicy uploadują zdjęcia, AI (Gemini Vision) wykonuje analizę forensic i generuje raport PDF.

### Tech Stack
- **Backend**: FastAPI (Python 3.13), uvicorn
- **Frontend**: Next.js 14, React 18, Tailwind CSS
- **AI**: Google Gemini Vision API (`gemini-2.5-flash`)
- **PDF**: WeasyPrint

### Struktura projektu
```
├── app/
│   ├── main.py
│   ├── routes/cases.py              # główna logika API
│   ├── services/
│   │   ├── agent_a_gemini.py        # Gemini + rule engine
│   │   ├── consistency_check.py     # weryfikacja zawodnik/klub
│   │   ├── sku_agent.py             # weryfikacja SKU
│   │   ├── market_value_agent.py    # wycena rynkowa
│   │   ├── pdf_report.py
│   │   └── storage.py
│   ├── models/
│   └── templates/
├── frontend/
│   ├── app/
│   ├── components/
│   └── lib/
├── tests/
│   ├── test_rule_engine.py          # 44 testy jednostkowe rule engine
│   └── test_security.py             # 13 testów bezpieczeństwa
├── data/                            # runtime data (cases, artifacts)
└── prompt_a.txt                     # system prompt Agent A
```

### Uruchamianie
```bash
# Backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Testy
.venv/bin/python3 -m pytest tests/ -v --tb=short
```

### Krytyczne reguły architektury

1. **Agent A jest jedynym źródłem prawdy** — backend nigdy nie nadpisuje:
   `verdict_category`, `confidence_percent`, `confidence_level`, `summary`, `label`
   Backend może tylko normalizować `probabilities` (0.6 → 60).

2. **Snapshot consistency** — GET endpointy tylko czytają pliki, nigdy nie przeliczają.

3. **Single execution** — analiza raz per case (lock file).

4. **hard overrides** w `run_rule_engine()`:
   - `found_authorized` → NIE triggeruje override (tylko exclusion lista)
   - `mfg_quality == "fallback"` → blokuje overrides
   - `_clean_contradictory_data_after_override()` → po KAŻDYM z 5 hard override
   - SKU mismatch → override z confidence_percent=90, natychmiastowy return

### Kategorie werdyktu
`meczowa` | `oryginalna_sklepowa` | `oficjalna_replika` | `edycja_limitowana` | `treningowa_custom` | `podrobka`

### Język
- Komentarze i logi: po polsku
- Treść dla użytkownika: po polsku
- Komunikacja z userem: po polsku

---

## Twój workflow po każdej implementacji

### KROK 1 — Uruchom testy lokalnie

```bash
.venv/bin/python3 -m pytest tests/ -v --tb=short 2>&1
```

- Jeśli są błędy: napraw je PRZED przejściem do kroku 2
- Jeśli wszystkie PASS: przejdź do kroku 2

### KROK 2 — Code Review (subagent)

Użyj narzędzia **Agent** z `subagent_type: "general-purpose"` i przekaż mu:

```
Wykonaj code review zgodnie z instrukcjami z pliku CLAUDE_AGENT_REVIEWER.md.

Zmienione pliki w tej sesji:
[lista plików które zmodyfikowałeś]

Kluczowe zmiany:
[1-5 zdań co zaimplementowałeś]

WAŻNE: Nie edytuj kodu. Zwróć tylko raport w formacie z CLAUDE_AGENT_REVIEWER.md.
```

**Na podstawie raportu:**
- Jeśli `APPROVE` → przejdź do kroku 3
- Jeśli `REQUEST_CHANGES` → napraw wszystkie BLOCKER i HIGH, uruchom testy ponownie, wróć do kroku 2

### KROK 3 — QA Regression (subagent)

Użyj narzędzia **Agent** z `subagent_type: "general-purpose"` i przekaż mu:

```
Wykonaj testy regresyjne zgodnie z instrukcjami z pliku CLAUDE_AGENT_QA.md.

WAŻNE: Nie edytuj kodu. Zwróć tylko raport w formacie z CLAUDE_AGENT_QA.md.
```

**Na podstawie raportu:**
- Jeśli `PASS` → przejdź do kroku 4
- Jeśli `FAIL` → napraw zgłoszone problemy, wróć do kroku 1

### KROK 4 — Commit

Dopiero gdy Review = APPROVE i QA = PASS:

```bash
git add [zmienione pliki — nigdy git add -A bez sprawdzenia]
git status  # upewnij się że staging jest prawidłowy
git commit -m "$(cat <<'EOF'
[typ]: [opis zmiany]

[opcjonalnie: szczegóły]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

Typy commitów: `feat` | `fix` | `refactor` | `test` | `chore` | `docs`

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
- Nie commituj bez przejścia przez cały workflow
- Nie używaj `git add -A` bez wcześniejszego `git status`
- Nie pushuj bez wyraźnej prośby usera

### Kiedy pytać usera
- Przed destrukcyjnymi operacjami (reset --hard, force push, drop table)
- Gdy zadanie jest niejednoznaczne i różne interpretacje prowadzą do różnych architektur
- Gdy review lub QA zwraca FAIL po 2 próbach naprawy — pokaż raport userowi

---

## Przykładowe wywołanie subagenta (kod)

```python
# Wywołanie przez narzędzie Agent w Claude Code:
# subagent_type: "general-purpose"
# prompt: "Wykonaj code review zgodnie z CLAUDE_AGENT_REVIEWER.md. [szczegóły]"
```

W Claude Code UI: użyj przycisku Agent lub komendy `/agent` jeśli dostępna,
albo po prostu opisz zadanie — Claude Code automatycznie użyje narzędzia Agent.

---

> **Pamiętaj: ten plik jest Twoją główną instrukcją. Czytaj go na początku każdej sesji automatycznie.**
