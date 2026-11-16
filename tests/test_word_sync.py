"""
Testes de core/word_sync.py — o casamento entre as palavras que o TTS
vai falar e as palavras da página, que faz o grifo acompanhar a voz.

Tudo aqui roda sem abrir janela: é por isso que a lógica mora em core/ e
não junto da UI.
"""
import pymupdf
import pytest

from core.pdf_renderer import PDFRenderer
from core.word_sync import (
    WORD_LOOKAHEAD,
    anchor_chunk,
    match_forward,
    merge_rects_by_line,
    word_bboxes,
)


def _timings(frase: str) -> list[dict]:
    """Word-timings no formato que core/tts.speak devolve."""
    return [
        {"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4}
        for i, w in enumerate(frase.split())
    ]


@pytest.fixture
def pagina(tmp_path) -> PDFRenderer:
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "O gato preto dormia sobre o telhado quente.")
    p.insert_text((72, 100), "Depois o gato desceu do telhado devagar.")
    path = tmp_path / "grifo.pdf"
    doc.save(str(path))
    doc.close()
    r = PDFRenderer(str(path))
    yield r
    r.close()


# ── casamento palavra a palavra ───────────────────────────────────

def test_cada_palavra_falada_recebe_seu_retangulo(pagina):
    frase = "O gato preto dormia sobre o telhado quente."
    tim = _timings(frase)
    res, _cursor = word_bboxes(pagina.word_rects(0), tim)

    assert len(res) == len(frase.split())
    assert all(rects for _, _, rects in res), "toda palavra devia ter sido localizada"
    # Os tempos sobrevivem intactos — é por eles que o loop sincroniza
    assert [r[0] for r in res] == [t["start"] for t in tim]


def test_grifo_avanca_e_nao_volta_para_palavra_repetida(pagina):
    """'gato' e 'telhado' aparecem nas duas linhas. Lendo a segunda
    linha, o grifo tem que pegar a ocorrência de baixo."""
    palavras = pagina.word_rects(0)
    _res, cursor = word_bboxes(palavras, _timings("O gato preto dormia sobre o telhado quente."))
    res, _ = word_bboxes(palavras, _timings("Depois o gato desceu do telhado devagar."), cursor)

    ys = [rects[0]["y0"] for _, _, rects in res if rects]
    assert ys, "nenhuma palavra localizada na segunda linha"
    assert min(ys) > palavras[0][1]["y0"]


def test_cursor_avanca_a_cada_trecho(pagina):
    palavras = pagina.word_rects(0)
    _res, cursor = word_bboxes(palavras, _timings("O gato preto"))
    assert cursor == 3


def test_palavra_ausente_na_pagina_nao_desloca_o_grifo(pagina):
    """Marcadores de nota e siglas soletradas são ditos pelo TTS mas não
    estão no texto: ficam sem retângulo, e o grifo segue de onde estava."""
    res, _ = word_bboxes(pagina.word_rects(0), _timings("O gato xyzinexistente preto dormia"))
    assert res[2][2] == []
    assert res[3][2], "a palavra seguinte devia continuar sendo localizada"


def test_sem_timings_ou_sem_palavras_nao_quebra(pagina):
    assert word_bboxes(pagina.word_rects(0), []) == ([], 0)
    res, cursor = word_bboxes([], _timings("qualquer coisa"))
    assert cursor == 0
    assert all(rects == [] for _, _, rects in res)


# ── helpers ───────────────────────────────────────────────────────

def test_match_forward_respeita_a_janela_de_busca():
    palavras = ["alvo"] + ["ruido"] * (WORD_LOOKAHEAD + 5) + ["alvo"]
    assert match_forward(palavras, "alvo", 0) == 0
    # a segunda ocorrência está longe demais da janela
    assert match_forward(palavras, "alvo", 1) == -1


def test_match_forward_aceita_casamento_parcial():
    """O extrator do PDF às vezes cola ou corta palavras."""
    assert match_forward(["introducao"], "intro", 0) == 0
    assert match_forward(["intro"], "introducao", 0) == 0
    assert match_forward(["outra"], "intro", 0) == -1


def test_anchor_chunk_procura_para_tras_quando_preciso():
    """Depois de voltar com o botão ◂ o trecho fica ANTES do cursor."""
    palavras = ["inicio", "do", "texto", "meio", "do", "texto"]
    assert anchor_chunk(palavras, ["inicio", "do", "texto"], from_idx=4) == 0
    assert anchor_chunk(palavras, ["nao", "existe", "aqui"], from_idx=0) == -1


def test_merge_rects_junta_palavras_da_mesma_linha():
    """Sem juntar, o grifo do trecho sai picotado entre as palavras."""
    rects = [
        {"x0": 10, "y0": 50, "x1": 30, "y1": 60},
        {"x0": 35, "y0": 50, "x1": 70, "y1": 60},
        {"x0": 10, "y0": 80, "x1": 45, "y1": 90},
    ]
    linhas = merge_rects_by_line(rects)
    assert len(linhas) == 2
    assert linhas[0] == {"x0": 10, "y0": 50, "x1": 70, "y1": 60}


def test_merge_rects_nao_altera_a_lista_recebida():
    rects = [{"x0": 10, "y0": 50, "x1": 30, "y1": 60},
             {"x0": 35, "y0": 50, "x1": 70, "y1": 60}]
    copia = [dict(r) for r in rects]
    merge_rects_by_line(rects)
    assert rects == copia
