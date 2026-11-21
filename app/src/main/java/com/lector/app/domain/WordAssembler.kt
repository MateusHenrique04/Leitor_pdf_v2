package com.lector.app.domain

import kotlin.math.max
import kotlin.math.min

/**
 * Junta glifos em palavras. Uma palavra termina em qualquer glifo "em branco" (espaço, NBSP, tab...).
 * Glifos com texto vazio são ignorados (não separam palavras).
 */
object WordAssembler {
    fun assemble(glyphs: List<Glyph>): List<WordBox> {
        val out = ArrayList<WordBox>()
        val sb = StringBuilder()
        var open = false
        var x0 = 0f
        var x1 = 0f
        var baseline = 0f
        var height = 0f

        fun flush() {
            if (open && sb.isNotBlank()) out.add(WordBox(sb.toString(), x0, baseline - height, x1, baseline))
            sb.setLength(0)
            open = false
        }

        for (g in glyphs) {
            if (g.unicode.isEmpty()) continue
            if (g.unicode.isBlank()) {
                flush()
                continue
            }
            if (!open) {
                open = true
                x0 = g.x
                x1 = g.x + g.width
                baseline = g.baseline
                height = g.height
            } else {
                x0 = min(x0, g.x)
                x1 = max(x1, g.x + g.width)
                baseline = max(baseline, g.baseline)
                height = max(height, g.height)
            }
            sb.append(g.unicode)
        }
        flush()
        return out
    }
}
