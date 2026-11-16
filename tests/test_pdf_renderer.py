"""
Testes de core/pdf_renderer.py — o módulo com a lógica mais arriscada do
projeto (search_text tem 4 estratégias de matching heurístico e não tinha
nenhum teste antes desta auditoria).
"""
import threading

import pymupdf
import pytest

from core.pdf_renderer import _MAX_CACHED_PAGES, PDFOpenError, PDFRenderer


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


def _small_format_pdf(tmp_path):
    """PDF de formato pequeno (252x331 pt, metade de um A4) — o caso que
    saía borrado quando a renderização usava um DPI fixo."""
    def build(doc):
        page = doc.new_page(width=252, height=331)
        page.insert_text((40, 60), "meditacoes metafisicas", fontsize=9)
    return _save_pdf(tmp_path, "pequeno.pdf", build)


def test_render_page_atende_a_largura_pedida(tmp_path):
    """A página é renderizada no tamanho em que vai ser exibida, não num
    DPI fixo — senão a tela precisa AMPLIAR a imagem, e o texto borra."""
    r = PDFRenderer(_small_format_pdf(tmp_path))
    base = r.render_page(0)                 # sem alvo: DPI base
    alvo = 980
    img = r.render_page(0, alvo)
    assert base.width < alvo, "o DPI base já cobriria o alvo; teste inócuo"
    assert img.width >= alvo, "renderizou menor que a exibição: vai borrar"
    r.close()


def test_dpi_for_nunca_fica_abaixo_do_piso(tmp_path):
    """Exibição minúscula (ou desconhecida) não pode render menos que o
    DPI base — o comportamento antigo é o piso, nunca o teto."""
    from config import PDF_RENDER_DPI

    r = PDFRenderer(_small_format_pdf(tmp_path))
    assert r.dpi_for(0, None) == PDF_RENDER_DPI
    assert r.dpi_for(0, 10) == PDF_RENDER_DPI
    r.close()


def test_dpi_for_respeita_o_teto_de_pixels(tmp_path):
    """Zoom alto não pode estourar a memória: o maior lado da imagem fica
    dentro de PDF_RENDER_MAX_PX."""
    from config import PDF_RENDER_MAX_PX

    r = PDFRenderer(_small_format_pdf(tmp_path))
    img = r.render_page(0, 50_000)
    assert max(img.size) <= PDF_RENDER_MAX_PX
    r.close()


def test_cache_separa_resolucoes_da_mesma_pagina(tmp_path):
    """A mesma página em duas resoluções são duas entradas — voltar o zoom
    reaproveita o que já foi renderizado em vez de refazer."""
    r = PDFRenderer(_small_format_pdf(tmp_path))
    a = r.render_page(0, 400)
    b = r.render_page(0, 1200)
    assert a.size != b.size
    assert len(r._cache) == 2
    assert r.render_page(0, 400) is a   # veio do cache, não re-renderizou
    r.close()


def test_cache_respeita_orcamento_de_memoria(tmp_path):
    """O limite do cache é em RAM, não em número de páginas: uma página no
    zoom máximo pesa dezenas de vezes mais que a mesma no DPI base."""
    from config import PDF_RENDER_CACHE_MB

    def build(doc):
        for _ in range(6):
            doc.new_page(width=252, height=331).insert_text((40, 60), "x")

    r = PDFRenderer(_save_pdf(tmp_path, "varias.pdf", build))
    for p in range(r.total):
        r.render_page(p, 3000)
    usado = sum(im.width * im.height * 3 for im in r._cache.values())
    assert usado <= PDF_RENDER_CACHE_MB * 1024 * 1024
    assert len(r._cache) >= 1
    r.close()


def test_page_size_devolve_pontos_do_pdf(tmp_path):
    """page_size é a base da conversão ponto→pixel na UI (_img_px_per_pt);
    se mentir, grifo e clique saem do lugar."""
    r = PDFRenderer(_small_format_pdf(tmp_path))
    w, h = r.page_size(0)
    assert round(w) == 252 and round(h) == 331
    assert r.page_size(99) == (0.0, 0.0)
    r.close()


