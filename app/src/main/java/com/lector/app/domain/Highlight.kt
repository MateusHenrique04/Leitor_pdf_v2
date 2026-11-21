package com.lector.app.domain

/**
 * O que desenhar na página [page]: a palavra sendo falada ([word]; null antes da primeira) e as linhas do
 * trecho inteiro nessa página ([lines]; um retângulo por linha, em tom mais fraco). Pontos PDF, origem no topo.
 */
data class Highlight(val page: Int, val word: WordRect?, val lines: List<WordRect>)

object HighlightBuilder {
    /**
     * Monta o grifo para a palavra [wordIndex] do trecho. Palavra sem retângulo (nota, sigla soletrada) mantém o
     * grifo na última palavra localizada, como no desktop. Antes da primeira palavra mostra só as linhas do trecho.
     * [fallbackPage] é usada se nenhuma palavra do trecho foi localizada.
     */
    fun build(fallbackPage: Int, words: List<SyncedWord>, wordIndex: Int): Highlight {
        var current: SyncedWord? = null
        var i = minOf(wordIndex, words.size - 1)
        while (i >= 0) {
            if (words[i].rect != null) { current = words[i]; break }
            i--
        }
        val page = (current ?: words.firstOrNull { it.rect != null })?.pageIndex ?: fallbackPage
        val rects = words.filter { it.pageIndex == page }.mapNotNull { it.rect }
        return Highlight(page, current?.rect, WordSync.mergeRectsByLine(rects))
    }
}

/** Quanto rolar a página para a palavra grifada ficar à vista (coordenadas de tela, em pixels). */
object RevealPolicy {
    data class Delta(val dx: Float, val dy: Float) {
        val isZero: Boolean get() = dx == 0f && dy == 0f
    }

    const val TARGET_FRACTION_Y = 0.30f
    const val MARGIN_FRACTION_Y = 0.10f

    /**
     * [left], [top], [right], [bottom]: retângulo da palavra na tela agora; [contentW]: largura da página na tela.
     *
     * Vertical: se a palavra sai da área útil (10% de margem em cima e embaixo), leva a linha para ~30% da altura.
     * Horizontal: com a página mais larga que a tela (zoom), a palavra é mantida no CENTRO a cada palavra, para a
     * página deslizar junto com a voz; com a página inteira cabendo na largura, não rola na horizontal.
     */
    fun delta(
        left: Float, top: Float, right: Float, bottom: Float,
        viewW: Float, viewH: Float, contentW: Float,
    ): Delta {
        val padY = viewH * MARGIN_FRACTION_Y
        val dy = if (top < padY || bottom > viewH - padY) viewH * TARGET_FRACTION_Y - top else 0f
        val dx = if (contentW > viewW + 1f) viewW / 2f - (left + right) / 2f else 0f
        return Delta(dx, dy)
    }
}
