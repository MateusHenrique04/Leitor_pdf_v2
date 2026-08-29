"""
Testes de core/dictionary.py — cobre a distinção "sem internet" vs.
"palavra não encontrada" e o TTL do cache negativo, adicionados na
auditoria de código (antes não havia nenhum teste para os parsers nem
para o comportamento de cache/rede).
"""
import json

import pytest

from core import dictionary as dic


@pytest.fixture(autouse=True)
def _clear_cache():
    """Cada teste começa com o cache de dicionário vazio."""
    dic._dict_cache.clear()
    yield
    dic._dict_cache.clear()


def test_clean_word_strips_punctuation():
    assert dic._clean_word("  Casa!! ") == "casa"
    assert dic._clean_word("café-com-leite") == "café-com-leite"


def test_normalize_slug_removes_accents():
    assert dic._normalize_slug("Café") == "cafe"
    assert dic._normalize_slug("Ação") == "acao"


def test_lookup_too_short_returns_none():
    assert dic.lookup("a") is None
    assert dic.lookup("") is None


def test_lookup_network_error_returns_marker_and_does_not_cache(monkeypatch):
    def _raise_network_error(*_args, **_kwargs):
        raise dic.DictionaryNetworkError("timeout")

    monkeypatch.setattr(dic, "_lookup_dicio", _raise_network_error)
    monkeypatch.setattr(dic, "_lookup_wiktionary_pt", _raise_network_error)
    monkeypatch.setattr(dic, "_lookup_free_dict", _raise_network_error)

    result = dic.lookup("palavra")
    assert result == {"_network_error": True}
    # Erro de rede não fica em cache — permite nova tentativa depois.
    assert "palavra:None" not in dic._dict_cache


def test_lookup_not_found_is_cached_as_none(monkeypatch):
    monkeypatch.setattr(dic, "_lookup_dicio", lambda _w: None)
    monkeypatch.setattr(dic, "_lookup_wiktionary_pt", lambda _w: None)
    monkeypatch.setattr(dic, "_lookup_free_dict", lambda _w, _l: None)

    result = dic.lookup("inexistente")
    assert result is None
    cached_value, expires_at = dic._dict_cache["inexistente:None"]
    assert cached_value is None
    assert expires_at is not None   # cache negativo tem TTL, não é permanente


def test_lookup_found_result_is_cached_without_ttl(monkeypatch):
    fake_result = {
        "word": "casa", "phonetic": None, "lang": "pt-BR",
        "source": "dicio.com.br", "meanings": [{"part_of_speech": "s.f.", "definitions": ["moradia"]}],
    }
    monkeypatch.setattr(dic, "_lookup_dicio", lambda _w: fake_result)

    result = dic.lookup("casa")
    assert result == fake_result
    cached_value, expires_at = dic._dict_cache["casa:None"]
    assert cached_value == fake_result
    assert expires_at is None   # resultado positivo não expira


def test_lookup_uses_cache_on_second_call(monkeypatch):
    calls = {"n": 0}

    def _dicio(_w):
        calls["n"] += 1
        return {"word": "casa", "phonetic": None, "lang": "pt-BR",
                "source": "dicio.com.br", "meanings": [{"part_of_speech": "s.f.", "definitions": ["moradia"]}]}

    monkeypatch.setattr(dic, "_lookup_dicio", _dicio)
    dic.lookup("casa")
    dic.lookup("casa")
    assert calls["n"] == 1


def test_lookup_free_dict_parses_response(monkeypatch):
    payload = json.dumps([{
        "word": "house",
        "phonetic": "/haʊs/",
        "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "a building for habitation"}]}],
    }]).encode("utf-8")

    monkeypatch.setattr(dic, "_get", lambda _url: payload)

    result = dic._lookup_free_dict("house", "en")
    assert result["word"] == "house"
    assert result["phonetic"] == "/haʊs/"
    assert result["meanings"][0]["part_of_speech"] == "noun"


def test_lookup_free_dict_no_response_returns_none(monkeypatch):
    monkeypatch.setattr(dic, "_get", lambda _url: None)
    assert dic._lookup_free_dict("xyz", "en") is None
