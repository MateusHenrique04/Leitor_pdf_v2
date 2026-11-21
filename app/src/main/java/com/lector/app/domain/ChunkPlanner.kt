package com.lector.app.domain

/**
 * Um trecho a ser enviado ao TTS.
 * - [index]: posição global no livro (chave do cache da Fase 8).
 * - [pageIndex]: página onde o trecho COMEÇA; [endPageIndex]: onde TERMINA (difere quando cruza páginas).
 * - [indexInPage]: ordem entre os trechos que começam na mesma página (equivale ao last_chunk_idx do desktop).
 */
data class Chunk(
    val index: Int,
    val pageIndex: Int,
    val endPageIndex: Int,
    val indexInPage: Int,
    val text: String,
)

/**
 * Porte de build_chunks (core/text.py) + tratamento de frases que atravessam páginas (lógica nova).
 * Determinístico: mesmas páginas + mesmo [VERSION] => mesmos índices. Se QUALQUER regra mudar
 * (limites, abreviações, junção de páginas), aumente [VERSION]: o cache de áudio depende disso.
 */
object ChunkPlanner {
    const val VERSION = 1
    const val TARGET_CHUNK_CHARS = 240
    const val MAX_CHUNK_CHARS = 520

    private const val CLOSERS = "\"'\u201D\u2019\u00BB)]}\u203A"
    private const val TERMINATORS = ".!?\u2026:"
    private val HYPHEN_END = Regex("""\p{L}-\z""")

    /**
     * Divide [text] (um "\n" = fim de parágrafo) em trechos: frases do MESMO parágrafo agrupadas até
     * ~[targetChars], nunca juntando parágrafos, nenhum trecho acima de [maxChars].
     */
    fun buildChunks(
        text: String,
        targetChars: Int = TARGET_CHUNK_CHARS,
        maxChars: Int = MAX_CHUNK_CHARS,
    ): List<String> {
        val chunks = ArrayList<String>()
        for (paragraph in text.split('\n')) {
            if (paragraph.isBlank()) continue
            var buf = ""
            for (sentence in TextSplitter.splitSentences(paragraph)) {
                for (part in TextSplitter.splitLongSentence(sentence, maxChars)) {
                    if (buf.isNotEmpty() && buf.length + 1 + part.length > maxChars) {
                        chunks.add(buf)
                        buf = part
                    } else {
                        buf = if (buf.isNotEmpty()) "$buf $part" else part
                    }
                    if (buf.length >= targetChars) {
                        chunks.add(buf)
                        buf = ""
                    }
                }
            }
            if (buf.isNotEmpty()) chunks.add(buf)
        }
        return chunks
    }

    /**
     * Planeja o livro inteiro a partir do texto limpo de cada página ([TextCleaner.cleanAll]).
     *
     * Frase que atravessa páginas: se o ÚLTIMO parágrafo de uma página não termina em . ! ? … : e o
     * PRIMEIRO da página seguinte (adjacente, com texto) começa em minúscula, os dois viram um só
     * parágrafo (com hífen de fim de linha unido). O trecho pertence à página onde começa
     * ([Chunk.pageIndex]) e informa onde termina ([Chunk.endPageIndex]); um trecho que fica inteiro na
     * página seguinte conta como daquela página.
     */
    fun planBook(
        pageTexts: List<String>,
        targetChars: Int = TARGET_CHUNK_CHARS,
        maxChars: Int = MAX_CHUNK_CHARS,
    ): List<Chunk> {
        val out = ArrayList<Chunk>()
        val perPage = HashMap<Int, Int>()
        for (para in mergeParagraphs(pageTexts)) {
            var from = 0
            for (c in buildChunks(para.text, targetChars, maxChars)) {
                val found = para.text.indexOf(c, from)
                val start = if (found >= 0) found else from
                val end = if (found >= 0) found + c.length - 1 else start
                if (found >= 0) from = found + c.length
                val startPage = para.pageAt(start)
                val endPage = para.pageAt(end)
                val inPage = perPage[startPage] ?: 0
                perPage[startPage] = inPage + 1
                out.add(Chunk(out.size, startPage, endPage, inPage, c))
            }
        }
        return out
    }

    /** Parágrafo possivelmente composto por pedaços de várias páginas. */
    private class Para(var text: String, startPage: Int) {
        /** (deslocamento no texto onde o pedaço começa, página do pedaço) */
        val segments = arrayListOf(0 to startPage)
        var lastPage = startPage

        fun pageAt(offset: Int): Int = segments.last { it.first <= offset }.second

        fun append(next: String, page: Int) {
            text = if (HYPHEN_END.containsMatchIn(text)) text.dropLast(1) + next else "$text $next"
            segments.add((text.length - next.length) to page)
            lastPage = page
        }
    }

    private fun mergeParagraphs(pageTexts: List<String>): List<Para> {
        val result = ArrayList<Para>()
        var pending: Para? = null
        for ((page, text) in pageTexts.withIndex()) {
            val paragraphs = text.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
            if (paragraphs.isEmpty()) { // página vazia interrompe qualquer continuação
                pending?.let { result.add(it) }
                pending = null
                continue
            }
            var rest = paragraphs
            val cur = pending
            if (cur != null && cur.lastPage == page - 1 && isUnfinished(cur.text) && startsLowercase(paragraphs[0])) {
                cur.append(paragraphs[0], page)
                rest = paragraphs.drop(1)
                if (rest.isEmpty()) continue // página só tem a continuação: a cadeia segue em aberto
                result.add(cur)
                pending = null
            } else {
                if (cur != null) result.add(cur)
                pending = null
            }
            for (i in rest.indices) {
                val para = Para(rest[i], page)
                if (i == rest.lastIndex) pending = para else result.add(para)
            }
        }
        pending?.let { result.add(it) }
        return result
    }

    private fun isUnfinished(text: String): Boolean {
        val t = text.trimEnd().trimEnd { it in CLOSERS }
        val last = t.lastOrNull() ?: return false
        return last !in TERMINATORS
    }

    private fun startsLowercase(s: String): Boolean = s.firstOrNull()?.isLowerCase() == true
}
