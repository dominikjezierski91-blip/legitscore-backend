"""Stałe współdzielone między serwisami analizy."""

# Wartości, którymi Agent A wypełnia pole subject (sku/player_name/club/season/...),
# gdy nie zdołał czegoś odczytać ze zdjęć — placeholder, nie prawdziwa wartość.
# Bez sprawdzania tego zbioru przed użyciem takiego pola, kod traktuje placeholder
# jak realną, "widoczną" wartość (np. generuje ostrzeżenie o niepoprawnym formacie
# dla dosłownego słowa "nieustalone", albo woła Gemini z fikcyjnym zawodnikiem
# "nieustalone" jako wejściem) — patrz incydent 2026-08-24 (Manchester United).
UNVERIFIED_SUBJECT_VALUES = {"nieustalone", "unknown", "brak", "n/a", "—"}
