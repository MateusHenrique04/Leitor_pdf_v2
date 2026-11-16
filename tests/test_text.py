"""
Testes de core/text.py — split_sentences cobre os casos que a regex
antiga duplicada em ui/controls.py quebrava errado: abreviações,
decimais, reticências, texto vazio e quebras de linha.
"""
from core.text import build_chunks, split_sentences


def test_empty_text_returns_empty_list():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_simple_two_sentences():
    assert split_sentences("Isso e uma frase. Isso e outra.") == [
        "Isso e uma frase.", "Isso e outra.",
    ]


def test_breaks_on_newline():
    assert split_sentences("Primeira linha\nSegunda linha") == [
        "Primeira linha", "Segunda linha",
    ]


def test_does_not_break_on_common_abbreviations():
    text = "O Dr. Silva chegou. A Sra. Costa tambem."
    assert split_sentences(text) == [
        "O Dr. Silva chegou.", "A Sra. Costa tambem.",
    ]


def test_does_not_break_on_page_abbreviation():
    text = "Veja a p. 23 para mais detalhes. Depois continue."
    assert split_sentences(text) == [
        "Veja a p. 23 para mais detalhes.", "Depois continue.",
    ]


def test_fig_abbreviation_never_breaks():
    text = "Compare com a Fig. 3, etc. Isso encerra o ponto."
    result = split_sentences(text)
    assert result == [
        "Compare com a Fig. 3, etc.", "Isso encerra o ponto.",
    ]


def test_etc_followed_by_lowercase_does_not_break():
    text = "Trouxe livros, canetas, etc. para a aula de hoje."
    assert split_sentences(text) == [
        "Trouxe livros, canetas, etc. para a aula de hoje.",
    ]


def test_does_not_break_on_decimal_numbers():
    text = "O valor subiu para 3.5 no ultimo mes. Isso e bom."
    assert split_sentences(text) == [
        "O valor subiu para 3.5 no ultimo mes.", "Isso e bom.",
    ]


def test_ellipsis_used_as_pause_stays_in_one_sentence():
    text = "Ele hesitou... e decidiu sair."
    assert split_sentences(text) == ["Ele hesitou... e decidiu sair."]


def test_english_and_spanish_abbreviations():
    text = "Mr. Smith arrived. Sra. Lopez tambien llego."
    assert split_sentences(text) == [
        "Mr. Smith arrived.", "Sra. Lopez tambien llego.",
    ]


def test_no_common_case_produces_empty_sentence():
    text = "Frase um.   Frase dois.\n\nFrase tres."
    result = split_sentences(text)
    assert all(s.strip() for s in result)
    assert len(result) == 3


# ──────────────────────────────────────────────────────────────────
# build_chunks — agrupamento das frases enviadas ao TTS
# ──────────────────────────────────────────────────────────────────

def test_build_chunks_junta_frases_curtas_do_mesmo_paragrafo():
    """Frases curtas sozinhas viram requisições de TTS separadas, e cada
    requisição custa uma pausa. Dentro de um parágrafo elas devem ser
    agrupadas."""
    texto = "Primeira. Segunda. Terceira."
    assert build_chunks(texto, target_chars=200, max_chars=400) == [
        "Primeira. Segunda. Terceira."
    ]


def test_build_chunks_nunca_junta_paragrafos_diferentes():
    """A pausa entre parágrafos é desejada: um título não pode ser lido
    emendado com o texto que vem depois."""
    texto = "Titulo da secao\nO texto do paragrafo comeca aqui."
    assert build_chunks(texto, target_chars=500, max_chars=900) == [
        "Titulo da secao",
        "O texto do paragrafo comeca aqui.",
    ]


def test_build_chunks_respeita_o_tamanho_alvo():
    frase = "Uma frase de tamanho conhecido para o teste. "
    texto = frase * 10
    chunks = build_chunks(texto, target_chars=100, max_chars=200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    # Nenhum trecho começa no meio de uma frase
    assert all(c[0].isupper() for c in chunks)


def test_build_chunks_quebra_frase_gigante_em_pontos_de_oracao():
    """Uma frase única acima do teto seria uma espera longa demais pela
    geração do áudio; é cortada onde a oração permite."""
    frase = ("Primeira oracao bem comprida desta frase gigante, "
             "segunda oracao igualmente comprida da mesma frase, "
             "terceira oracao que fecha a frase toda.")
    chunks = build_chunks(frase, target_chars=60, max_chars=80)
    assert len(chunks) > 1
    assert all(len(c) <= 80 for c in chunks)
    # O texto sobrevive inteiro ao corte
    assert " ".join(chunks) == frase


def test_build_chunks_frase_sem_ponto_de_corte_nao_e_mutilada():
    """Sem vírgula nem ponto-e-vírgula, é melhor uma requisição longa do
    que cortar no meio de uma palavra."""
    frase = "palavra " * 40
    chunks = build_chunks(frase.strip(), target_chars=50, max_chars=100)
    assert "".join(chunks).replace(" ", "") == frase.replace(" ", "")


def test_build_chunks_texto_vazio():
    assert build_chunks("") == []
    assert build_chunks("   \n  \n ") == []
