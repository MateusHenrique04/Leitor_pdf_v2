package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DownloadEstimatorTest {
    @Test fun estimaTempoETamanho() {
        // 290 caracteres a 14,5 car/s = 20 s + 1,2 s de overhead = 21,2 s -> 127.200 bytes
        val e = DownloadEstimator.estimate(listOf(290))
        assertEquals(1, e.chunks)
        assertEquals(21L, e.audioSeconds)
        assertEquals(127_200L, e.bytes)
    }

    @Test fun somaVariosTrechos() {
        val e = DownloadEstimator.estimate(listOf(145, 145, 145)) // 3 x (10 s + 1,2 s)
        assertEquals(3, e.chunks)
        assertEquals(33L, e.audioSeconds)
    }

    @Test fun semTrechosEZero() {
        val e = DownloadEstimator.estimate(emptyList())
        assertEquals(0L, e.bytes)
    }

    @Test fun espacoPrecisaCobrirMargemEReserva() {
        val need = 200L * 1024 * 1024
        val reserve = DownloadEstimator.RESERVE_BYTES
        assertTrue(DownloadEstimator.enoughSpace(need, (need * 1.15).toLong() + reserve))
        assertFalse(DownloadEstimator.enoughSpace(need, need)) // sobra zero: não é suficiente
        assertFalse(DownloadEstimator.enoughSpace(need, (need * 1.15).toLong() + reserve - 1))
    }

    @Test fun vozesOferecidas() {
        assertEquals(3, Voices.ALL.size)
        assertEquals("pt-BR-AntonioNeural", Voices.DEFAULT_ID)
        assertEquals("en-US", Voices.byId("en-US-GuyNeural")?.language)
        assertEquals("es-ES", Voices.byId("es-ES-AlvaroNeural")?.language)
    }
}
