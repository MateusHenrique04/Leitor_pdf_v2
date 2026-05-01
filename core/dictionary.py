"""
core/dictionary.py
------------------
Busca definições de palavras usando a Free Dictionary API.
Suporte: pt-BR (principal), en (secundário), es (terciário).
"""

import urllib.request
import urllib.parse
import json
import re

# Prioridade de idiomas
LANG_PRIORITY = ["pt-BR", "en", "es"]
API_BASE = "https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}"


def _clean_word(word: str) -> str:
    """Remove pontuação e normaliza a palavra para busca."""
    return re.sub(r"[^\w\-']", "", word).strip().lower()


def _fetch(lang: str, word: str) -> dict | None:
    """Faz requisição à API. Retorna dict com dados ou None se não encontrado."""
    url = API_BASE.format(lang=lang, word=urllib.parse.quote(word))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lector/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                if isinstance(data, list) and data:
                    return data[0]
    except Exception:
        pass
    return None


def lookup(word: str, detected_lang: str | None = None) -> dict | None:
    """
    Busca a definição de uma palavra.
    Tenta o idioma detectado primeiro, depois percorre LANG_PRIORITY.

    Retorna dict com:
        word        : str
        phonetic    : str | None
        lang        : str  (idioma encontrado)
        meanings    : list[{part_of_speech, definitions: list[str]}]
    Retorna None se nenhum idioma retornar resultado.
    """
    clean = _clean_word(word)
    if not clean:
        return None

    order = []
    if detected_lang and detected_lang not in LANG_PRIORITY:
        order.append(detected_lang)
    if detected_lang and detected_lang in LANG_PRIORITY:
        order = [detected_lang] + [l for l in LANG_PRIORITY if l != detected_lang]
    else:
        order = LANG_PRIORITY[:]

    for lang in order:
        data = _fetch(lang, clean)
        if not data:
            continue

        phonetic = data.get("phonetic") or ""
        if not phonetic:
            for p in data.get("phonetics", []):
                if p.get("text"):
                    phonetic = p["text"]
                    break

        meanings = []
        for m in data.get("meanings", []):
            pos   = m.get("partOfSpeech", "")
            defs  = [d["definition"] for d in m.get("definitions", [])[:3] if d.get("definition")]
            if defs:
                meanings.append({"part_of_speech": pos, "definitions": defs})

        if meanings:
            return {
                "word":     data.get("word", clean),
                "phonetic": phonetic or None,
                "lang":     lang,
                "meanings": meanings,
            }

    return None


def detect_lang(text: str) -> str | None:
    """Tenta detectar o idioma do texto. Retorna código compatível com a API ou None."""
    try:
        from langdetect import detect
        code = detect(text)
        mapping = {"pt": "pt-BR", "en": "en", "es": "es"}
        return mapping.get(code)
    except Exception:
        return None
