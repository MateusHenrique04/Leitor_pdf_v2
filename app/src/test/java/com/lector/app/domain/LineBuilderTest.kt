package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LineBuilderTest {
    /** Palavra com altura 10 e linha de base [base]. */
    private fun w(text: String, x0: Float, x1: Float, base: Float = 100f, h: Float = 10f) =
        WordBox(text, x0, base - h, x1, base)

    @Test fun listaVaziaNaoGeraLinhas() = assertTrue(LineBuilder.build(emptyList()).isEmpty())

    @Test fun palavrasNaMesmaLinhaDeBaseViramUmaLinha() {
        val lines = LineBuilder.build(listOf(w("Olá", 10f, 30f), w("mundo", 35f, 70f)))
        val line = lines.single()
        assertEquals("Olá mundo", line.text)
        assertEquals(10f, line.x0, 0.001f)
        assertEquals(70f, line.x1, 0.001f)
        assertEquals(100f, line.y1, 0.001f)
        assertEquals(10f, line.height, 0.001f)
    }

    @Test fun mudancaDeLinhaDeBaseCriaNovaLinha() {
        val lines = LineBuilder.build(listOf(w("a", 10f, 20f, 100f), w("b", 10f, 20f, 112f)))
        assertEquals(listOf("a", "b"), lines.map { it.text })
    }

    @Test fun sobrescritoFicaNaMesmaLinha() {
        val sup = WordBox("1", 40f, 91f, 44f, 96f) // altura 5, linha de base 96
        val lines = LineBuilder.build(listOf(w("texto", 10f, 38f), sup, w("depois", 46f, 80f)))
        val line = lines.single()
        assertEquals("texto 1 depois", line.text)
        assertEquals(100f, line.y1, 0.001f) // mediana das linhas de base
    }

    @Test fun voltarParaAEsquerdaNaMesmaAlturaIniciaNovaLinha() {
        val lines = LineBuilder.build(listOf(w("fim", 200f, 250f), w("coluna2", 20f, 80f)))
        assertEquals(2, lines.size)
    }

    @Test fun recuoPequenoPorKerningNaoQuebraLinha() {
        val lines = LineBuilder.build(listOf(w("a", 10f, 30f), w("b", 28f, 40f)))
        assertEquals(1, lines.size)
    }

    @Test fun ignoraPalavrasEmBranco() {
        val lines = LineBuilder.build(listOf(w(" ", 0f, 5f), w("ok", 10f, 20f)))
        assertEquals(listOf("ok"), lines.map { it.text })
    }
}
