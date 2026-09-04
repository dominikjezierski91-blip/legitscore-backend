"""
Kit Context Search — wstrzykuje aktualną wiedzę o oficjalnych krojach przed analizą Agent A.

Krok 1: Szybki Gemini call — identyfikuje klub i producenta z obrazów.
Krok 2: Gemini z url_context czyta footy-headlines.com bezpośrednio (live scraping),
         wyciąga opisy designu dla ostatnich 3 sezonów per typ koszulki.
Fallback: jeśli url_context zawiedzie, Google Search jak poprzednio.

Non-fatal — błąd zwraca pusty string.
"""

import asyncio
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_MAX_CONTEXT_BLOCK_CHARS = 1500


def _current_season_start_years(count: int = 4) -> List[int]:
    """Rok startowy N ostatnich sezonów piłkarskich, licząc od dzisiejszej daty
    (konwencja: sezon zaczyna się w lipcu, np. sezon "2026/27" zaczyna się w
    lipcu 2026). Liczone dynamicznie — patrz incydent (2026-08-20): zapytania
    wyszukiwania miały sezony zakodowane na sztywno do "2025/26", więc agent
    nigdy nie sprawdzał, czy koszulka może być z NOWEGO sezonu (2026/27), mimo
    że sezon ten realnie już trwał w dniu analizy."""
    now = datetime.now(timezone.utc)
    current_start_year = now.year if now.month >= 7 else now.year - 1
    return [current_start_year - i for i in range(count)]


