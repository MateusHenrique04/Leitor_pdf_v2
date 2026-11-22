package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class FormattersTest {
    private val mb = 1024L * 1024

    @Test fun bytes() {
        assertEquals("512 B", Formatters.bytes(512))
        assertEquals("2 KB", Formatters.bytes(2048))
        assertEquals("5,0 MB", Formatters.bytes(5 * mb))
        assertEquals("150 MB", Formatters.bytes(150 * mb))
        assertEquals("1,50 GB", Formatters.bytes(1536 * mb))
    }

    @Test fun duracao() {
        assertEquals("45 s", Formatters.duration(45))
        assertEquals("10 min", Formatters.duration(600))
        assertEquals("1 h 00 min", Formatters.duration(3600))
        assertEquals("1 h 02 min", Formatters.duration(3725))
    }
}
