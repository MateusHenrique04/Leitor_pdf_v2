package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HighlightTest {
    private fun r(x0: Float, y0: Float) = WordRect(x0, y0, x0 + 30f, y0 + 10f)
    private fun w(page: Int, rect: WordRect?) = SyncedWord(0f, 0.4f, page, rect)

    private val words = listOf(
        w(0, r(10f, 50f)), w(0, r(50f, 50f)), w(0, null), w(0, r(10f, 80f)),
        w(1, r(10f, 20f)), w(1, r(50f, 20f)),
    )

    @Test fun palavraAtualEAsLinhasDoTrecho() {
        val h = HighlightBuilder.build(0, words, 1)
        assertEquals(0, h.page)
        assertEquals(r(50f, 50f), h.word)
        assertEquals(2, h.lines.size) // y=50 (2 palavras juntas) e y=80
    }

    @Test fun palavraSemRetanguloMantemAAnterior() {
        val h = HighlightBuilder.build(0, words, 2)
        assertEquals(r(50f, 50f), h.word)
    }

    @Test fun antesDaPrimeiraPalavraSoMostraAsLinhas() {
        val h = HighlightBuilder.build(0, words, -1)
        assertNull(h.word)
        assertEquals(0, h.page)
        assertTrue(h.lines.isNotEmpty())
    }

    @Test fun trechoQueCruzaPaginaGrifaNaPaginaDaPalavraAtual() {
        val h = HighlightBuilder.build(0, words, 4)
        assertEquals(1, h.page)
        assertEquals(r(10f, 20f), h.word)
        assertEquals(1, h.lines.size) // só as linhas da pág. 1
    }

    @Test fun nenhumaPalavraLocalizadaUsaAPaginaDeReserva() {
        val h = HighlightBuilder.build(7, listOf(w(7, null), w(7, null)), 1)
        assertEquals(7, h.page)
        assertNull(h.word)
        assertTrue(h.lines.isEmpty())
    }

    @Test fun semPalavras() {
        val h = HighlightBuilder.build(3, emptyList(), 0)
        assertEquals(3, h.page)
        assertNull(h.word)
    }

    @Test fun indiceAlemDoFimUsaAUltima() {
        val h = HighlightBuilder.build(0, words, 99)
        assertEquals(r(50f, 20f), h.word)
    }
}
