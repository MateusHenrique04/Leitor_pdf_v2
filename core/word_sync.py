"""
core/word_sync.py — casa as palavras que o TTS vai falar com as palavras
da página, para o grifo acompanhar a voz.

Lógica pura: entra lista, sai lista. Fica em `core/` pela mesma razão dos
outros módulos daqui — é o que permite testar o casamento sem abrir uma
janela. A UI (ui/highlights_mixin.py) só guarda o cursor entre um trecho
e o seguinte e chama `word_bboxes`.

Por que casar palavra a palavra em vez de buscar cada uma no PDF: a busca
textual do PyMuPDF custa ~9 ms por palavra e, por casar por âncora,
devolve a LINHA inteira em vez do retângulo da palavra. Aqui uma única
leitura da página (PDFRenderer.word_rects, com cache) resolve o trecho
todo em poucos milissegundos, com o retângulo exato de cada palavra.
"""
from core.pdf_renderer import normalize_word

# Quantas palavras da página olhar à frente quando a palavra dita pelo
# TTS não é exatamente a próxima da página. Acontece com marcadores de
# nota ("...dicha crisis.[1]"), com siglas que o sintetizador soletra e
# com palavras que o extrator do PDF separa de outra forma.
WORD_LOOKAHEAD = 12


def match_forward(page_words: list[str], word: str, start: int) -> int:
    """Índice da próxima ocorrência de `word` a partir de `start`, dentro
    da janela de busca. -1 se não achar — nesse caso o grifo simplesmente
    continua onde estava, em vez de saltar para outro ponto da página."""
    stop = min(start + WORD_LOOKAHEAD, len(page_words))
    for j in range(start, stop):
        if page_words[j] == word:
            return j
    # Casamento parcial: o extrator às vezes cola duas palavras ou corta
    # uma ao meio, e aí a igualdade exata nunca bate.
    for j in range(start, stop):
        pw = page_words[j]
        if pw and (pw.startswith(word) or word.startswith(pw)):
            return j
    return -1


def anchor_chunk(page_words: list[str], spoken: list[str], from_idx: int) -> int:
    """Onde o trecho falado começa na página. Procura as três primeiras
    palavras em sequência a partir de `from_idx` e, se não achar, desde o
    início da página (o usuário pode ter voltado com ◂). -1 se não achar."""
    needle = [w for w in spoken if w][:3]
    if not needle:
        return -1
    k = len(needle)
    for base in (from_idx, 0):
        for i in range(base, len(page_words) - k + 1):
            if page_words[i:i + k] == needle:
                return i
    return -1


def merge_rects_by_line(rects: list[dict], tol: float = 3.0) -> list[dict]:
    """Junta os retângulos de palavras que estão na mesma linha num único
    retângulo, para o grifo do trecho sair contínuo em vez de picotado
    entre as palavras."""
    lines: list[dict] = []
    for r in rects:
        for ln in lines:
            if abs(ln["y0"] - r["y0"]) <= tol:
                ln["x0"] = min(ln["x0"], r["x0"])
                ln["y0"] = min(ln["y0"], r["y0"])
                ln["x1"] = max(ln["x1"], r["x1"])
                ln["y1"] = max(ln["y1"], r["y1"])
                break
        else:
            lines.append(dict(r))
    return lines


def word_bboxes(
    page_words: list[tuple[str, dict]],
    timings: list[dict],
    cursor: int = 0,
) -> tuple[list[tuple[float, float, list[dict]]], int]:
    """
    Para cada palavra que o TTS vai falar, o retângulo correspondente na
    página.

    `page_words` vem de PDFRenderer.word_rects(n); `timings` são os
    word-timings de core.tts.speak; `cursor` é o ponto da página onde a
    leitura parou no trecho anterior.

    Devolve ([(inicio_s, fim_s, [retângulos]), ...], novo_cursor). O
    cursor existe para que uma palavra comum ("de", "que") não faça o
    grifo saltar de volta para a primeira ocorrência da página.
    """
    if not timings:
        return [], cursor
    if not page_words:
        return [(t["start"], t["end"], []) for t in timings], cursor

    page_norms = [w for w, _ in page_words]
    spoken = [normalize_word(t["word"]) for t in timings]

    anchor = anchor_chunk(page_norms, spoken, cursor)
    if anchor >= 0:
        cursor = anchor

    result: list[tuple[float, float, list[dict]]] = []
    for t, word in zip(timings, spoken, strict=True):
        rects: list[dict] = []
        if word:
            hit = match_forward(page_norms, word, cursor)
            if hit >= 0:
                rects = [dict(page_words[hit][1])]
                cursor = hit + 1
        result.append((t["start"], t["end"], rects))

    return result, cursor
