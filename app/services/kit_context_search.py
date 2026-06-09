"""
Kit Context Search — wstrzykuje aktualną wiedzę o oficjalnych krojach przed analizą Agent A.

Krok 1: Szybki Gemini call — identyfikuje klub i producenta z obrazów.
Krok 2: Gemini z url_context czyta footy-headlines.com bezpośrednio (live scraping),
         wyciąga opisy designu dla ostatnich 3 sezonów per typ koszulki.
Fallback: jeśli url_context zawiedzie, Google Search jak poprzednio.

Non-fatal — błąd zwraca pusty string.
"""

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

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

_SEARCH_FALLBACK_PROMPT = """You are a football kit authenticity researcher with access to Google Search.

Jersey identification data provided. The season_guess may be UNRELIABLE — manufacturers reuse designs.

MANDATORY searches — run ALL:
1. "site:footy-headlines.com [club] [manufacturer] 2025"
2. "site:footy-headlines.com [club] [manufacturer] 2024"
3. "[manufacturer] [club] 2025/26 home away third kit official"
4. "[manufacturer] [club] 2024/25 home away third kit official"
5. "[manufacturer] [club] 2023/24 kit official"

For each season found, describe the VISUAL DESIGN: colors, stripe pattern, sponsor name/color, unique elements.
If two seasons look similar, state exactly what differentiates them.

Start with "OFFICIAL KIT CONTEXT:" — plain text only."""


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

    # --- Krok 2: live scraping footy-headlines.com via url_context ---
    slug = _club_to_footy_headlines_slug(club)
    kits_url = f"https://www.footy-headlines.com/{slug}-kits/"
    logger.info("[KIT_CONTEXT] Próba url_context: %s", kits_url)

    context = await _fetch_via_url_context(client, fast_model, types, kits_url, identification)

    if context:
        logger.info("[KIT_CONTEXT] url_context ok (%d znaków)", len(context))
        return context

    # --- Fallback: Google Search ---
    logger.info("[KIT_CONTEXT] url_context nieudany — fallback na Google Search")
    context = await _fetch_via_google_search(client, fast_model, types, identification)

    if context:
        logger.info("[KIT_CONTEXT] Google Search ok (%d znaków)", len(context))
    return context


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
    search_input = (
        f"Jersey identification:\n{identification}\n\n"
        f"NOTE: season_guess may be wrong — manufacturers reuse similar designs across seasons. "
        f"Search for ALL recent seasons (2023/24, 2024/25, 2025/26)."
    )
    try:
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text=search_input)])],
            config=types.GenerateContentConfig(
                system_instruction=_SEARCH_FALLBACK_PROMPT,
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
