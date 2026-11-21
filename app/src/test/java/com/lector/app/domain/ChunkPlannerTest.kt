package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChunkPlannerTest {
    // ---------- build_chunks (portado de tests/test_text.py) ----------

    @Test fun juntaFrasesCurtasDoMesmoParagrafo() =
        assertEquals(
            listOf("Primeira. Segunda. Terceira."),
            ChunkPlanner.buildChunks("Primeira. Segunda. Terceira.", targetChars = 200, maxChars = 400),
        )

    @Test fun nuncaJuntaParagrafosDiferentes() =
        assertEquals(
            listOf("Titulo da secao", "O texto do paragrafo comeca aqui."),
            ChunkPlanner.buildChunks("Titulo da secao\nO texto do paragrafo comeca aqui.", 500, 900),
        )

    @Test fun respeitaOTamanhoAlvo() {
        val texto = "Uma frase de tamanho conhecido para o teste. ".repeat(10)
        val chunks = ChunkPlanner.buildChunks(texto, targetChars = 100, maxChars = 200)
        assertTrue(chunks.size > 1)
        assertTrue(chunks.all { it.length <= 200 })
        assertTrue(chunks.all { it[0].isUpperCase() })
    }

    @Test fun quebraFraseGiganteEmPontosDeOracao() {
        val frase = "Primeira oracao bem comprida desta frase gigante, " +
            "segunda oracao igualmente comprida da mesma frase, " +
            "terceira oracao que fecha a frase toda."
        val chunks = ChunkPlanner.buildChunks(frase, targetChars = 60, maxChars = 80)
        assertTrue(chunks.size > 1)
        assertTrue(chunks.all { it.length <= 80 })
        assertEquals(frase, chunks.joinToString(" "))
    }

    @Test fun fraseSemPontoDeCorteNaoEMutilada() {
        val frase = "palavra ".repeat(40)
        val chunks = ChunkPlanner.buildChunks(frase.trim(), targetChars = 50, maxChars = 100)
        assertEquals(frase.replace(" ", ""), chunks.joinToString("").replace(" ", ""))
    }

    @Test fun textoVazio() {
        assertEquals(emptyList<String>(), ChunkPlanner.buildChunks(""))
        assertEquals(emptyList<String>(), ChunkPlanner.buildChunks("   \n  \n "))
    }

    // ---------- planBook ----------

    @Test fun indicesGlobaisEPorPagina() {
        val c = ChunkPlanner.planBook(listOf("Titulo\nTexto um.", "Outra pagina."))
        assertEquals(listOf("Titulo", "Texto um.", "Outra pagina."), c.map { it.text })
        assertEquals(listOf(0, 1, 2), c.map { it.index })
        assertEquals(listOf(0, 0, 1), c.map { it.pageIndex })
        assertEquals(listOf(0, 1, 0), c.map { it.indexInPage })
    }

    @Test fun paginaVaziaNaoGeraTrechos() {
        val c = ChunkPlanner.planBook(listOf("A.", "", "B."))
        assertEquals(listOf(0, 2), c.map { it.pageIndex })
        assertEquals(listOf(0, 1), c.map { it.index })
    }

    @Test fun livroVazio() = assertEquals(emptyList<Chunk>(), ChunkPlanner.planBook(emptyList()))

    @Test fun fraseQueCruzaPaginasViraUmTrecho() {
        val c = ChunkPlanner.planBook(
            listOf("Início da frase que continua", "na próxima página. Outra frase.\nNovo parágrafo."),
        )
        assertEquals(2, c.size)
        assertEquals("Início da frase que continua na próxima página. Outra frase.", c[0].text)
        assertEquals(0, c[0].pageIndex); assertEquals(1, c[0].endPageIndex); assertEquals(0, c[0].indexInPage)
        assertEquals("Novo parágrafo.", c[1].text)
        assertEquals(1, c[1].pageIndex); assertEquals(1, c[1].endPageIndex); assertEquals(0, c[1].indexInPage)
    }

    @Test fun hifenDeFimDePaginaEUnido() {
        val c = ChunkPlanner.planBook(listOf("A informa-", "ção continua aqui."))
        assertEquals(listOf("A informação continua aqui."), c.map { it.text })
        assertEquals(1, c[0].endPageIndex)
    }

    @Test fun maiusculaNaPaginaSeguinteNaoJunta() {
        val c = ChunkPlanner.planBook(listOf("Frase sem ponto final", "Começa com maiúscula."))
        assertEquals(2, c.size)
        assertEquals(listOf(0, 1), c.map { it.pageIndex })
    }

    @Test fun paginaTerminadaEmPontoNaoJunta() {
        val c = ChunkPlanner.planBook(listOf("Frase completa.", "continua em minúscula."))
        assertEquals(2, c.size)
    }

    @Test fun aspasAposOPontoContamComoFrasePronta() {
        val c = ChunkPlanner.planBook(listOf("Ele disse \"vamos embora.\"", "depois saiu."))
        assertEquals(2, c.size)
    }

    @Test fun paginaVaziaInterrompeAContinuacao() {
        val c = ChunkPlanner.planBook(listOf("Frase sem fim", "", "continua aqui."))
        assertEquals(2, c.size)
        assertEquals(listOf(0, 2), c.map { it.pageIndex })
    }

    @Test fun continuacaoEmCadeiaPorTresPaginas() {
        val c = ChunkPlanner.planBook(listOf("Começo da frase", "meio da frase", "fim da frase. Outra."))
        assertEquals(1, c.size)
        assertEquals("Começo da frase meio da frase fim da frase. Outra.", c[0].text)
        assertEquals(0, c[0].pageIndex); assertEquals(2, c[0].endPageIndex)
    }

    @Test fun trechoSeguinteQueFicaInteiroNaPaginaDoisContaComoDaPaginaDois() {
        val c = ChunkPlanner.planBook(
            listOf(
                "Uma frase longa que começa na primeira página e",
                "termina na segunda página. Depois vem outra frase completa aqui.",
            ),
            targetChars = 30, maxChars = 60,
        )
        assertEquals(2, c.size)
        assertEquals(0, c[0].pageIndex); assertEquals(1, c[0].endPageIndex)
        assertEquals(1, c[1].pageIndex); assertEquals(1, c[1].endPageIndex)
        assertEquals(0, c[1].indexInPage)
    }

    @Test fun planejamentoEDeterministico() {
        val paginas = listOf("Uma frase. Outra frase.\nTítulo", "e continua aqui. Fim.")
        assertEquals(ChunkPlanner.planBook(paginas), ChunkPlanner.planBook(paginas))
    }

    @Test fun versaoDoPlannerExiste() = assertEquals(1, ChunkPlanner.VERSION)
}
