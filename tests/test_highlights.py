"""
Testes de data/highlights.py — grifos agora são identificados por "id"
(uuid4) em vez do índice na lista, e um highlights.json antigo sem "id"
deve ser migrado sem perder dados.

Isola cada teste apontando config.HIGHLIGHTS_FILE para um arquivo em
tmp_path e zerando o cache do módulo (_cache é global).
"""
import json

import pytest

import config
import data.highlights as highlights


@pytest.fixture(autouse=True)
def _isolate_highlights_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HIGHLIGHTS_FILE", tmp_path / "highlights.json")
    highlights._cache = None
    yield
    highlights._cache = None


def test_add_returns_id_and_persists(tmp_path):
    hid = highlights.add("book.pdf", 1, 0, 0, 10, 10)
    assert hid is not None
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert saved["book.pdf"]["1"][0]["id"] == hid


def test_add_duplicate_within_margin_returns_none():
    first = highlights.add("book.pdf", 1, 0, 0, 10, 10)
    dup = highlights.add("book.pdf", 1, 0.5, 0.5, 10.5, 10.5)
    assert first is not None
    assert dup is None
    assert len(highlights.get("book.pdf", 1)) == 1


def test_delete_by_id_removes_only_that_highlight():
    id1 = highlights.add("book.pdf", 1, 0, 0, 10, 10)
    id2 = highlights.add("book.pdf", 1, 100, 100, 110, 110)
    highlights.delete("book.pdf", 1, id1)
    remaining = highlights.get("book.pdf", 1)
    assert len(remaining) == 1
    assert remaining[0]["id"] == id2


def test_delete_unknown_id_is_a_noop():
    highlights.add("book.pdf", 1, 0, 0, 10, 10)
    highlights.delete("book.pdf", 1, "id-que-nao-existe")
    assert len(highlights.get("book.pdf", 1)) == 1


def test_delete_order_independent():
    """Apagar pelo id funciona mesmo se a lista for reordenada entre
    desenhar e apagar — o ponto de ter saído do índice posicional."""
    id1 = highlights.add("book.pdf", 1, 0, 0, 10, 10)
    id2 = highlights.add("book.pdf", 1, 100, 100, 110, 110)
    page_list = highlights.get("book.pdf", 1)
    page_list.reverse()   # simula a ordem mudando
    highlights.delete("book.pdf", 1, id2)
    remaining = highlights.get("book.pdf", 1)
    assert [h["id"] for h in remaining] == [id1]


def test_migrates_old_file_without_ids(tmp_path):
    old_data = {
        "book.pdf": {
            "1": [
                {"x0": 0, "y0": 0, "x1": 10, "y1": 10, "color": "#FFDD00", "opacity": 0.35},
                {"x0": 20, "y0": 20, "x1": 30, "y1": 30, "color": "#FFDD00", "opacity": 0.35},
            ]
        }
    }
    config.HIGHLIGHTS_FILE.write_text(json.dumps(old_data), encoding="utf-8")
    highlights._cache = None

    page_list = highlights.get("book.pdf", 1)
    assert len(page_list) == 2
    ids = [h["id"] for h in page_list]
    assert all(ids)
    assert len(set(ids)) == 2   # ids únicos

    # A migração já deve ter sido persistida em disco.
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert all("id" in h for h in saved["book.pdf"]["1"])
    # Nenhum dado original foi perdido.
    assert saved["book.pdf"]["1"][0]["x0"] == 0
    assert saved["book.pdf"]["1"][1]["x1"] == 30


def test_clear_page_removes_only_that_page():
    highlights.add("book.pdf", 1, 0, 0, 10, 10)
    highlights.add("book.pdf", 2, 0, 0, 10, 10)
    highlights.clear_page("book.pdf", 1)
    assert highlights.get("book.pdf", 1) == []
    assert len(highlights.get("book.pdf", 2)) == 1


def test_clear_page_on_book_without_highlights_is_a_noop():
    highlights.clear_page("book-sem-grifos.pdf", 1)   # não deve lançar


def test_clear_book_removes_all_pages():
    highlights.add("book.pdf", 1, 0, 0, 10, 10)
    highlights.add("book.pdf", 2, 0, 0, 10, 10)
    highlights.add("outro.pdf", 1, 0, 0, 10, 10)
    highlights.clear_book("book.pdf")
    assert highlights.all_for_book("book.pdf") == {}
    assert len(highlights.get("outro.pdf", 1)) == 1


def test_persists_to_disk_after_every_change():
    """Cada função que altera grifos persiste imediatamente — grifos não
    dependem do usuário fechar o app normalmente para não serem perdidos."""
    hid = highlights.add("book.pdf", 1, 0, 0, 10, 10)
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert saved["book.pdf"]["1"][0]["id"] == hid

    highlights.add("book.pdf", 1, 100, 100, 110, 110)
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert len(saved["book.pdf"]["1"]) == 2

    highlights.delete("book.pdf", 1, hid)
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert len(saved["book.pdf"]["1"]) == 1

    highlights.clear_page("book.pdf", 1)
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert saved["book.pdf"].get("1", []) == []

    highlights.add("book.pdf", 2, 0, 0, 10, 10)
    highlights.clear_book("book.pdf")
    saved = json.loads(config.HIGHLIGHTS_FILE.read_text(encoding="utf-8"))
    assert "book.pdf" not in saved
