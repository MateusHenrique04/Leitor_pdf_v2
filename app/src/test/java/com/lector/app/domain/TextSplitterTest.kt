package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Portado de tests/test_text.py (split_sentences). */
class TextSplitterTest {
    private fun split(s: String) = TextSplitter.splitSentences(s)

    @Test fun textoVazio() {
        assertEquals(emptyList<String>(), split(""))
        assertEquals(emptyList<String>(), split("   "))
    }

    @Test fun duasFrasesSimples() =
        assertEquals(listOf("Isso e uma frase.", "Isso e outra."), split("Isso e uma frase. Isso e outra."))

    @Test fun quebraEmNovaLinha() =
        assertEquals(listOf("Primeira linha", "Segunda linha"), split("Primeira linha\nSegunda linha"))

    @Test fun naoQuebraEmAbreviacoesComuns() =
        assertEquals(
            listOf("O Dr. Silva chegou.", "A Sra. Costa tambem."),
            split("O Dr. Silva chegou. A Sra. Costa tambem."),
        )

    @Test fun naoQuebraEmAbreviacaoDePagina() =
        assertEquals(
            listOf("Veja a p. 23 para mais detalhes.", "Depois continue."),
            split("Veja a p. 23 para mais detalhes. Depois continue."),
        )

    @Test fun figNuncaQuebraEEtcFechaFrase() =
        assertEquals(
            listOf("Compare com a Fig. 3, etc.", "Isso encerra o ponto."),
            split("Compare com a Fig. 3, etc. Isso encerra o ponto."),
        )

    @Test fun etcSeguidoDeMinusculaNaoQuebra() =
        assertEquals(
            listOf("Trouxe livros, canetas, etc. para a aula de hoje."),
            split("Trouxe livros, canetas, etc. para a aula de hoje."),
        )

    @Test fun naoQuebraEmDecimais() =
        assertEquals(
            listOf("O valor subiu para 3.5 no ultimo mes.", "Isso e bom."),
            split("O valor subiu para 3.5 no ultimo mes. Isso e bom."),
        )

    @Test fun reticenciasFicamNaMesmaFrase() =
        assertEquals(listOf("Ele hesitou... e decidiu sair."), split("Ele hesitou... e decidiu sair."))

    @Test fun abreviacoesEmIngles() =
        assertEquals(
            listOf("Mr. Smith arrived.", "Sra. Lopez tambien llego."),
            split("Mr. Smith arrived. Sra. Lopez tambien llego."),
        )

    @Test fun nenhumCasoComumGeraFraseVazia() {
        val r = split("Frase um.   Frase dois.\n\nFrase tres.")
        assertTrue(r.all { it.isNotBlank() })
        assertEquals(3, r.size)
    }

    @Test fun caractereDeControleNuncaVazaParaOResultado() {
        val r = split("Dr. Silva viu 3.5 itens... e saiu, etc. depois.")
        assertTrue(r.none { it.contains('\u0000') })
    }

    @Test fun abreviacaoComAcentoEMaiuscula() =
        assertEquals(listOf("Veja a Pág. 5 agora."), split("Veja a Pág. 5 agora."))

    @Test fun naoTrataFimDePalavraComoAbreviacao() {
        // "grupo." termina em "p" mas NÃO é a abreviação "p." (precisa ser palavra isolada)
        assertEquals(listOf("Ele saiu do grupo.", "Voltou depois."), split("Ele saiu do grupo. Voltou depois."))
    }

    @Test fun fraseLongaSemPontoDeCorteNaoEMutilada() {
        val s = "palavra ".repeat(40).trim()
        assertEquals(listOf(s), TextSplitter.splitLongSentence(s, 100))
    }

    @Test fun fraseCurtaNaoEQuebrada() =
        assertFalse(TextSplitter.splitLongSentence("curta, mas ok", 100).size > 1)
}
