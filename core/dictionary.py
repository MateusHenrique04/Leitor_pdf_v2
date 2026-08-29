"""
core/dictionary.py
------------------
Busca definições de palavras.

  PT-BR : dicio.com.br  (scraping com requests+bs4 — cobertura excelente)
          Wiktionary PT (fallback via REST API com UA de browser)
  EN    : Free Dictionary API (api.dictionaryapi.dev)
  ES    : Free Dictionary API (api.dictionaryapi.dev)

Dependências: requests, beautifulsoup4 (ambas em requirements.txt).
"""

import html as html_mod
import json
import logging
import re
import time
import unicodedata

log = logging.getLogger(__name__)

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
    import urllib.error
    import urllib.parse
    import urllib.request

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

_UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Cache de definições já buscadas: chave → (valor, expira_em | None).
# expira_em None = cacheado para sempre (resultado positivo real, não muda).
# Resultados negativos ("não encontrado") ficam só _NEG_CACHE_TTL segundos,
# para não travar permanentemente uma palavra que na verdade existe mas
# falhou por instabilidade momentânea de um dos backends.
_dict_cache: dict[str, tuple[dict | None, float | None]] = {}
_NEG_CACHE_TTL = 600.0   # 10 minutos


class DictionaryNetworkError(Exception):
    """Falha de rede (timeout/conexão) ao consultar um backend de dicionário —
    distinto de "palavra não encontrada", para a UI poder diferenciar as duas
    mensagens (ver core.dictionary.lookup)."""


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
    """
    GET com User-Agent de browser.
    Retorna bytes do corpo em caso de 200, None em outro status HTTP
    (ex.: 404 → "palavra não encontrada" nesse backend).
    Lança DictionaryNetworkError em falha de conexão/timeout — quem chama
    decide se propaga ou tenta o próximo backend.
    """
    if _HAS_REQUESTS:
        try:
            r = _SESSION.get(url, timeout=6)
        except (_requests.exceptions.ConnectionError, _requests.exceptions.Timeout) as e:
            log.warning("Falha de rede ao acessar %s: %s", url, e)
            raise DictionaryNetworkError(str(e)) from e
        except Exception as e:
            log.debug("Erro inesperado ao acessar %s: %s", url, e)
            return None
        if r.status_code == 200:
            return r.content
        log.debug("%s respondeu HTTP %d", url, r.status_code)
        return None
    else:
        try:
            req = urllib.request.Request(url, headers=_UA_HEADERS)
            with urllib.request.urlopen(req, timeout=6) as r:
                if r.status == 200:
                    return r.read()
                log.debug("%s respondeu HTTP %d", url, r.status)
                return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning("Falha de rede ao acessar %s: %s", url, e)
            raise DictionaryNetworkError(str(e)) from e
        except Exception as e:
            log.debug("Erro inesperado ao acessar %s: %s", url, e)
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
    except Exception as e:
        log.warning("Falha ao parsear HTML do dicio.com.br para %r: %s", word, e)
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
    except Exception as e:
        log.warning("Falha ao parsear JSON do Wiktionary para %r: %s", word, e)
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
    except Exception as e:
        log.warning("Falha ao parsear JSON do Free Dictionary (%s) para %r: %s", lang, word, e)
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

def _try(fn, *args) -> tuple[dict | None, bool]:
    """Executa `fn(*args)`, retorna (resultado, teve_erro_de_rede)."""
    try:
        return fn(*args), False
    except DictionaryNetworkError:
        return None, True


def lookup(word: str, detected_lang: str | None = None) -> dict | None:
    """
    Busca a definição de uma palavra.

    Cadeia PT-BR : dicio.com.br → Wiktionary → Free Dictionary EN → ES
    EN direto    : Free Dictionary EN
    ES direto    : Free Dictionary ES

    Retorna dict com:
        word        : str
        phonetic    : str | None
        lang        : str
        source      : str   ('dicio.com.br' | 'wiktionary' | 'freedictionary')
        meanings    : list[{part_of_speech, definitions: list[str]}]
    Retorna {"_network_error": True} se TODOS os backends tentados
    falharam por problema de rede (permite a UI mostrar "sem internet"
    em vez de "palavra não encontrada" — e não fica em cache, para que
    uma nova tentativa funcione assim que a conexão voltar).
    Retorna None se nenhum backend encontrou a palavra.
    """
    clean = _clean_word(word)
    if not clean or len(clean) < 2:
        return None

    cache_key = f"{clean}:{detected_lang}"
    cached = _dict_cache.get(cache_key)
    if cached is not None:
        value, expires_at = cached
        if expires_at is None or time.time() < expires_at:
            return value
        del _dict_cache[cache_key]

    network_errors = 0
    attempts = 0

    def attempt(fn, *args):
        nonlocal network_errors, attempts
        attempts += 1
        result, had_error = _try(fn, *args)
        if had_error:
            network_errors += 1
        return result

    if detected_lang == "en":
        result = attempt(_lookup_free_dict, clean, "en")
    elif detected_lang == "es":
        result = attempt(_lookup_free_dict, clean, "es")
    else:
        # PT-BR: dicio → wiktionary → en fallback → es fallback
        result = attempt(_lookup_dicio, clean)
        if not result:
            result = attempt(_lookup_wiktionary_pt, clean)
        if not result:
            result = attempt(_lookup_free_dict, clean, "en")
        if not result:
            result = attempt(_lookup_free_dict, clean, "es")

    if result is None and attempts > 0 and network_errors == attempts:
        log.info("Todos os backends de dicionário falharam por rede para %r.", clean)
        return {"_network_error": True}   # não cacheia — permite nova tentativa

    expires_at = (time.time() + _NEG_CACHE_TTL) if result is None else None
    _dict_cache[cache_key] = (result, expires_at)
    return result


def detect_lang(text: str) -> str | None:
    """Detecta idioma do texto. Retorna 'pt-BR', 'en', 'es' ou None."""
    try:
        from langdetect import detect
        code = detect(text)
        return {"pt": "pt-BR", "en": "en", "es": "es"}.get(code)
    except Exception as e:
        log.debug("Detecção de idioma falhou (ignorado): %s", e)
        return None
