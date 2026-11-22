package com.lector.app.domain

/**
 * Índice de narração do livro inteiro: todos os [Chunk] já planejados (texto limpo + junção entre páginas).
 * É o que o player (Fase 6b) e o download offline (Fase 8) usam, para que os índices sejam sempre os mesmos.
 * Em [chunks], a posição na lista é igual a [Chunk.index].
 */
data class BookIndex(val plannerVersion: Int, val pageCount: Int, val chunks: List<Chunk>) {
    private val byPage: Map<Int, List<Chunk>> by lazy { chunks.groupBy { it.pageIndex } }

    val isEmpty: Boolean get() = chunks.isEmpty()

    /** Trechos que COMEÇAM na página [page], em ordem. */
    fun chunksStartingOn(page: Int): List<Chunk> = byPage[page].orEmpty()

    /** Trecho [indexInPage] da página [page] (é o que BookEntity.lastPage + lastChunkIndex guardam). */
    fun find(page: Int, indexInPage: Int): Chunk? = byPage[page]?.getOrNull(indexInPage)

    /** Primeiro trecho que começa na página [page] ou depois (páginas sem texto são puladas). */
    fun firstFrom(page: Int): Chunk? = chunks.firstOrNull { it.pageIndex >= page }

    /** Onde retomar a leitura: o trecho salvo; se não existir mais, o primeiro a partir da página. */
    fun resumePoint(page: Int, indexInPage: Int): Chunk? = find(page, indexInPage) ?: firstFrom(page)

    /**
     * Intervalo de [Chunk.index] dos trechos que COMEÇAM nas páginas [fromPage]..[toPage] (base 0, inclusive);
     * null se nenhum começa ali. Os trechos estão em ordem de página, então o intervalo é contínuo.
     */
    fun chunkRange(fromPage: Int, toPage: Int): IntRange? {
        val inRange = fromPage..toPage
        val first = chunks.firstOrNull { it.pageIndex in inRange } ?: return null
        val last = chunks.last { it.pageIndex in inRange }
        return first.index..last.index
    }

    fun next(chunk: Chunk): Chunk? = chunks.getOrNull(chunk.index + 1)

    fun previous(chunk: Chunk): Chunk? = chunks.getOrNull(chunk.index - 1)
}
