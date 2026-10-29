"""
Testes de data/prefs.py — isola cada teste apontando config.PREFS_FILE
para um arquivo em tmp_path e zerando o cache do módulo entre testes.
"""
import json

import pytest

import config
import data.prefs as prefs


@pytest.fixture(autouse=True)
def _isolate_prefs_file(tmp_path, monkeypatch):
    # data/prefs.py faz "from config import PREFS_FILE" — o nome fica
    # ligado ao módulo prefs, não a config; por isso o monkeypatch tem
    # que mirar prefs.PREFS_FILE, e não config.PREFS_FILE.
    prefs_file = tmp_path / "prefs.json"
    monkeypatch.setattr(prefs, "PREFS_FILE", prefs_file)
    monkeypatch.setattr(config, "PREFS_FILE", prefs_file)
    prefs._cache = None
    yield
    prefs._cache = None


def test_get_all_returns_defaults_when_no_file_exists():
    all_prefs = prefs.get_all()
    assert all_prefs["voice"] is None
    assert all_prefs["autoscroll"] is True


def test_set_value_persists_and_is_read_back():
    prefs.set_value("voice", "pt-BR-AntonioNeural")
    assert prefs.get_all()["voice"] == "pt-BR-AntonioNeural"


def test_set_value_only_changes_given_key():
    prefs.set_value("zoom", 2.5)
    prefs.set_value("volume", 0.5)
    all_prefs = prefs.get_all()
    assert all_prefs["zoom"] == 2.5
    assert all_prefs["volume"] == 0.5
    assert all_prefs["autoscroll"] is True   # default intocado


def test_get_all_returns_a_copy_not_the_live_cache():
    copy1 = prefs.get_all()
    copy1["voice"] = "alterado-so-na-copia"
    assert prefs.get_all()["voice"] is None


def test_old_prefs_file_with_unknown_keys_still_loads(tmp_path):
    """Um prefs.json de uma versão anterior, com chaves que não existem
    mais em _DEFAULTS, não deve quebrar a leitura."""
    config.PREFS_FILE.write_text(
        json.dumps({"voice": "x", "chave_antiga_removida": 123}), encoding="utf-8"
    )
    prefs._cache = None
    all_prefs = prefs.get_all()
    assert all_prefs["voice"] == "x"
    assert all_prefs["chave_antiga_removida"] == 123


def test_persists_to_disk_immediately():
    prefs.set_value("speed", "rapido")
    saved = json.loads(config.PREFS_FILE.read_text(encoding="utf-8"))
    assert saved["speed"] == "rapido"
