package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WordAssemblerTest {
    private fun g(u: String, x: Float, base: Float = 100f, w: Float = 5f, h: Float = 10f) = Glyph(u, x, base, w, h)

    @Test fun separaPalavrasNoEspaco() {
        val words = WordAssembler.assemble(
            listOf(g("O", 10f), g("l", 15f), g("á", 20f), g(" ", 25f), g("m", 30f), g("u", 35f)),
        )
        assertEquals(listOf("Olá", "mu"), words.map { it.text })
    }

    @Test fun retanguloCobreOsGlifosDaPalavra() {
        val w = WordAssembler.assemble(listOf(g("a", 10f), g("b", 15f), g("c", 20f))).single()
        assertEquals(10f, w.x0, 0.001f)
        assertEquals(25f, w.x1, 0.001f)
        assertEquals(90f, w.y0, 0.001f)
        assertEquals(100f, w.y1, 0.001f) // y1 = linha de base
    }

    @Test fun usaMaiorAlturaELinhaDeBaseMaisBaixa() {
        val w = WordAssembler.assemble(listOf(g("a", 0f, 100f, 5f, 8f), g("b", 5f, 102f, 5f, 12f))).single()
        assertEquals(102f, w.y1, 0.001f)
        assertEquals(90f, w.y0, 0.001f)
    }

    @Test fun ligaduraContinuaUmaPalavra() {
        val words = WordAssembler.assemble(listOf(g("\uFB01", 0f), g("m", 5f)))
        assertEquals(listOf("\uFB01m"), words.map { it.text })
    }

    @Test fun glifoVazioNaoSeparaPalavra() {
        val words = WordAssembler.assemble(listOf(g("a", 0f), g("", 5f), g("b", 5f)))
        assertEquals(listOf("ab"), words.map { it.text })
    }

    @Test fun espacoNaoRompidoSeparaPalavra() {
        val words = WordAssembler.assemble(listOf(g("a", 0f), g("\u00A0", 5f), g("b", 10f)))
        assertEquals(listOf("a", "b"), words.map { it.text })
    }

    @Test fun soBrancosOuListaVaziaNaoGeramPalavras() {
        assertTrue(WordAssembler.assemble(emptyList()).isEmpty())
        assertTrue(WordAssembler.assemble(listOf(g(" ", 0f), g(" ", 5f))).isEmpty())
    }

    @Test fun separadorDeFimDePalavraNaoCriaPalavraVazia() {
        val words = WordAssembler.assemble(listOf(g("a", 0f), g(" ", 0f), g(" ", 0f), g("b", 10f), g(" ", 0f)))
        assertEquals(listOf("a", "b"), words.map { it.text })
    }
}
