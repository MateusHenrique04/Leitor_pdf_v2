package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TextCleanerTest {
    private fun page(vararg blocks: List<String>) = RawPage(blocks.toList())
    private fun clean(p: RawPage) = TextCleaner(listOf(p)).cleanPage(0)

    @Test fun juntaLinhasDoMesmoBlocoComEspaco() =
        assertEquals("A casa é grande e bonita.", clean(page(listOf("A casa é", "grande e bonita."))))

    @Test fun blocosViramParagrafosSeparadosPorNovaLinha() =
        assertEquals("Título\nTexto do parágrafo.", clean(page(listOf("Título"), listOf("Texto do parágrafo."))))

    @Test fun unePalavraHifenizadaNoMesmoBloco() =
        assertEquals("Esta é a informação completa.", clean(page(listOf("Esta é a informa-", "ção completa."))))

    @Test fun unePalavraHifenizadaEntreBlocos() =
        assertEquals("Esta é a informação do texto.", clean(page(listOf("Esta é a informa-"), listOf("ção do texto."))))

    @Test fun removeNumeroDePaginaIsolado() =
        assertEquals("Texto", clean(page(listOf("17"), listOf("Texto"))))

    @Test fun mantemNumeroDentroDeFrase() =
        assertEquals("Cap 17 é longo.", clean(page(listOf("Cap 17 é longo."))))

    @Test fun colapsaEspacosETabs() = assertEquals("a b c", clean(page(listOf("a   b\t\tc"))))

    @Test fun normalizaLigaturasNFKC() = assertEquals("final", clean(page(listOf("\uFB01nal"))))

    @Test fun paginaVaziaEForaDoIntervaloDevolvemVazio() {
        val c = TextCleaner(listOf(RawPage(emptyList())))
        assertEquals("", c.cleanPage(0))
        assertEquals("", c.cleanPage(5))
        assertEquals("", c.cleanPage(-1))
    }

    @Test fun removeCabecalhoERodapeRepetidos() {
        val pages = (1..5).map { i ->
            page(listOf("Editora X"), listOf("Corpo da página $i com texto único."), listOf("Rodapé fixo"))
        }
        val c = TextCleaner(pages)
        assertEquals("Corpo da página 2 com texto único.", c.cleanPage(1))
        assertTrue("Editora X" in c.skipKeys && "Rodapé fixo" in c.skipKeys)
    }

    @Test fun removeRodapeCujoNumeroMuda() {
        val pages = (1..4).map { i -> page(listOf("Cabeçalho fixo"), listOf("Conteúdo $i."), listOf("Página $i")) }
        val c = TextCleaner(pages)
        assertEquals("Conteúdo 3.", c.cleanPage(2))
        assertTrue("Página #" in c.skipKeys)
    }

    @Test fun linhaLongaComNumeroNaoEMascarada() {
        val pages = (1..4).map { i ->
            page(
                listOf("Este parágrafo longo de texto corrido aumentou $i por cento naquele ano, segundo o relatório."),
                listOf("Fim."),
            )
        }
        val c = TextCleaner(pages)
        assertEquals(
            "Este parágrafo longo de texto corrido aumentou 2 por cento naquele ano, segundo o relatório.\nFim.",
            c.cleanPage(1),
        )
    }

    @Test fun skipKeyDeLinhaLongaComDigitoEhNulo() {
        assertNull(TextCleaner.skipKey("x".repeat(40) + " 12 " + "y".repeat(40)))
        assertEquals("Página #", TextCleaner.skipKey("Página 17"))
        assertEquals("sem digitos", TextCleaner.skipKey("  sem digitos "))
    }

    @Test fun abaixoDoLimiarDeRepeticaoNaoRemove() {
        // 10 páginas -> limiar = max(3, 3) = 3; o cabeçalho aparece só em 2.
        val pages = (0 until 10).map { i ->
            val top = if (i < 2) "Cabeçalho raro" else "Abertura ${'a' + i}"
            page(listOf(top), listOf("Corpo ${'a' + i}."))
        }
        val c = TextCleaner(pages)
        assertEquals("Cabeçalho raro\nCorpo a.", c.cleanPage(0))
    }

    @Test fun pageLengthsSomaCaracteresDasLinhas() {
        val c = TextCleaner(listOf(RawPage(listOf(listOf("abc", "de"))), RawPage(emptyList())))
        assertEquals(listOf(5, 0), c.pageLengths)
    }

    @Test fun cleanAllCobreTodasAsPaginas() {
        val c = TextCleaner(listOf(page(listOf("Um.")), page(listOf("Dois."))))
        assertEquals(listOf("Um.", "Dois."), c.cleanAll())
    }
}