def test_render_page_cache_is_lru(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    # Reacessa as páginas e garante que não lança erro e que o cache fica
    # dentro do teto de entradas (o outro limite, de memória, tem teste
    # próprio em test_cache_respeita_orcamento_de_memoria).
    for _ in range(2):
        for p in range(r.total):
            r.render_page(p)
    assert len(r._cache) <= _MAX_CACHED_PAGES
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


# ──────────────────────────────────────────────────────────────────
# text_for_page — reflow de parágrafos
# ──────────────────────────────────────────────────────────────────

def test_text_for_page_junta_linhas_quebradas_do_mesmo_paragrafo(tmp_path):
    """O PDF guarda uma linha visual por "\n". Sem juntar, uma frase que
    ocupa três linhas virava três requisições de TTS — três pedaços com
    pausa no meio. text_for_page deve devolver a frase inteira numa linha
    só."""
    def build(doc):
        p = doc.new_page()
        p.insert_text((72, 72), "Esta frase comeca na primeira linha da")
        p.insert_text((72, 86), "pagina, continua na segunda linha e so")
        p.insert_text((72, 100), "termina aqui na terceira.")

    r = PDFRenderer(_save_pdf(tmp_path, "wrap.pdf", build))
    text = r.text_for_page(0)
    assert text.count("\n") == 0
    assert text == ("Esta frase comeca na primeira linha da pagina, "
                    "continua na segunda linha e so termina aqui na terceira.")
    r.close()


def test_text_for_page_separa_paragrafos_distintos_com_newline(tmp_path):
    """Um título e o parágrafo seguinte estão longe um do outro na página
    e devem continuar separados — a pausa entre eles é desejada."""
    def build(doc):
        p = doc.new_page()
        p.insert_text((72, 72), "Titulo do capitulo")
        p.insert_text((72, 200), "O corpo do texto comeca bem mais abaixo.")

    r = PDFRenderer(_save_pdf(tmp_path, "paras.pdf", build))
    assert r.text_for_page(0).split("\n") == [
        "Titulo do capitulo",
        "O corpo do texto comeca bem mais abaixo.",
    ]
    r.close()


def test_text_for_page_remove_rodape_que_muda_de_numero(tmp_path):
    """O rodapé mais comum traz o número da página, então a string é
    diferente em cada página e a contagem por texto literal nunca batia o
    limiar: o rodapé escapava e era lido em voz alta a cada virada."""
    def build(doc):
        for i in range(5):
            p = doc.new_page()
            p.insert_text((72, 72), (
                f"Conteudo relevante da pagina {i + 1}: uma linha de texto "
                "corrido com o comprimento tipico de um livro."))
            p.insert_text((72, 780), f"www.exemplo.com - Pagina {i + 1}")

    r = PDFRenderer(_save_pdf(tmp_path, "rodape.pdf", build))
    for i in range(5):
        text = r.text_for_page(i)
        assert "www.exemplo.com" not in text
        assert f"pagina {i + 1}" in text
    r.close()


# ──────────────────────────────────────────────────────────────────
# word_rects — base do grifo que acompanha a voz
# ──────────────────────────────────────────────────────────────────

def test_word_rects_devolve_palavras_normalizadas_em_ordem(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    words = r.word_rects(0)
    nomes = [w for w, _ in words]
    assert nomes[:3] == ["capitulo", "um", "o"]
    # a pontuação some na normalização (casa com o texto do TTS)
    assert "telhado" in nomes
    assert all(set(rect) == {"x0", "y0", "x1", "y1"} for _, rect in words)
    r.close()


def test_word_rects_retangulo_e_da_palavra_e_nao_da_linha(sample_pdf_path):
    """O ponto da mudança: search_text casa por âncora e devolve a LINHA
    inteira; aqui cada palavra tem o seu próprio retângulo, estreito."""
    r = PDFRenderer(sample_pdf_path)
    rects = dict(r.word_rects(0))
    linha = r.search_text(0, "O gato preto dormia tranquilo sobre o telhado quente.")
    largura_palavra = rects["gato"]["x1"] - rects["gato"]["x0"]
    largura_linha = linha[0]["x1"] - linha[0]["x0"]
    assert largura_palavra < largura_linha / 3
    r.close()


def test_word_rects_fora_do_intervalo_e_apos_close(sample_pdf_path):
    r = PDFRenderer(sample_pdf_path)
    assert r.word_rects(99) == []
    assert r.word_rects(-1) == []
    r.close()
    assert r.word_rects(0) == []
