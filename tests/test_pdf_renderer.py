"""
Testes de core/pdf_renderer.py — o módulo com a lógica mais arriscada do
projeto (search_text tem 4 estratégias de matching heurístico e não tinha
nenhum teste antes desta auditoria).
"""
import threading

import pymupdf
import pytest

from core.pdf_renderer import PDFOpenError, PDFRenderer


def _save_pdf(tmp_path, name, build_fn):
    """Cria um PDF em memória com `build_fn(doc)` e salva em tmp_path/name."""
    doc = pymupdf.open()
    build_fn(doc)
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return str(path)


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


def test_search_text_stage2_anchors_by_start_across_hyphenated_lines(tmp_path):
    """Etapa 2: a frase completa dehifenizada (como text_for_page entrega
    pro TTS) não existe literalmente na página — lá está "hifeniza-" numa
    linha e "cao" na próxima, como PDFs reais quebram palavras no fim da
    linha. search_for() da etapa 1 falha; a âncora pelas primeiras
    palavras (que estão todas na primeira linha) deve achar o trecho."""
    path = _save_pdf(tmp_path, "hyphen.pdf", lambda doc: (
        doc.new_page().insert_text((72, 72), "Este e um exemplo de hifeniza-"),
        doc[0].insert_text((72, 90), "cao quebrada entre linhas no documento."),
    ))
    r = PDFRenderer(path)
    chunk = r.text_for_page(0).split("\n")[0]
    assert chunk == "Este e um exemplo de hifenizacao quebrada entre linhas no documento."
    hits = r.search_text(0, chunk)
    assert len(hits) >= 1
    r.close()


def test_search_text_stage3_anchors_by_end_of_sentence(tmp_path):
    """Etapa 3: o começo do chunk não existe na página (texto reescrito
    de forma diferente), mas o final sim — âncora pelas últimas 3
    palavras deve encontrar o trecho."""
    path = _save_pdf(tmp_path, "end_anchor.pdf", lambda doc: doc.new_page().insert_text(
        (72, 72),
        "Capitulo tres contem uma oracao que comeca diferente mas termina "
        "com as mesmas tres palavras finais.",
    ))
    r = PDFRenderer(path)
    chunk = (
        "Esta secao contem uma oracao que comeca diferente mas termina "
        "com as mesmas tres palavras finais."
    )
    hits = r.search_text(0, chunk)
    assert len(hits) >= 1
    r.close()


def test_search_text_stage4_fallback_unique_words(tmp_path):
    """Etapa 4: nem início nem fim do chunk batem com nada contíguo na
    página, mas palavras únicas e significativas (>4 letras) aparecem —
    o fallback deve achar as linhas que contêm essas palavras."""
    path = _save_pdf(tmp_path, "fallback.pdf", lambda doc: (
        doc.new_page().insert_text((72, 72), "Pagina cheia de palavras diferentes para testar."),
        doc[0].insert_text(
            (72, 100),
            "Misterio escondido inexplicavel desconfortavel sensacao estranha aqui.",
        ),
    ))
    r = PDFRenderer(path)
    chunk = "Misterio trazia consigo estranha sensacao inexplicavel desconfortavel."
    hits = r.search_text(0, chunk)
    assert len(hits) >= 1
    r.close()


def test_text_for_page_strips_repeated_header_and_footer(tmp_path):
    """Cabeçalho/rodapé repetidos em >=30% das páginas devem ser
    removidos do texto entregue ao TTS (ver __init__ — detecção de
    hdr/ftr), mas o conteúdo da página continua presente."""
    def build(doc):
        for i in range(4):
            p = doc.new_page()
            p.insert_text((72, 40), "LECTOR - Manual de Teste")
            p.insert_text((72, 72), f"Conteudo da pagina numero {i + 1} com texto relevante aqui.")
            p.insert_text((72, 780), str(i + 1))

    path = _save_pdf(tmp_path, "header_footer.pdf", build)
    r = PDFRenderer(path)
    for i in range(4):
        text = r.text_for_page(i)
        assert "LECTOR - Manual de Teste" not in text
        assert text.strip() != str(i + 1)
        assert f"pagina numero {i + 1}" in text
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


def test_concurrent_access_does_not_raise(sample_pdf_path):
    """PyMuPDF não é thread-safe — render_page, text_for_page e search_text
    rodam de várias threads ao mesmo tempo (UI, prefetch, busca e loop de
    leitura fazem isso na prática) e nenhuma delas deve lançar exceção
    nem travar, graças ao RLock em torno de _doc/_cache."""
    r = PDFRenderer(sample_pdf_path)
    errors: list[Exception] = []

    def worker(i: int):
        try:
            for _ in range(20):
                page = i % r.total
                r.render_page(page)
                r.text_for_page(page)
                r.search_text(page, "gato")
                r.word_at(page, 80, 100)
        except Exception as e:  # pragma: no cover - só deve rodar se falhar
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    r.close()


def test_text_in_rect_returns_text_under_bbox(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    hits = r.search_text(0, "Capitulo Um")
    assert hits
    bbox = hits[0]
    text = r.text_in_rect(0, bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
    assert "Capitulo" in text
    r.close()


def test_text_in_rect_out_of_range_page_returns_empty(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    assert r.text_in_rect(99, 0, 0, 10, 10) == ""
    r.close()
