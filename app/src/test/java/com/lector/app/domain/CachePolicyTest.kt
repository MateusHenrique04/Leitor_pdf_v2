package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class CachePolicyTest {
    private val timings = TimingsCodec.encode(listOf(WordTiming("olá", 0.25f, 0.6f)))

    private fun resolve(
        done: Boolean = true,
        path: String? = "/f/3.mp3",
        end: Long? = 900,
        t: String? = timings,
        exists: Boolean = true,
    ) = CachePolicy.resolve(done, path, end, t) { exists }

    @Test fun trechoProntoComArquivoETemposServe() {
        val c = resolve()
        assertNotNull(c)
        assertEquals("/f/3.mp3", c!!.path)
        assertEquals(900L, c.endMs)
        assertEquals(listOf(WordTiming("olá", 0.25f, 0.6f)), c.timings)
    }

    @Test fun naoServeSeNaoEstaPronto() = assertNull(resolve(done = false))

    @Test fun naoServeSeOArquivoSumiuDoDisco() = assertNull(resolve(exists = false))

    @Test fun naoServeSemCaminho() {
        assertNull(resolve(path = null))
        assertNull(resolve(path = " "))
    }

    @Test fun naoServeComTemposAusentesOuCorrompidos() {
        assertNull(resolve(t = null))
        assertNull(resolve(t = "lixo sem tabs\n"))
    }

    @Test fun semCorteDeFimAindaServe() {
        val c = resolve(end = null)
        assertNotNull(c)
        assertNull(c!!.endMs)
    }
}
