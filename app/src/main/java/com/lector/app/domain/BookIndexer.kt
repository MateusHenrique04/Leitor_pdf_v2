package com.lector.app.domain

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/**
 * Constrói o [BookIndex]: extrai o texto bruto de TODAS as páginas, limpa (cabeçalho/rodapé repetidos só
 * aparecem olhando o livro todo) e planeja os trechos com o [ChunkPlanner]. Cancelável a cada página.
 * Lógica pura: quem extrai o texto é injetado em [extract] (PdfEngine no app, fake nos testes).
 */
object BookIndexer {
    suspend fun build(
        pageCount: Int,
        extract: suspend (pageIndex: Int) -> RawPage,
        onProgress: (donePages: Int, totalPages: Int) -> Unit = { _, _ -> },
    ): BookIndex {
        val raws = ArrayList<RawPage>(pageCount)
        for (p in 0 until pageCount) {
            currentCoroutineContext().ensureActive()
            raws.add(extract(p))
            onProgress(p + 1, pageCount)
        }
        currentCoroutineContext().ensureActive()
        val texts = TextCleaner(raws).cleanAll()
        val chunks = ChunkPlanner.planBook(texts)
        return BookIndex(ChunkPlanner.VERSION, pageCount, chunks)
    }
}
