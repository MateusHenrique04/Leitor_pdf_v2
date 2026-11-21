package com.lector.app.domain

import kotlin.math.abs
import kotlin.math.max

/**
 * O PdfBox não entrega "blocos" como o PyMuPDF: aqui as linhas viram parágrafos (blocos para o [RawPage]).
 *
 * Há um novo parágrafo entre a linha A e a próxima linha B quando:
 *  1. B está ACIMA de A (nova coluna ou nova região);
 *  2. o espaço vertical A->B é bem maior que o normal da página;
 *  3. o tamanho da fonte muda (título -> texto);
 *  4. A termina em pontuação final E (A é bem mais curta que a coluna OU B tem recuo de 1ª linha).
 *
 * Por que a regra 4 exige pontuação: texto alinhado à esquerda (sem justificar) tem linhas curtas no meio
 * do parágrafo; cortar ali quebraria a frase ao meio e o TTS leria com pausa errada.
 * TODAS as constantes abaixo são pontos de ajuste com os PDFs reais.
 */
object ParagraphGrouper {
    /** B "acima" de A por mais que esta fração da altura => outra coluna/região. */
    const val COLUMN_BACK_RATIO = 0.5f

    /** Espaço A->B maior que (espaço típico da página x este fator) => novo parágrafo. */
    const val PARAGRAPH_GAP_RATIO = 1.5f

    /** Recuo de 1ª linha: B começa à direita de A por mais que (altura x este fator). */
    const val INDENT_RATIO = 0.8f

    /** A termina antes da borda direita da coluna por mais que (altura x este fator) => linha curta. */
    const val SHORT_LINE_RATIO = 3.0f

    /** Diferença de altura entre linhas maior que esta fração => mudança de fonte. */
    const val FONT_CHANGE_RATIO = 0.2f

    /** Só entram na estimativa do espaço típico distâncias menores que (altura mediana x este fator). */
    const val MAX_PITCH_HEIGHTS = 2.5f

    /**
     * O espaço típico estimado nunca passa de (altura mediana x este fator): protege páginas com poucas linhas,
     * onde o único espaço medido pode ser justamente o de entre parágrafos.
     */
    const val MAX_BASE_PITCH_HEIGHTS = 1.8f

    /** Sem dados suficientes: espaço típico = altura mediana x este fator. */
    const val DEFAULT_PITCH_RATIO = 1.2f

    private const val CLOSERS = "\"'\u201D\u2019\u00BB)]}\u203A"
    private const val TERMINATORS = ".!?\u2026:"

    fun group(lines: List<TextLine>): List<List<String>> {
        val ls = lines.filter { it.text.isNotBlank() }
        if (ls.isEmpty()) return emptyList()

        val basePitch = estimateBasePitch(ls)
        val rightEdge = columnRightEdges(ls)

        val blocks = ArrayList<List<String>>()
        var cur = ArrayList<String>()
        cur.add(ls[0].text)
        for (i in 1 until ls.size) {
            if (startsNewParagraph(ls[i - 1], ls[i], rightEdge[i - 1], basePitch)) {
                blocks.add(cur)
                cur = ArrayList()
            }
            cur.add(ls[i].text)
        }
        blocks.add(cur)
        return blocks
    }

    internal fun endsSentence(text: String): Boolean {
        val t = text.trimEnd().trimEnd { it in CLOSERS }
        return t.isNotEmpty() && t.last() in TERMINATORS
    }

    private fun isColumnBreak(a: TextLine, b: TextLine): Boolean =
        b.y1 < a.y1 - COLUMN_BACK_RATIO * max(a.height, 1f)

    private fun startsNewParagraph(a: TextLine, b: TextLine, rightEdge: Float, basePitch: Float): Boolean {
        val h = max(a.height, 1f)
        if (isColumnBreak(a, b)) return true
        if (b.y1 - a.y1 > basePitch * PARAGRAPH_GAP_RATIO) return true
        if (abs(b.height - a.height) > FONT_CHANGE_RATIO * max(max(a.height, b.height), 1f)) return true
        if (endsSentence(a.text)) {
            if (a.x1 < rightEdge - SHORT_LINE_RATIO * h) return true
            if (b.x0 - a.x0 > INDENT_RATIO * h) return true
        }
        return false
    }

    /** Para cada linha, a borda direita (maior x1) da sequência de linhas da mesma coluna a que ela pertence. */
    private fun columnRightEdges(ls: List<TextLine>): FloatArray {
        val edges = FloatArray(ls.size)
        var start = 0
        for (i in 1..ls.size) {
            if (i == ls.size || isColumnBreak(ls[i - 1], ls[i])) {
                val right = (start until i).maxOf { ls[it].x1 }
                for (k in start until i) edges[k] = right
                start = i
            }
        }
        return edges
    }

    private fun estimateBasePitch(ls: List<TextLine>): Float {
        val medianHeight = LineBuilder.median(ls.map { it.height }).let { if (it > 0f) it else 12f }
        val pitches = ArrayList<Float>()
        for (i in 1 until ls.size) {
            val p = ls[i].y1 - ls[i - 1].y1
            if (p > 0f && p < MAX_PITCH_HEIGHTS * medianHeight) pitches.add(p)
        }
        if (pitches.isEmpty()) return DEFAULT_PITCH_RATIO * medianHeight
        return minOf(LineBuilder.median(pitches), MAX_BASE_PITCH_HEIGHTS * medianHeight)
    }
}
