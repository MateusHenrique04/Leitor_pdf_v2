package com.lector.app.domain

/** Retângulo em pontos PDF, origem no canto superior esquerdo (sem Android, testável no PC). */
data class WordRect(val x0: Float, val y0: Float, val x1: Float, val y1: Float)

/** Palavra da página: forma normalizada (chave de comparação) + retângulo. Equivale a word_rects() do desktop. */
data class PageWord(val norm: String, val rect: WordRect) {
    companion object {
        fun from(box: WordBox) = PageWord(normalizeWord(box.text), WordRect(box.x0, box.y0, box.x1, box.y1))
        fun fromAll(boxes: List<WordBox>) = boxes.map { from(it) }
    }
}

/**
 * Onde a leitura parou: página e índice da próxima palavra a casar.
 * Persiste entre um trecho e o seguinte para "de"/"que" não saltarem para a 1ª ocorrência da página.
 */
data class SyncCursor(val pageIndex: Int = 0, val wordIndex: Int = 0)

/**
 * Uma palavra falada. [rect] == null: não achou na página (nota, sigla soletrada...); o grifo
 * fica onde estava. [pageIndex] diz em que página está o retângulo (trechos podem cruzar páginas).
 */
data class SyncedWord(val startSeconds: Float, val endSeconds: Float, val pageIndex: Int, val rect: WordRect?)

data class SyncResult(val words: List<SyncedWord>, val cursor: SyncCursor)

/** Porte de core/word_sync.py. Lógica pura: entra lista, sai lista. */
object WordSync {
    /** Quantas palavras da página olhar à frente quando a falada não é exatamente a próxima. */
    const val WORD_LOOKAHEAD = 12

    /** Quantas palavras antes do fim da página já se aceita tentar a página seguinte (trecho que cruza páginas). */
    const val PAGE_END_WINDOW = WORD_LOOKAHEAD

    /** Tolerância (pt) para considerar dois retângulos na mesma linha. */
    const val LINE_TOLERANCE_PT = 3f

    /** Próxima ocorrência de [word] a partir de [start], dentro da janela. -1 se não achar. */
    fun matchForward(pageWords: List<String>, word: String, start: Int): Int {
        val from = maxOf(start, 0)
        val stop = minOf(start + WORD_LOOKAHEAD, pageWords.size)
        for (j in from until stop) if (pageWords[j] == word) return j
        // Casamento parcial: o extrator às vezes cola duas palavras ou corta uma ao meio.
        for (j in from until stop) {
            val pw = pageWords[j]
            if (pw.isNotEmpty() && (pw.startsWith(word) || word.startsWith(pw))) return j
        }
        return -1
    }

    /**
     * Onde o trecho falado começa na página: as 3 primeiras palavras em sequência a partir de
     * [fromIdx] e, se não achar, desde o início (o usuário pode ter voltado). -1 se não achar.
     */
    fun anchorChunk(pageWords: List<String>, spoken: List<String>, fromIdx: Int): Int {
        val needle = spoken.filter { it.isNotEmpty() }.take(3)
        if (needle.isEmpty()) return -1
        val k = needle.size
        for (base in intArrayOf(fromIdx, 0)) {
            var i = maxOf(base, 0)
            while (i <= pageWords.size - k) {
                var ok = true
                for (n in 0 until k) if (pageWords[i + n] != needle[n]) { ok = false; break }
                if (ok) return i
                i++
            }
        }
        return -1
    }

    /** Junta os retângulos da mesma linha num só, para o grifo do trecho sair contínuo. */
    fun mergeRectsByLine(rects: List<WordRect>, tol: Float = LINE_TOLERANCE_PT): List<WordRect> {
        val lines = ArrayList<WordRect>()
        for (r in rects) {
            val i = lines.indexOfFirst { kotlin.math.abs(it.y0 - r.y0) <= tol }
            if (i >= 0) {
                val ln = lines[i]
                lines[i] = WordRect(minOf(ln.x0, r.x0), minOf(ln.y0, r.y0), maxOf(ln.x1, r.x1), maxOf(ln.y1, r.y1))
            } else {
                lines.add(r)
            }
        }
        return lines
    }
}

/**
 * Para cada palavra que o TTS vai falar, o retângulo na página (porte de word_bboxes).
 *
 * [pageWords] devolve as palavras de uma página (pode ser lenta na 1ª vez; só é chamada para a
 * página inicial e, se o trecho cruzar páginas, para a seguinte). Novidade em relação ao desktop:
 * um trecho que começa em [startPage] e termina em [endPage] continua na página seguinte quando
 * a palavra falada não existe mais no fim da página atual.
 */
class WordSyncEngine(private val pageWords: (pageIndex: Int) -> List<PageWord>) {

    fun sync(
        startPage: Int,
        endPage: Int,
        timings: List<WordTiming>,
        cursor: SyncCursor = SyncCursor(startPage, 0),
    ): SyncResult {
        if (timings.isEmpty()) return SyncResult(emptyList(), cursor)
        val lastPage = maxOf(endPage, startPage)

        var page = startPage
        var current = pageWords(page)
        if (current.isEmpty()) {
            return SyncResult(timings.map { SyncedWord(it.startSeconds, it.endSeconds, page, null) }, cursor)
        }
        var norms = current.map { it.norm }
        val spoken = timings.map { normalizeWord(it.word) }

        // O cursor só vale na mesma página; em página nova a leitura começa do início.
        var cur = if (cursor.pageIndex == startPage) cursor.wordIndex else 0
        val anchor = WordSync.anchorChunk(norms, spoken, cur)
        if (anchor >= 0) cur = anchor

        val out = ArrayList<SyncedWord>(timings.size)
        for ((t, word) in timings.zip(spoken)) {
            var rect: WordRect? = null
            if (word.isNotEmpty()) {
                val hit = WordSync.matchForward(norms, word, cur)
                if (hit >= 0) {
                    rect = current[hit].rect
                    cur = hit + 1
                } else if (page < lastPage && cur >= norms.size - WordSync.PAGE_END_WINDOW) {
                    val next = pageWords(page + 1)
                    val nextNorms = next.map { it.norm }
                    val h2 = WordSync.matchForward(nextNorms, word, 0)
                    if (h2 >= 0) {
                        page += 1
                        current = next
                        norms = nextNorms
                        rect = current[h2].rect
                        cur = h2 + 1
                    }
                }
            }
            out.add(SyncedWord(t.startSeconds, t.endSeconds, page, rect))
        }
        return SyncResult(out, SyncCursor(page, cur))
    }
}
