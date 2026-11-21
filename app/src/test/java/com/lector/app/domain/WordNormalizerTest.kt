package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class WordNormalizerTest {
    @Test fun removePontuacaoEAspas() = assertEquals("mercados", normalizeWord("«Mercados»,"))
    @Test fun minusculaComAcento() = assertEquals("ação", normalizeWord("AÇÃO"))
    @Test fun naoQuebraAcentosUnicode() = assertEquals("não", normalizeWord("Não."))
    @Test fun ligaduraViraLetras() = assertEquals("final", normalizeWord("\uFB01nal"))
    @Test fun acentoCombinadoViraComposto() = assertEquals("á", normalizeWord("a\u0301"))
    @Test fun soPontuacaoViraVazio() = assertEquals("", normalizeWord("---"))
    @Test fun vazio() = assertEquals("", normalizeWord(""))
    @Test fun numerosFicam() = assertEquals("35", normalizeWord("3,5"))
    @Test fun sublinhadoFica() = assertEquals("a_b", normalizeWord("a_b"))
    @Test fun mesmaChaveParaVariacoes() = assertEquals(normalizeWord("Que,"), normalizeWord("\"que\""))
}
