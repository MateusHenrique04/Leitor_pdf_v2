package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TtsResultTest {
    @Test fun fimDaFalaEhUltimaPalavraMaisMargem() {
        val r = TTSResult(ByteArray(0), listOf(WordTiming("a", 0.3f, 0.6f), WordTiming("b", 0.7f, 1.234f)))
        assertEquals(1334L, r.speechEndMs)
    }

    @Test fun semPalavrasNaoCorta() {
        val r = TTSResult(ByteArray(0), emptyList())
        assertNull(r.speechEndMs)
        assertNull(r.speechEndSeconds)
    }
}
