package com.lector.app.domain

import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BookIndexerTest {
    private fun raw(vararg paragraphs: String) = RawPage(paragraphs.map { listOf(it) })

    private val pages = listOf(
        raw("Cabeçalho do livro", "Primeira frase da página um. Segunda frase da página um.", "Uma frase que não termina e"),
        raw("Cabeçalho do livro", "continua na página dois. Outra frase aqui.", "Texto final da página dois."),
        raw("Cabeçalho do livro", "Terceira página, com apenas uma frase."),
        raw("Cabeçalho do livro", "Quarta página, curta."),
    )

    @Test fun igualAoPlanejamentoDireto() = runBlocking {
        val esperado = ChunkPlanner.planBook(TextCleaner(pages).cleanAll())
        val index = BookIndexer.build(pages.size, { pages[it] })
        assertEquals(esperado, index.chunks)
        assertEquals(ChunkPlanner.VERSION, index.plannerVersion)
        assertEquals(pages.size, index.pageCount)
        assertTrue(index.chunks.isNotEmpty())
    }

    @Test fun juntaFraseQueCruzaPaginas() = runBlocking {
        val index = BookIndexer.build(pages.size, { pages[it] })
        val cruza = index.chunks.filter { it.endPageIndex > it.pageIndex }
        assertTrue("devia haver um trecho cruzando da pág 0 para a 1", cruza.any { it.pageIndex == 0 && it.endPageIndex == 1 })
    }

    @Test fun informaProgressoPaginaAPagina() = runBlocking {
        val calls = ArrayList<Pair<Int, Int>>()
        BookIndexer.build(pages.size, { pages[it] }, { d, t -> calls.add(d to t) })
        assertEquals(listOf(1 to 4, 2 to 4, 3 to 4, 4 to 4), calls)
    }

    @Test fun livroSemPaginasOuSemTextoDaIndiceVazio() = runBlocking {
        assertTrue(BookIndexer.build(0, { error("não devia extrair") }).isEmpty)
        assertTrue(BookIndexer.build(3, { RawPage(emptyList()) }).isEmpty)
    }

    @Test fun cancelamentoParaNaProximaPagina() = runBlocking {
        var calls = 0
        val job = launch {
            BookIndexer.build(100, {
                calls++
                if (calls == 3) currentCoroutineContext().cancel()
                raw("Texto $it.")
            })
        }
        job.join()
        assertTrue(job.isCancelled)
        assertEquals(3, calls)
    }
}
