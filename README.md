### Konfiguracja Gemini

- **GEMINI_API_KEY** – klucz API Gemini Developer, wymagany do działania `/run-decision`.
- **GOOGLE_API_KEY** – alternatywnie możesz użyć tego klucza; jeśli oba są ustawione, używany jest `GEMINI_API_KEY`.
- **GEMINI_MODEL** – nazwa modelu używanego przez agenta A.
  - Domyślnie: `gemini-1.5-flash`
  - Przykład zmiany modelu:

  ```bash
  export GEMINI_MODEL="gemini-2.5-flash"
  export GEMINI_API_KEY="twój_klucz_api"
  ```

Jeśli klucz nie jest ustawiony, endpoint `/api/cases/{case_id}/run-decision` zwróci `503` z komunikatem
`"Gemini API key missing"` zamiast stack trace.

