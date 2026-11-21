package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

/** Palavras -> linhas -> parágrafos -> texto limpo -> trechos (tudo Kotlin puro, sem PDF). */
class TextPipelineTest {
    private fun w(text: String, x0: Float, x1: Float, base: Float) = WordBox(text, x0, base - 10f, x1, base)

    @Test fun hifenizacaoNoFimDaLinhaVoltaInteira() {
        val words = listOf(
            w("Esta", 10f, 30f, 100f), w("é", 35f, 40f, 100f), w("a", 45f, 50f, 100f), w("informa-", 55f, 100f, 100f),
            w("ção", 10f, 30f, 112f), w("completa.", 35f, 90f, 112f),
        )
        val raw = RawPage(ParagraphGrouper.group(LineBuilder.build(words)))
        assertEquals("Esta é a informação completa.", TextCleaner(listOf(raw)).cleanPage(0))
    }

    @Test fun doisParagrafosGeramDoisTrechos() {
        val words = listOf(
            w("Primeiro", 10f, 70f, 100f), w("parágrafo.", 75f, 140f, 100f),
            w("Segundo", 10f, 60f, 130f), w("parágrafo.", 65f, 130f, 130f),
        )
        val raw = RawPage(ParagraphGrouper.group(LineBuilder.build(words)))
        val text = TextCleaner(listOf(raw)).cleanPage(0)
        assertEquals("Primeiro parágrafo.\nSegundo parágrafo.", text)
        assertEquals(2, ChunkPlanner.buildChunks(text).size)
    }
}
