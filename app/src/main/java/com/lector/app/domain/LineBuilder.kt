package com.lector.app.domain

import kotlin.math.abs
import kotlin.math.max

/**
 * Agrupa palavras (na ordem do fluxo do PDF) em linhas visuais, por geometria:
 * a palavra continua a linha se a linha de base dela está perto da linha de base da 1ª palavra
 * (aceita sobrescrito/subscrito) e ela não "volta" para a esquerda (isso indicaria nova linha).
 */
object LineBuilder {
    /** Tolerância da linha de base, como fração da altura do texto. */
    const val SAME_LINE_BASELINE_RATIO = 0.5f
    const val MIN_BASELINE_TOLERANCE_PT = 1f

    /** Quanto a palavra pode recuar para a esquerda (kerning/sobreposição) sem contar como nova linha. */
    const val MAX_BACKTRACK_PT = 3f

    fun build(words: List<WordBox>): List<TextLine> {
        val lines = ArrayList<TextLine>()
        var cur = ArrayList<WordBox>()
        for (w in words) {
            if (w.text.isBlank()) continue
            if (cur.isNotEmpty() && !belongs(cur, w)) {
                lines.add(toLine(cur))
                cur = ArrayList()
            }
            cur.add(w)
        }
        if (cur.isNotEmpty()) lines.add(toLine(cur))
        return lines
    }

    private fun belongs(line: List<WordBox>, w: WordBox): Boolean {
        val first = line.first()
        val last = line.last()
        val ref = max(max(w.y1 - w.y0, first.y1 - first.y0), 0f)
        val tolerance = max(SAME_LINE_BASELINE_RATIO * ref, MIN_BASELINE_TOLERANCE_PT)
        if (abs(w.y1 - first.y1) > tolerance) return false
        if (w.x0 < last.x1 - MAX_BACKTRACK_PT) return false
        return true
    }

    private fun toLine(words: List<WordBox>): TextLine {
        val baseline = median(words.map { it.y1 })
        val height = median(words.map { it.y1 - it.y0 })
        return TextLine(
            text = words.joinToString(" ") { it.text },
            x0 = words.minOf { it.x0 },
            y0 = baseline - height,
            x1 = words.maxOf { it.x1 },
            y1 = baseline,
        )
    }

    internal fun median(values: List<Float>): Float {
        if (values.isEmpty()) return 0f
        val s = values.sorted()
        return if (s.size % 2 == 1) s[s.size / 2] else (s[s.size / 2 - 1] + s[s.size / 2]) / 2f
    }
}
