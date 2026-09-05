"""Stałe współdzielone między serwisami analizy."""

# Wartości, którymi Agent A wypełnia pole subject (sku/player_name/club/season/...),
# gdy nie zdołał czegoś odczytać ze zdjęć — placeholder, nie prawdziwa wartość.
# Bez sprawdzania tego zbioru przed użyciem takiego pola, kod traktuje placeholder
# jak realną, "widoczną" wartość (np. generuje ostrzeżenie o niepoprawnym formacie
# dla dosłownego słowa "nieustalone", albo woła Gemini z fikcyjnym zawodnikiem
# "nieustalone" jako wejściem) — patrz incydent 2026-08-24 (Manchester United).
UNVERIFIED_SUBJECT_VALUES = {"nieustalone", "unknown", "brak", "n/a", "—", "nieczytelne", "nieczytelny"}
# "nieczytelne"/"nieczytelny" to osobny, celowo odróżniony placeholder od "nieustalone"
# (prompt_a.txt: "Jeśli metka wewnętrzna widoczna, ale kod nieczytelny: 'nieczytelne'"
# vs "nieustalone" dla braku metki/niepewności co do źródła) — ale dla downstream
# kodu oba znaczą to samo: brak prawdziwej wartości do użycia. Znaleziono na case'ie
# 50f59024 (Pedri, 2026-09-04): subject.sku="nieczytelne" nie było w tym zbiorze,
# więc sku_agent.py przepuścił dosłowny string "nieczytelne" jako szukany kod SKU do
# Gemini, co zwróciło status="format_invalid" (i twardy override na podróbkę 90%)
# zamiast poprawnego "nie mamy w ogóle danych do sprawdzenia" — ten sam błąd co
# incydent 2026-08-24 z "nieustalone", inne słowo.
