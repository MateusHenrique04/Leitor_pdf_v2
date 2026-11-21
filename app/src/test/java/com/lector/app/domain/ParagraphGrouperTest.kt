package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ParagraphGrouperTest {
    /** Linha de altura [h] com linha de base [base]; larga (x1 = 300) por padrão. */
    private fun ln(text: String, base: Float, x0: Float = 50f, x1: Float = 300f, h: Float = 10f) =
        TextLine(text, x0, base - h, x1, base)

    private fun sizes(blocks: List<List<String>>) = blocks.map { it.size }

    @Test fun semLinhasNaoHaBlocos() {
        assertTrue(ParagraphGrouper.group(emptyList()).isEmpty())
        assertTrue(ParagraphGrouper.group(listOf(ln("  ", 100f))).isEmpty())
    }

    @Test fun linhasSeguidasSemSinaisFormamUmParagrafo() {
        val blocks = ParagraphGrouper.group(listOf(ln("a", 100f), ln("b", 112f), ln("fim.", 124f, x1 = 200f)))
        assertEquals(listOf(listOf("a", "b", "fim.")), blocks)
    }

    @Test fun espacoVerticalMaiorQueOTipicoCriaParagrafo() {
        val blocks = ParagraphGrouper.group(
            listOf(ln("a", 100f), ln("b", 112f), ln("c.", 124f), ln("d", 148f), ln("e.", 160f)),
        )
        assertEquals(listOf(3, 2), sizes(blocks))
    }

    @Test fun recuoDeInicioDeParagrafoCriaParagrafoQuandoALinhaAnteriorTerminaEmFrase() {
        val blocks = ParagraphGrouper.group(
            listOf(
                ln("um", 100f, x0 = 60f), ln("dois", 112f), ln("tres.", 124f),
                ln("quatro", 136f, x0 = 60f), ln("cinco.", 148f),
            ),
        )
        assertEquals(listOf(3, 2), sizes(blocks))
    }

    @Test fun recuoSemFimDeFraseNaoQuebra() {
        // Lista com recuo suspenso: a linha anterior não termina a frase.
        val blocks = ParagraphGrouper.group(listOf(ln("item longo que", 100f), ln("continua aqui.", 112f, x0 = 70f)))
        assertEquals(listOf(2), sizes(blocks))
    }

    @Test fun linhaCurtaQueTerminaEmFraseEncerraOParagrafo() {
        val blocks = ParagraphGrouper.group(
            listOf(ln("a", 100f), ln("b", 112f), ln("fim do paragrafo.", 124f, x1 = 150f), ln("novo", 136f), ln("texto.", 148f)),
        )
        assertEquals(listOf(3, 2), sizes(blocks))
    }

    @Test fun linhaCurtaSemPontuacaoNaoQuebra() {
        // Texto alinhado à esquerda: linhas de comprimentos variados no meio da frase.
        val blocks = ParagraphGrouper.group(
            listOf(ln("a", 100f), ln("palavra comprida", 112f, x1 = 220f), ln("c", 124f)),
        )
        assertEquals(listOf(3), sizes(blocks))
    }

    @Test fun pontuacaoFinalComAspasFechandoContaComoFimDeFrase() {
        assertTrue(ParagraphGrouper.endsSentence("disse \u201Cadeus.\u201D"))
        assertTrue(ParagraphGrouper.endsSentence("acabou? "))
        assertFalse(ParagraphGrouper.endsSentence("informa-"))
        assertFalse(ParagraphGrouper.endsSentence("vírgula,"))
    }

    @Test fun mudancaDeColunaCriaNovoBlocoEOutraBordaDireita() {
        // Coluna esquerda (x 50..300) e direita (x 320..570) começando mais acima.
        val left = listOf(ln("e1", 100f, 50f, 300f), ln("e2", 112f, 50f, 300f), ln("e3", 124f, 50f, 300f))
        val right = listOf(ln("d1", 100f, 320f, 570f), ln("d2", 112f, 320f, 570f))
        val blocks = ParagraphGrouper.group(left + right)
        assertEquals(listOf(listOf("e1", "e2", "e3"), listOf("d1", "d2")), blocks)
    }

    @Test fun linhaCurtaEmColunaEstreitaNaoViraQuebraPorCausaDaOutraColuna() {
        // A borda direita é calculada por coluna: e2 chega à borda da coluna esquerda (300), não da direita (570).
        val left = listOf(ln("e1.", 100f, 50f, 290f), ln("e2", 112f, 50f, 300f))
        val right = listOf(ln("d1", 100f, 320f, 570f))
        val blocks = ParagraphGrouper.group(left + right)
        assertEquals(listOf(2, 1), sizes(blocks))
    }

    @Test fun mudancaDeFonteSeparaTituloDoTexto() {
        val blocks = ParagraphGrouper.group(
            listOf(
                ln("Capítulo", 100f, h = 14f, x1 = 120f), ln("texto", 114f), ln("texto.", 126f), ln("texto", 138f),
            ),
        )
        assertEquals(listOf(1, 3), sizes(blocks))
    }

    @Test fun umaUnicaLinhaVira1Bloco() {
        assertEquals(listOf(listOf("só")), ParagraphGrouper.group(listOf(ln("só", 100f))))
    }
}
