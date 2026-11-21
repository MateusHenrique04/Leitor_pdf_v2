package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class TextCleanerSoftHyphenTest {
    private fun clean(vararg blocks: List<String>) = TextCleaner(listOf(RawPage(blocks.toList()))).cleanPage(0)

    @Test fun hifenSuaveNoFimDaLinhaUneAPalavraNoMesmoBloco() =
        assertEquals("a tradução do percurso", clean(listOf("a tradução do per\u00AD", "curso")))

    @Test fun hifenSuaveEntreBlocosUneAPalavra() =
        assertEquals("o ensaio protestante.", clean(listOf("o ensaio protestan\u00AD"), listOf("te.")))

    @Test fun hifenUnicode2010UneAPalavra() =
        assertEquals("informação completa", clean(listOf("informa\u2010", "ção completa")))

    @Test fun hifenSuaveSobranteNoMeioDaLinhaEhRemovido() =
        assertEquals("percurso", clean(listOf("per\u00ADcurso")))

    @Test fun hifenComumContinuaUnindo() =
        assertEquals("informação", clean(listOf("informa-", "ção")))
}