def _season_label(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"

_IDENTIFICATION_PROMPT = """You are a football jersey identification assistant.
Look at the images and extract basic identification data. Be brief and factual.

Return plain text (NOT JSON) with exactly these fields, one per line:
club: [club name in English, or "unknown"]
manufacturer: [Nike / Adidas / Puma / other, or "unknown"]
season_guess: [visual best guess e.g. "2025/26" — may be unreliable if manufacturer reused similar designs, write "unknown" if unsure]
special_features: [distinctive logos, patches, collaboration indicators, limited edition markings — or "none"]

Only output the 4 lines above. No explanation."""

_SCRAPE_PROMPT = """You are a football kit database assistant with access to web pages.

Read the provided football kit page(s) and extract for each kit found:
- Season (e.g. 2025/26)
- Kit type (home / away / third / goalkeeper / special)
- Visual description: dominant colors, stripe pattern, color gradient or texture, collar style
- Sponsor: name, color, shape/style on shirt
- Any unique badge, patch, special marking, or collaboration element

IMPORTANT: Focus on the 4 most recent seasons. If two seasons share a visually similar design (same stripe pattern, similar colors), explicitly state what distinguishes them — especially sponsor name/color and any badge differences.

Start with "OFFICIAL KIT CONTEXT:" then write plain text, one paragraph per kit. Be specific — Agent A uses this to identify which season a jersey belongs to."""

def _build_search_fallback_prompt() -> str:
    """Buduje prompt z aktualnymi sezonami zamiast zakodowanych na sztywno lat —
    patrz komentarz przy _current_season_start_years()."""
    years = _current_season_start_years(4)
    labels = [_season_label(y) for y in years]
    return f"""You are a football kit authenticity researcher with access to Google Search.

Jersey identification data provided. The season_guess may be UNRELIABLE — manufacturers reuse designs.
Today's reference date means the CURRENT season is {labels[0]} — a jersey may genuinely be from this
newest season, not necessarily an older one. Do not assume the newest season "doesn't exist yet".

MANDATORY searches — run ALL:
1. "site:footy-headlines.com [club] [manufacturer] {years[0]}"
2. "site:footy-headlines.com [club] [manufacturer] {years[1]}"
3. "[manufacturer] [club] {labels[0]} home away third kit official"
4. "[manufacturer] [club] {labels[1]} home away third kit official"
5. "[manufacturer] [club] {labels[2]} kit official"

For each season found, describe the VISUAL DESIGN: colors, stripe pattern, sponsor name/color, unique elements.
If two seasons look similar, state exactly what differentiates them.

Start with "OFFICIAL KIT CONTEXT:" — plain text only."""

_TROPHY_SEARCH_PROMPT = """You are a football trophy researcher with access to Google Search.

Search for OFFICIAL, VERIFIABLE trophies/titles won by the given club, focusing on the current
year and the two years before it (recent seasons only — do not report older history).
Cover: domestic league, domestic cup, continental competitions (e.g. Champions League / Europa
League / Copa Libertadores), and world/intercontinental titles (e.g. FIFA Intercontinental Cup,
Club World Cup).

MANDATORY searches — run ALL:
1. "[club] trophies won 2024 2025 2026"
2. "[club] champions league final result winner runner-up"
3. "[club] league title winner 2025 2026"
4. "[club] intercontinental cup OR club world cup winner"

CRITICAL — WON vs REACHED: for cup/knockout competitions (Champions League, Europa League,
domestic cups, World/Intercontinental Cup) you MUST determine and explicitly state whether the
club WON the final or only REACHED it (runner-up/finalist). Commemorative jersey patches reading
"FINAL [CITY] [YEAR]" are issued to the WINNING team as a champion's patch — do not report a
final as merely "the club played in it" if your search shows they won it; state the outcome
plainly (won / runner-up) so this is unambiguous downstream.

For each CONFIRMED result, report: competition name, year, WON or RUNNER-UP, and host city of
the final if known (needed for "FINAL [CITY] [YEAR]" style commemorative patches). Only report
what your search actually confirms — do not guess or extrapolate. If a search finds nothing for
a competition, say so explicitly instead of omitting it silently.

Start with "RECENT CONFIRMED TITLES:" then list each confirmed result on its own line as:
[competition] — [year] — WON or RUNNER-UP — [host city or "unknown"]
If no confirmed titles were found at all, write exactly: "RECENT CONFIRMED TITLES: none found"."""


def _build_tech_name_search_prompt() -> str:
    """Buduje prompt z aktualnym sezonem — patrz _build_search_fallback_prompt()."""
    label = _season_label(_current_season_start_years(1)[0])
    return f"""You are a sportswear technology researcher with access to Google Search.

Search for the CURRENT, OFFICIAL fabric/moisture-wicking technology brand names that the given
manufacturer uses on football/soccer jerseys for the {label} season, across product tiers
(authentic/match-issue vs replica/stadium/fan version). Manufacturers regularly introduce, rename,
or retire these technology names across seasons (e.g. Nike's Dri-FIT ADV for the authentic/match
tier, Adidas's AEROREADY/HEATRDY) — the name you find for {label} may differ from what you learned
during training, which has an earlier cutoff. Do not assume an unfamiliar name is wrong just
because you don't recognize it.

MANDATORY searches — run ALL:
1. "[manufacturer] football jersey technology name authentic match {label}"
2. "[manufacturer] [club] authentic jersey technology fabric {label}"
3. "[manufacturer] soccer jersey stadium replica technology name {label}"

For each tier you find (authentic/match vs replica/stadium/fan), report the current official
technology name(s) actually in use for {label}, and explicitly note if it differs from an older
name (e.g. a rename from a prior season).

Start with "CONFIRMED CURRENT TECHNOLOGY NAMES:" then list each finding as:
[tier] — [technology name] — [note]
If nothing could be confirmed, write exactly: "CONFIRMED CURRENT TECHNOLOGY NAMES: none found"."""


def _club_to_footy_headlines_slug(club: str) -> str:
    """FC Barcelona → fc-barcelona, Atlético Madrid → atletico-madrid"""
    normalized = unicodedata.normalize("NFKD", club)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_str.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug or len(slug) > 80:
        return ""
    return slug


async def run_kit_context_search(asset_paths: List[str]) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("[KIT_CONTEXT] google-genai niedostępne")
        return ""

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return ""

    fast_model = os.getenv("GEMINI_FAST_MODEL", "models/gemini-2.5-flash")
    client = genai.Client(api_key=api_key)

    # --- Krok 1: identyfikacja z obrazów ---
    parts = []
    for p in asset_paths[:4]:
        path = Path(p)
        if not path.exists():
            continue
        ext = path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))

    if not parts:
        return ""

    parts.insert(0, types.Part(text="Identify this jersey:"))

    try:
        id_resp = await client.aio.models.generate_content(
            model=fast_model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=_IDENTIFICATION_PROMPT,
                temperature=0.1,
            ),
        )
        identification = (id_resp.text or "").strip()
    except Exception as e:
        logger.warning("[KIT_CONTEXT] Identyfikacja nieudana: %s", e)
        return ""

    if not identification:
        return ""

    logger.info("[KIT_CONTEXT] Identyfikacja: %s", identification.replace("\n", " | "))

    lines = {
        k.strip(): v.strip()
        for line in identification.splitlines()
        if ":" in line
        for k, v in [line.split(":", 1)]
    }
    club = lines.get("club", "unknown")
    if club.lower() == "unknown":
        logger.info("[KIT_CONTEXT] Nieznany klub — pomijam search")
        return ""
    manufacturer = lines.get("manufacturer", "unknown")

    # --- Krok 2a: żywa weryfikacja ostatnich tytułów/pucharów (Google Search) ---
    # Uruchamiana ZAWSZE, niezależnie od tego, czy web-scraping designu kroju się
    # powiedzie — to ta część, która pozwala Agentowi A wiedzieć, że np. "FINAL
    # BUDAPEST 2026" to prawdziwe, rozegrane wydarzenie, a nie fikcja (patrz
    # incydent PSG Kvaratskhelia). Non-fatal: pusty string przy błędzie.
    # Odpalana RÓWNOLEGLE z krokiem 2b (nie sekwencyjnie) — to osobne, niezależne
    # wywołanie Gemini, więc czekanie na nie po kolei tylko dokładałoby pełny
    # dodatkowy round-trip do czasu każdej analizy bez potrzeby.
    trophy_task = asyncio.create_task(_fetch_recent_trophies(client, fast_model, types, club))

    # --- Krok 2a-bis: żywa weryfikacja aktualnych nazw technologii materiału ---
    # Ten sam problem co trofea, inna postać: producenci zmieniają nazwy technologii
    # materiału/nadruku między sezonami (np. Nike Dri-FIT ADV dla wersji meczowej),
    # a Agent A z datą odcięcia treningu nie zna nazw nowszych niż jego wiedza —
    # patrz incydent PSG Dembélé (2026-09-04): raport uznał nazwę "AERO-FIT" za
    # "przestarzałą technologię Nike" i to był kluczowy dowód werdyktu "Podróbka
    # 95%", mimo że to literalnie aktualna, oficjalna nazwa Nike dla tej dokładnie
    # autentycznej koszulki (potwierdzone na nike.com pod tym samym SKU).
    # Odpalana równolegle z resztą, non-fatal.
    tech_name_task = asyncio.create_task(
        _fetch_current_technology_names(client, fast_model, types, manufacturer, club)
    )

    # --- Krok 2b: live scraping footy-headlines.com via url_context ---
    slug = _club_to_footy_headlines_slug(club)
    kits_url = f"https://www.footy-headlines.com/{slug}-kits/"
    logger.info("[KIT_CONTEXT] Próba url_context: %s", kits_url)

    kit_context = await _fetch_via_url_context(client, fast_model, types, kits_url, identification)

    if kit_context:
        logger.info("[KIT_CONTEXT] url_context ok (%d znaków)", len(kit_context))
    else:
        # --- Fallback: Google Search ---
        logger.info("[KIT_CONTEXT] url_context nieudany — fallback na Google Search")
        kit_context = await _fetch_via_google_search(client, fast_model, types, identification)
        if kit_context:
            logger.info("[KIT_CONTEXT] Google Search ok (%d znaków)", len(kit_context))

    trophy_context = await trophy_task
    if trophy_context:
        logger.info("[KIT_CONTEXT] Trophy search ok (%d znaków)", len(trophy_context))

    tech_name_context = await tech_name_task
    if tech_name_context:
        logger.info("[KIT_CONTEXT] Technology name search ok (%d znaków)", len(tech_name_context))

    # Trophy + tech-name context na początku (krótsze, decyzyjnie ważniejsze) —
    # przeżyją ewentualne ucięcie extra_context[:4000] w agent_a_gemini.py, nawet
    # jeśli opis kroju jest długi. Tylko te dwa krótkie/decyzyjne bloki są tu
    # ograniczone do _MAX_CONTEXT_BLOCK_CHARS (code review, 2026-09-04) — kit_context
    # celowo NIE jest capowany tutaj, bo to on ma być tym, co outer extra_context[:4000]
    # obcina jako pierwsze w normalnym przypadku. Bez tego capu dwa nieograniczone
    # bloki mogłyby w skrajnym przypadku razem przekroczyć 4000 znaków i uciąć drugi
    # blok w połowie, łamiąc marker "CONFIRMED CURRENT TECHNOLOGY NAMES:", którego
    # szuka Agent A.
    trophy_context = trophy_context[:_MAX_CONTEXT_BLOCK_CHARS] if trophy_context else trophy_context
    tech_name_context = tech_name_context[:_MAX_CONTEXT_BLOCK_CHARS] if tech_name_context else tech_name_context
    parts_out = [p for p in (trophy_context, tech_name_context, kit_context) if p]
    return "\n\n".join(parts_out)


