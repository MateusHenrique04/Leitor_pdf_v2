package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TimingsCodecTest {
    private val timings = listOf(
        WordTiming("Olá,", 0.25f, 0.61f),
        WordTiming("mundo.", 0.7f, 1.2345679f),
        WordTiming("a\\b\tc\nd\re", 1.3f, 1.4f),
        WordTiming("ação😀", 1.5f, 2f),
    )

    @Test fun idaEVoltaPreservaTudo() {
        assertEquals(timings, TimingsCodec.decode(TimingsCodec.encode(timings)))
    }

    @Test fun vazioIdaEVolta() {
        assertEquals("", TimingsCodec.encode(emptyList()))
        assertEquals(emptyList<WordTiming>(), TimingsCodec.decode(""))
    }

    @Test fun textoMalformadoDevolveNull() {
        assertNull(TimingsCodec.decode("sem tabs\n"))
        assertNull(TimingsCodec.decode("x\t1.0\tpalavra\n"))
        assertNull(TimingsCodec.decode("1.0\t2.0\tpalavra")) // sem o \n final (cortado)
        assertNull(TimingsCodec.decode("1.0\t2.0\tfoo\\x\n")) // escape inválido
    }

    @Test fun palavraVaziaEhPermitida() {
        val t = listOf(WordTiming("", 0f, 0.1f))
        assertEquals(t, TimingsCodec.decode(TimingsCodec.encode(t)))
    }
}
