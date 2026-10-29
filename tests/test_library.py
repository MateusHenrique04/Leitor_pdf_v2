"""
Testes de data/library.py — isola cada teste apontando config.LIBRARY_FILE
para um arquivo em tmp_path e zerando o cache do módulo entre testes.
"""
import json

import pytest

import config
import data.library as lib


@pytest.fixture(autouse=True)
def _isolate_library_file(tmp_path, monkeypatch):
    # data/library.py faz "from config import LIBRARY_FILE" — o nome
    # fica ligado ao módulo library, não a config; por isso o monkeypatch
    # tem que mirar lib.LIBRARY_FILE, e não só config.LIBRARY_FILE.
    library_file = tmp_path / "library.json"
    monkeypatch.setattr(lib, "LIBRARY_FILE", library_file)
    monkeypatch.setattr(config, "LIBRARY_FILE", library_file)
    lib._cache = None
    yield
    lib._cache = None


def test_add_creates_entry_with_defaults():
    lib.add("book.pdf")
    assert lib.get("book.pdf") == {"last_page": 0}


def test_add_twice_does_not_overwrite_progress():
    lib.add("book.pdf")
    lib.save_position("book.pdf", 5, 2)
    lib.add("book.pdf")   # reabrir o mesmo livro não deve resetar o progresso
    assert lib.get("book.pdf")["last_page"] == 5


def test_remove_deletes_entry():
    lib.add("book.pdf")
    lib.remove("book.pdf")
    assert lib.get("book.pdf") == {}


def test_remove_unknown_path_is_a_noop():
    lib.remove("nao-existe.pdf")   # não deve lançar
    assert lib.all_books() == {}


def test_save_position_updates_page_and_chunk():
    lib.add("book.pdf")
    lib.save_position("book.pdf", 10, 3)
    meta = lib.get("book.pdf")
    assert meta["last_page"] == 10
    assert meta["last_chunk_idx"] == 3


def test_save_position_on_unknown_book_is_a_noop():
    lib.save_position("nao-existe.pdf", 10, 3)
    assert lib.get("nao-existe.pdf") == {}


def test_save_total_sets_total_pages():
    lib.add("book.pdf")
    lib.save_total("book.pdf", 42)
    assert lib.get("book.pdf")["total_pages"] == 42


def test_mark_finished_toggle_and_is_finished():
    lib.add("book.pdf")
    assert lib.is_finished("book.pdf") is False
    lib.mark_finished("book.pdf", True)
    assert lib.is_finished("book.pdf") is True
    lib.mark_finished("book.pdf", False)
    assert lib.is_finished("book.pdf") is False


def test_is_finished_unknown_book_returns_false():
    assert lib.is_finished("nao-existe.pdf") is False


def test_all_books_returns_everything_added():
    lib.add("a.pdf")
    lib.add("b.pdf")
    assert set(lib.all_books().keys()) == {"a.pdf", "b.pdf"}


def test_persists_to_disk_after_every_change():
    lib.add("book.pdf")
    saved = json.loads(config.LIBRARY_FILE.read_text(encoding="utf-8"))
    assert "book.pdf" in saved

    lib.save_position("book.pdf", 7, 1)
    saved = json.loads(config.LIBRARY_FILE.read_text(encoding="utf-8"))
    assert saved["book.pdf"]["last_page"] == 7

    lib.remove("book.pdf")
    saved = json.loads(config.LIBRARY_FILE.read_text(encoding="utf-8"))
    assert "book.pdf" not in saved