async def _fetch_recent_trophies(client, model: str, types, club: str) -> str:
    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=f"Club: {club}")])],
            config=types.GenerateContentConfig(
                system_instruction=_TROPHY_SEARCH_PROMPT,
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = (resp.text or "").strip()
        if "RECENT CONFIRMED TITLES:" in text:
            return text
        return ""
    except Exception as e:
        logger.warning("[KIT_CONTEXT] Trophy search error: %s", e)
        return ""


async def _fetch_current_technology_names(client, model: str, types, manufacturer: str, club: str) -> str:
    manufacturer = (manufacturer or "").strip()
    if not manufacturer or manufacturer.lower() in ("unknown", "other"):
        return ""
    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=f"Manufacturer: {manufacturer}\nClub: {club}")])],
            config=types.GenerateContentConfig(
                system_instruction=_build_tech_name_search_prompt(),
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = (resp.text or "").strip()
        if "CONFIRMED CURRENT TECHNOLOGY NAMES:" in text:
            return text
        return ""
    except Exception as e:
        logger.warning("[KIT_CONTEXT] Technology name search error: %s", e)
        return ""


async def _fetch_via_url_context(client, model: str, types, url: str, identification: str) -> str:
    prompt = (
        f"Jersey identification:\n{identification}\n\n"
        f"Read the kit page at {url} and extract kit descriptions for ALL seasons listed, "
        f"focusing on the 4 most recent seasons."
    )
    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=_SCRAPE_PROMPT,
                temperature=0.1,
                tools=[types.Tool(url_context=types.UrlContext())],
            ),
        )
        text = (resp.text or "").strip()
        if "OFFICIAL KIT CONTEXT:" in text and len(text) > 200:
            return text
        return ""
    except Exception as e:
        logger.warning("[KIT_CONTEXT] url_context error: %s", e)
        return ""


async def _fetch_via_google_search(client, model: str, types, identification: str) -> str:
    labels = [_season_label(y) for y in _current_season_start_years(3)]
    search_input = (
        f"Jersey identification:\n{identification}\n\n"
        f"NOTE: season_guess may be wrong — manufacturers reuse similar designs across seasons. "
        f"Search for ALL recent seasons ({', '.join(labels)})."
    )
    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=search_input)])],
            config=types.GenerateContentConfig(
                system_instruction=_build_search_fallback_prompt(),
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = (resp.text or "").strip()
        if "OFFICIAL KIT CONTEXT:" in text:
            return text
        return ""
    except Exception as e:
        logger.warning("[KIT_CONTEXT] Google Search error: %s", e)
        return ""
