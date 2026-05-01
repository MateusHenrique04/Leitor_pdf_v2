"""
core/dictionary.py
------------------
Busca definições de palavras.
  - Português : Wiktionary PT  (cobertura excelente)
  - Inglês    : Free Dictionary API  (api.dictionaryapi.dev)
  - Espanhol  : Free Dictionary API  (api.dictionaryapi.dev)
"""

import urllib.request
import urllib.parse
import json
import re
import html


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _clean_word(word: str) -> str:
    """Remove pontuação e normaliza para busca."""
    return re.sub(r"[^\w\-']", "", word).strip().lower()


def _strip_html(text: str) -> str:
    """Remove tags HTML e decodifica entidades."""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _get(url: str) -> bytes | None:
    """Faz GET simples com timeout. Retorna bytes ou None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lector/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status == 200:
                return r.read()
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────
# Backends
# ──────────────────────────────────────────────────────────────────

def _lookup_wiktionary_pt(word: str) -> dict | None:
    """
    Busca no Wiktionary PT via REST API.
    Endpoint: https://pt.wiktionary.org/api/rest_v1/page/definition/{word}
    """
    url = f"https://pt.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(word)}"
    raw = _get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None

    # A API retorna dict de idiomas; chave "pt" para Português
    lang_data = data.get("pt") or data.get("en") or next(iter(data.values()), [])
    if not lang_data:
        return None

    meanings = []
    for entry in lang_data:
        pos = entry.get("partOfSpeech", "")
        defs = []
        for d in entry.get("definitions", [])[:3]:
            definition = _strip_html(d.get("definition", ""))
            if definition:
                defs.append(definition)
        if defs:
            meanings.append({"part_of_speech": pos, "definitions": defs})

    if not meanings:
        return None

    return {
        "word":     word,
        "phonetic": None,
        "lang":     "pt-BR",
        "meanings": meanings,
    }


def _lookup_free_dict(word: str, lang: str) -> dict | None:
    """
    Busca na Free Dictionary API.
    Boa para EN e ES.
    """
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

    entry = data[0]
    phonetic = entry.get("phonetic") or ""
    if not phonetic:
        for p in entry.get("phonetics", []):
            if p.get("text"):
                phonetic = p["text"]
                break

    meanings = []
    for m in entry.get("meanings", []):
        pos  = m.get("partOfSpeech", "")
        defs = [d["definition"] for d in m.get("definitions", [])[:3] if d.get("definition")]
        if defs:
            meanings.append({"part_of_speech": pos, "definitions": defs})

    if not meanings:
        return None

    return {
        "word":     entry.get("word", word),
        "phonetic": phonetic or None,
        "lang":     lang,
        "meanings": meanings,
    }


# ──────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────

def lookup(word: str, detected_lang: str | None = None) -> dict | None:
    """
    Busca a definição de uma palavra.
    Ordem de tentativa: PT (Wiktionary) → EN → ES.
    Se detected_lang for passado, esse idioma vai primeiro.

    Retorna dict com:
        word        : str
        phonetic    : str | None
        lang        : str
        meanings    : list[{part_of_speech, definitions: list[str]}]
    """
    clean = _clean_word(word)
    if not clean or len(clean) < 2:
        return None

    # Sempre tenta PT primeiro (idioma principal do app)
    result = _lookup_wiktionary_pt(clean)
    if result:
        return result

    # Fallback: EN
    result = _lookup_free_dict(clean, "en")
    if result:
        return result

    # Fallback: ES
    result = _lookup_free_dict(clean, "es")
    if result:
        return result

    return None


def detect_lang(text: str) -> str | None:
    """Detecta idioma do texto. Retorna 'pt-BR', 'en', 'es' ou None."""
    try:
        from langdetect import detect
        code = detect(text)
        return {"pt": "pt-BR", "en": "en", "es": "es"}.get(code)
    except Exception:
        return None

