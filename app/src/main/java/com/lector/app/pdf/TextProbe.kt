package com.lector.app.pdf

import com.lector.app.domain.ChunkPlanner
import com.lector.app.domain.PageGeometry
import com.lector.app.domain.PageSize
import com.lector.app.domain.TextCleaner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.Locale
import kotlin.math.min

/**
 * TEMPORÁRIO (Fase 3b): mede a extração de [count] páginas seguidas, confere o tamanho da página com o
 * PdfRenderer e mostra uma prévia do texto limpo. Será removido quando o PdfEngine estiver integrado.
 */
object TextProbe {
    suspend fun run(
        engine: PdfEngine,
        rendererSize: (Int) -> PageSize,
        currentPage: Int,
        count: Int = 5,
    ): String = withContext(Dispatchers.IO) {
        val last = min(engine.pageCount - 1, currentPage + count - 1)
        val pages = (currentPage..last).map { engine.extractPage(it, useCache = false) }
        val loc = Locale.US
        val sb = StringBuilder()

        sb.append("Abrir no PdfBox: ${engine.openMs} ms (só na 1ª vez)\n")
        sb.append("Páginas ${currentPage + 1} a ${last + 1} (${engine.pageCount} no livro)\n\n")
        for (p in pages) {
            sb.append(
                "Pág %d: %d ms | %d palavras | %d linhas | %d parágrafos | %d car.\n".format(
                    loc, p.index + 1, p.extractMs, p.words.size, p.lines.size, p.raw.blocks.size,
                    p.raw.lines.sumOf { it.length },
                )
            )
        }
        val first = pages.first().extractMs
        val rest = pages.drop(1).map { it.extractMs }
        sb.append("\n1ª página medida: $first ms (pode incluir carregar fontes)\n")
        if (rest.isNotEmpty()) {
            val avg = rest.average()
            sb.append("Média das demais: %.0f ms/página\n".format(loc, avg))
            sb.append("Livro inteiro (estimativa linear): ~%.0f s\n".format(loc, avg * engine.pageCount / 1000.0))
        } else {
            sb.append("Só 1 página medida: vá para uma página antes do fim para medir 5 seguidas.\n")
        }

        sb.append("\nTamanho PdfBox x PdfRenderer:\n")
        for (p in pages) {
            val r = rendererSize(p.index)
            val diff = PageGeometry.mismatch(p.size, r)
            sb.append("  pág ${p.index + 1} (rot ${p.rotation}): ${diff?.let { "DIFERENTE: $it" } ?: "OK"}\n")
        }

        // Diagnóstico de hifenização: caracteres "estranhos" no fim das linhas (hífen suave, hífen especial etc.).
        val oddEnds = pages.flatMap { it.lines }
            .mapNotNull { it.text.trimEnd().lastOrNull() }
            .filter { !it.isLetterOrDigit() && it !in NORMAL_ENDS }
            .groupingBy { it }.eachCount()
        sb.append("\nFim de linha fora do comum: ")
        sb.append(
            if (oddEnds.isEmpty()) "nenhum"
            else oddEnds.entries.sortedByDescending { it.value }.take(6)
                .joinToString(", ") { "U+%04X x%d".format(it.key.code, it.value) }
        )
        sb.append("\n")

        val cleaner = TextCleaner(pages.map { it.raw })
        val text = cleaner.cleanPage(0)
        val chunks = ChunkPlanner.buildChunks(text)
        sb.append("\nCabeçalho/rodapé removidos: ${cleaner.skipKeys.size}")
        if (cleaner.skipKeys.isNotEmpty()) sb.append(" ${cleaner.skipKeys.take(3)}")
        sb.append("\nTrechos na pág ${currentPage + 1}: ${chunks.size} (planner v${ChunkPlanner.VERSION})\n")
        sb.append("\nTexto limpo da pág ${currentPage + 1} (¶ = parágrafo):\n")
        val preview = text.replace("\n", "\n¶ ")
        sb.append("¶ ").append(if (preview.length > PREVIEW_CHARS) preview.take(PREVIEW_CHARS) + " [...]" else preview)
        if (text.isEmpty()) sb.append("\n(sem texto: página em branco ou PDF escaneado)")
        sb.toString()
    }

    private const val PREVIEW_CHARS = 900
    private const val NORMAL_ENDS = ".,;:!?\u2026\"\u201D\u201C\u2019)]\u00BB"
}
