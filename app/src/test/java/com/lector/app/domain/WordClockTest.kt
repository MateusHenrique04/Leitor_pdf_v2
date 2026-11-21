package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class WordClockTest {
    private val t = listOf(
        WordTiming("um", 0.25f, 0.50f),
        WordTiming("dois", 0.60f, 0.90f),
        WordTiming("três", 1.00f, 1.40f),
    )

    @Test fun antesDaPrimeiraPalavra() = assertEquals(-1, WordClock.wordIndexAt(t, 0.10f))

    @Test fun noInicioExatoDeUmaPalavra() {
        assertEquals(0, WordClock.wordIndexAt(t, 0.25f))
        assertEquals(2, WordClock.wordIndexAt(t, 1.00f))
    }

    @Test fun noMeioDeUmaPalavraOuNoSilencioEntreElas() {
        assertEquals(0, WordClock.wordIndexAt(t, 0.55f)) // pausa entre "um" e "dois": segura a anterior
        assertEquals(1, WordClock.wordIndexAt(t, 0.75f))
    }

    @Test fun depoisDaUltimaFicaNaUltima() = assertEquals(2, WordClock.wordIndexAt(t, 9f))

    @Test fun semPalavras() = assertEquals(-1, WordClock.wordIndexAt(emptyList(), 1f))
}
