package com.lector.app.data

import com.lector.app.domain.BookIndex
import com.lector.app.domain.BookIndexCodec
import com.lector.app.domain.ChunkPlanner
import java.io.File

/**
 * Guarda o [BookIndex] em arquivo (um por livro e por versão do planner). Só usa java.io: testável no PC.
 * Bloqueante: chame fora da main thread. Em app real use `File(context.filesDir, "index")` (não o cache,
 * porque refazer o índice leva dezenas de segundos).
 */
class BookIndexStore(private val dir: File) {

    /** null se não existe, está corrompido, é de outra versão do planner ou o PDF mudou de nº de páginas. */
    fun load(bookId: String, pageCount: Int): BookIndex? {
        val f = file(bookId, ChunkPlanner.VERSION)
        if (!f.isFile) return null
        val index = BookIndexCodec.decode(f.readText(Charsets.UTF_8)) ?: return null
        return index.takeIf { it.plannerVersion == ChunkPlanner.VERSION && it.pageCount == pageCount }
    }

    /** Escrita atômica (arquivo temporário e depois rename); apaga índices de versões antigas do mesmo livro. */
    fun save(bookId: String, index: BookIndex) {
        dir.mkdirs()
        val target = file(bookId, index.plannerVersion)
        val tmp = File(dir, target.name + ".tmp")
        tmp.writeText(BookIndexCodec.encode(index), Charsets.UTF_8)
        target.delete()
        check(tmp.renameTo(target)) { "Falha ao gravar o índice do livro" }
        removeFiles(bookId) { it != target.name }
    }

    fun delete(bookId: String) = removeFiles(bookId) { true }

    private fun removeFiles(bookId: String, filter: (String) -> Boolean) {
        val prefix = "${safe(bookId)}.v"
        dir.listFiles()?.filter { it.name.startsWith(prefix) && filter(it.name) }?.forEach { it.delete() }
    }

    private fun file(bookId: String, version: Int) = File(dir, "${safe(bookId)}.v$version.idx")

    private fun safe(bookId: String): String {
        require(bookId.isNotEmpty() && bookId.all { it.isLetterOrDigit() || it == '-' }) { "bookId inválido: $bookId" }
        return bookId
    }
}
