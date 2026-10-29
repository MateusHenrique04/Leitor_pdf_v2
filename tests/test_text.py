"""
Testes de core/text.py — split_sentences cobre os casos que a regex
antiga duplicada em ui/controls.py quebrava errado: abreviações,
decimais, reticências, texto vazio e quebras de linha.
"""
from core.text import split_sentences


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
