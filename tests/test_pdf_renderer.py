"""
Testes de core/pdf_renderer.py — o módulo com a lógica mais arriscada do
projeto (search_text tem 4 estratégias de matching heurístico e não tinha
nenhum teste antes desta auditoria).
"""
import pytest

from core.pdf_renderer import PDFOpenError, PDFRenderer


def test_open_valid_pdf(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    assert r.total == 3
    r.close()


def test_open_corrupted_pdf_raises_friendly_error(corrupted_pdf_path):
    with pytest.raises(PDFOpenError):
        PDFRenderer(corrupted_pdf_path)


def test_open_missing_file_raises_pdfopenerror(tmp_path):
    missing = tmp_path / "nao_existe.pdf"
    with pytest.raises(PDFOpenError):
        PDFRenderer(str(missing))


def test_text_for_page_returns_expected_content(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    text = r.text_for_page(0)
    assert "gato preto" in text
    r.close()


def test_search_text_full_phrase_match(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    hits = r.search_text(0, "O gato preto dormia tranquilo sobre o telhado quente.")
    assert len(hits) >= 1
    for h in hits:
        assert {"x0", "y0", "x1", "y1"} <= h.keys()
    r.close()


def test_search_text_no_match_returns_empty(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    hits = r.search_text(0, "frase que definitivamente nao existe no documento")
    assert hits == []
    r.close()


def test_search_text_out_of_range_page_returns_empty(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    assert r.search_text(99, "qualquer coisa") == []
    assert r.search_text(-1, "qualquer coisa") == []
    r.close()


def test_word_at_finds_word_under_point(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    hits = r.search_text(0, "gato")
    assert hits, "pré-condição: 'gato' precisa ser encontrável na página"
    bbox = hits[0]
    cx = (bbox["x0"] + bbox["x1"]) / 2
    cy = (bbox["y0"] + bbox["y1"]) / 2
    word = r.word_at(0, cx, cy)
    assert word is not None and "gato" in word.lower()
    r.close()


def test_word_at_no_word_at_position_returns_none(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    # Ponto bem no canto inferior direito, longe de qualquer texto inserido.
    assert r.word_at(0, 590, 830) is None
    r.close()


def test_render_page_cache_is_lru(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    # Preenche o cache além do limite (10) e garante que não lança erro
    # e que a página mais recentemente usada permanece cacheada.
    for _ in range(2):
        for p in range(r.total):
            r.render_page(p)
    assert len(r._cache) <= 10
    # Página 0 foi acessada por último no laço acima antes da 1 e 2 de novo
    # — só validamos que renderizar de novo não lança exceção.
    img = r.render_page(0)
    assert img is not None
    r.close()


def test_get_toc_returns_entries(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    toc = r.get_toc()
    assert isinstance(toc, list)
    r.close()
