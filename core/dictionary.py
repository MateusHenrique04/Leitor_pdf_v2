"""
core/dictionary.py
------------------
Busca definições de palavras.

  PT-BR : dicio.com.br  (scraping com requests+bs4 — cobertura excelente)
          Wiktionary PT (fallback via REST API com UA de browser)
  EN    : Free Dictionary API (api.dictionaryapi.dev)
  ES    : Free Dictionary API (api.dictionaryapi.dev)

Dependências adicionais (adicione ao requirements.txt):
    requests
    beautifulsoup4
"""

import json
import re
import html as html_mod
import unicodedata

# Usa requests se disponível (melhor handling de cookies/UA/redirects)
# Fallback para urllib se não tiver
try:
    import requests as _requests
    _SESSION = _requests.Session()
    _SESSION.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    import urllib.request
    import urllib.parse

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _clean_word(word: str) -> str:
    return re.sub(r"[^\w\-']", "", word).strip().lower()


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(text).strip()


def _normalize_slug(word: str) -> str:
    """Converte para slug do dicio: minúsculas, sem acento, só letras e hífen."""
    nfkd = unicodedata.normalize("NFKD", word.lower())
    ascii_word = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z\-]", "", ascii_word)


def _get(url: str) -> bytes | None:
    """GET com User-Agent de browser. Retorna bytes ou None."""
    if _HAS_REQUESTS:
        try:
            r = _SESSION.get(url, timeout=6)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass
        return None
    else:
        # fallback urllib — User-Agent de browser para evitar 403
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "pt-BR,pt;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=6) as r:
                if r.status == 200:
                    return r.read()
        except Exception:
            pass
        return None


# ──────────────────────────────────────────────────────────────────
# Backends
# ──────────────────────────────────────────────────────────────────

def _lookup_dicio(word: str) -> dict | None:
    """
    Scraping do dicio.com.br.
    Melhor cobertura para PT-BR: arcaísmos, gírias, termos literários.
    Requer: requests + beautifulsoup4
    """
    if not _HAS_BS4:
        return None

    slug = _normalize_slug(word)
    if not slug:
        return None

    raw = _get(f"https://www.dicio.com.br/{slug}/")
    if not raw:
        return None

    try:
        soup = BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")
    except Exception:
        return None

    # Página "não encontrada" tem elemento específico
    if soup.find("p", class_="found") or soup.find("div", id="word-not-found"):
        return None

    meanings: list[dict] = []

    for p in soup.find_all("p", class_="significado"):
        # Classe gramatical fica em <span class="cl">
        cl_tag = p.find("span", class_="cl")
        pos = cl_tag.get_text(strip=True) if cl_tag else ""
        if cl_tag:
            cl_tag.decompose()

        # Remove <span class="tag"> (ex: [Figurado])
        for tag in p.find_all("span", class_="tag"):
            tag.decompose()

        raw_text = p.get_text(separator=" ").strip()
        raw_text = re.sub(r"\s{2,}", "  ", raw_text)

        # Separa definições numeradas (1. 2. ...) ou por duplo espaço
        parts = re.split(r"\s*\d+\.\s+", raw_text)
        if len(parts) == 1:
            parts = raw_text.split("  ")

        defs = [d.strip().rstrip(".").strip() for d in parts if len(d.strip()) > 5]

        if defs:
            meanings.append({"part_of_speech": pos, "definitions": defs[:4]})

    if not meanings:
        return None

    return {
        "word":     word,
        "phonetic": None,
        "lang":     "pt-BR",
        "source":   "dicio.com.br",
        "meanings": meanings,
    }


def _lookup_wiktionary_pt(word: str) -> dict | None:
    """Wiktionary PT via REST API — fallback quando dicio não encontra."""
    if _HAS_REQUESTS:
        url = f"https://pt.wiktionary.org/api/rest_v1/page/definition/{word}"
    else:
        import urllib.parse
        url = f"https://pt.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(word)}"

    raw = _get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None

    lang_data = data.get("pt") or data.get("en") or next(iter(data.values()), [])
    if not lang_data:
        return None

    meanings = []
    for entry in lang_data:
        pos  = entry.get("partOfSpeech", "")
        defs = [
            _strip_html(d.get("definition", ""))
            for d in entry.get("definitions", [])[:3]
            if d.get("definition")
        ]
        defs = [d for d in defs if d]
        if defs:
            meanings.append({"part_of_speech": pos, "definitions": defs})

    if not meanings:
        return None

    return {
        "word":     word,
        "phonetic": None,
        "lang":     "pt-BR",
        "source":   "wiktionary",
        "meanings": meanings,
    }


def _lookup_free_dict(word: str, lang: str) -> dict | None:
    """Free Dictionary API — EN e ES."""
    if _HAS_REQUESTS:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}"
    else:
        import urllib.parse
        url = f"https://api.dictionaryapi.dev/api/v2/entries/{lang}/{urllib.parse.quote(word)}"

    raw = _get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None

    entry    = data[0]
    phonetic = entry.get("phonetic") or ""
    if not phonetic:
        for p in entry.get("phonetics", []):
            if p.get("text"):
                phonetic = p["text"]
                break

    meanings = []
    for m in entry.get("meanings", []):
        pos  = m.get("partOfSpeech", "")
        defs = [
            d["definition"]
            for d in m.get("definitions", [])[:3]
            if d.get("definition")
        ]
        if defs:
            meanings.append({"part_of_speech": pos, "definitions": defs})

    if not meanings:
        return None

    return {
        "word":     entry.get("word", word),
        "phonetic": phonetic or None,
        "lang":     lang,
        "source":   "freedictionary",
        "meanings": meanings,
    }


# ──────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────

def lookup(word: str, detected_lang: str | None = None) -> dict | None:
    """
    Busca a definição de uma palavra.

    Cadeia PT-BR : dicio.com.br → Wiktionary → Free Dictionary EN
    EN direto    : Free Dictionary EN
    ES direto    : Free Dictionary ES

    Retorna dict com:
        word        : str
        phonetic    : str | None
        lang        : str
        source      : str   ('dicio.com.br' | 'wiktionary' | 'freedictionary')
        meanings    : list[{part_of_speech, definitions: list[str]}]
    Ou None se não encontrado / sem internet.
    """
    clean = _clean_word(word)
    if not clean or len(clean) < 2:
        return None

    cache_key = f"{clean}:{detected_lang}"
    if cache_key in _dict_cache:
        return _dict_cache[cache_key]

    if detected_lang == "en":
        result = _lookup_free_dict(clean, "en")
    elif detected_lang == "es":
        result = _lookup_free_dict(clean, "es")
    else:
        # PT-BR: dicio → wiktionary → en fallback
        result = _lookup_dicio(clean)
        if not result:
            result = _lookup_wiktionary_pt(clean)
        if not result:
            result = _lookup_free_dict(clean, "en")
        if not result:
            result = _lookup_free_dict(clean, "es")

    _dict_cache[cache_key] = result
    return result


def detect_lang(text: str) -> str | None:
    """Detecta idioma do texto. Retorna 'pt-BR', 'en', 'es' ou None."""
    try:
        from langdetect import detect
        code = detect(text)
        return {"pt": "pt-BR", "en": "en", "es": "es"}.get(code)
    except Exception:
        return None