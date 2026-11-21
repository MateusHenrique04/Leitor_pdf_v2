package com.lector.app.domain

import java.text.Normalizer
import kotlin.math.max

/**
 * Uma página já extraída: [blocks] = blocos de texto (na prática parágrafos/títulos) em ordem de leitura,
 * cada bloco = suas linhas visuais. É o equivalente de page.get_text("blocks") do PyMuPDF.
 * Quem produz isto (PdfEngine, passo futuro) precisa agrupar linhas em blocos.
 */
data class RawPage(val blocks: List<List<String>>) {
    /** Todas as linhas da página, aparadas, sem vazias, em ordem de leitura. */
    val lines: List<String> by lazy {
        blocks.flatten()
            .map { Normalizer.normalize(it, Normalizer.Form.NFKC).trim() }
            .filter { it.isNotEmpty() }
    }
}

/**
 * Porte de PDFRenderer.text_for_page + detecção de cabeçalho/rodapé (core/pdf_renderer.py).
 * Devolve UM parágrafo por linha ("\n" = fim de parágrafo), que é o que o [ChunkPlanner] espera.
 */
class TextCleaner(private val pages: List<RawPage>) {
    /** Chaves (dígitos mascarados) de linhas repetidas no topo/rodapé em >= 30% das páginas (mín. 3). */
    val skipKeys: Set<String>

    /** Caracteres de texto por página (base da estimativa de duração/espaço). */
    val pageLengths: List<Int>

    init {
        val hdr = HashMap<String, Int>()
        val ftr = HashMap<String, Int>()
        val lengths = ArrayList<Int>(pages.size)
        for (page in pages) {
            val lines = page.lines
            lengths.add(lines.sumOf { it.length })
            if (lines.isNotEmpty()) skipKey(lines.first())?.let { hdr[it] = (hdr[it] ?: 0) + 1 }
            if (lines.size > 1) skipKey(lines.last())?.let { ftr[it] = (ftr[it] ?: 0) + 1 }
        }
        pageLengths = lengths
        val threshold = max(3, (pages.size * 0.30).toInt())
        // Como no desktop ({**hdr, **ftr}): se a mesma chave está nos dois, vale a contagem do rodapé.
        skipKeys = (hdr + ftr).filterValues { it >= threshold }.keys
    }

    fun cleanPage(n: Int): String {
        val page = pages.getOrNull(n) ?: return ""
        return cleanBlocks(page.blocks, skipKeys)
    }

    fun cleanAll(): List<String> = pages.indices.map { cleanPage(it) }

    companion object {
        /** Cabeçalhos/rodapés são curtos; texto corrido tem 70-95 caracteres por linha. */
        const val MAX_RUNNING_HEAD_CHARS = 60

        private val DIGITS = Regex("""\p{Nd}+""")
        private val PAGE_NUMBER = Regex("""\p{Nd}{1,4}""")
        // Hífen de fim de linha: "-" comum, hífen suave U+00AD (o que InDesign/Word exportam) ou hífen U+2010.
        private val HYPHEN_BREAK = Regex("""([\p{L}\p{N}_])[-\u00AD\u2010]\n([\p{L}\p{N}_])""")
        private const val SOFT_HYPHEN = "\u00AD"
        private val SPACES = Regex("""[ \t]+""")

        /**
         * Chave para reconhecer a mesma linha de cabeçalho/rodapé em páginas diferentes: dígitos viram "#"
         * ("Página 17" e "Página 18" são iguais). Linhas LONGAS com dígito não são candidatas (null),
         * senão texto corrido que só muda um numeral seria descartado.
         */
        fun skipKey(line: String): String? {
            val l = line.trim()
            if (l.any { it.isDigit() } && l.length > MAX_RUNNING_HEAD_CHARS) return null
            return DIGITS.replace(l, "#")
        }

        fun cleanBlocks(blocks: List<List<String>>, skip: Set<String>): String {
            val paragraphs = ArrayList<String>()
            for (block in blocks) {
                var raw = Normalizer.normalize(block.joinToString("\n"), Normalizer.Form.NFKC)
                // "hifeniza-\ncao" -> "hifenizacao" (antes de juntar as linhas, senão sobra "- ").
                raw = HYPHEN_BREAK.replace(raw, "\$1\$2")
                val lines = ArrayList<String>()
                for (rawLine in raw.split('\n')) {
                    val ln = rawLine.trim()
                    if (ln.isEmpty()) continue
                    val key = skipKey(ln)
                    if (key != null && key in skip) continue
                    if (PAGE_NUMBER.matches(ln)) continue // número de página isolado
                    lines.add(ln)
                }
                if (lines.isNotEmpty()) paragraphs.add(lines.joinToString(" "))
            }
            var text = paragraphs.joinToString("\n")
            // Hifenização que caiu entre dois blocos (cada linha virou um bloco).
            text = HYPHEN_BREAK.replace(text, "\$1\$2")
            text = SPACES.replace(text, " ")
            // Hífen suave que sobrou (no meio da linha, ou sem letra depois): é invisível, não deve ir ao TTS.
            text = text.replace(SOFT_HYPHEN, "")
            return text.trim()
        }
    }
}
