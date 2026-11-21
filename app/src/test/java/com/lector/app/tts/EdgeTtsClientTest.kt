package com.lector.app.tts

import com.lector.app.domain.TTSResult
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

class EdgeTtsClientTest {

    // ---------- falsos ----------

    private class FakeSocket(script: List<EdgeFrame>, closeAfter: Boolean = true) : EdgeSocket {
        val sent = ArrayList<String>()
        var closed = false
        private val channel = Channel<EdgeFrame>(Channel.UNLIMITED).also { ch ->
            script.forEach { ch.trySend(it) }
            if (closeAfter) ch.close()
        }
        override val frames: ReceiveChannel<EdgeFrame> get() = channel
        override fun send(text: String) {
            sent.add(text)
        }

        override fun close() {
            closed = true
        }
    }

    private class FakeTransport(private val steps: List<() -> EdgeSocket>) : EdgeTransport {
        val urls = ArrayList<String>()
        val headers = ArrayList<Map<String, String>>()
        var connects = 0
        override suspend fun connect(url: String, headers: Map<String, String>): EdgeSocket {
            urls.add(url)
            this.headers.add(headers)
            return steps[connects++]()
        }
    }

    private fun text(path: String, body: String = "") =
        EdgeFrame.Text("X-Timestamp:t\r\nContent-Type:application/json\r\nPath:$path\r\n\r\n$body")

    private fun audio(bytes: ByteArray, contentType: String? = "audio/mpeg", path: String = "audio"): EdgeFrame {
        val header = "X-RequestId:a\r\n" + (if (contentType != null) "Content-Type:$contentType\r\n" else "") + "Path:$path\r\n"
        val h = header.toByteArray(Charsets.UTF_8)
        return EdgeFrame.Binary(byteArrayOf((h.size shr 8).toByte(), (h.size and 0xFF).toByte()) + h + bytes)
    }

    private fun word(w: String, offset: Long, duration: Long) = text(
        "audio.metadata",
        """{"Metadata":[{"Type":"WordBoundary","Data":{"Offset":$offset,"Duration":$duration,""" +
            """"text":{"Text":"$w","Length":${w.length},"BoundaryType":"WordBoundary"}}}]}""",
    )

    private fun okTurn(bytes: ByteArray, vararg words: EdgeFrame): List<EdgeFrame> =
        listOf(text("turn.start"), text("response")) + words + listOf(audio(bytes), text("turn.end"))

    private val voice = "pt-BR-FranciscaNeural"

    private fun client(t: EdgeTransport, clock: DrmClock = DrmClock({ 1763553600.0 }), max: Int = 4096, timeout: Long = 2000) =
        EdgeTtsClient(t, clock, timeout, max)

    // ---------- testes ----------

    @Test fun sintetizaAudioETimings() = runBlocking {
        val s = FakeSocket(
            listOf(text("turn.start"), word("Olá", 2_500_000, 3_000_000), word("mundo", 5_500_000, 4_000_000)) +
                listOf(audio(byteArrayOf(1, 2, 3)), audio(byteArrayOf(4, 5)), text("turn.end")),
        )
        val t = FakeTransport(listOf({ s }))
        val r = client(t).synthesize("Olá mundo", voice)

        assertArrayEquals(byteArrayOf(1, 2, 3, 4, 5), r.audioBytes)
        assertEquals(listOf("Olá", "mundo"), r.timings.map { it.word })
        assertEquals(0.25f, r.timings[0].startSeconds, 0.0001f)
        assertEquals(0.55f, r.timings[0].endSeconds, 0.0001f)
        assertEquals(0.55f, r.timings[1].startSeconds, 0.0001f)
        assertEquals(0.95f, r.timings[1].endSeconds, 0.0001f)
        assertEquals(1.05f, r.speechEndSeconds!!, 0.0001f)
        assertTrue(s.closed)
    }

    @Test fun enviaConfiguracaoESsmlNaOrdemCerta() = runBlocking {
        val s = FakeSocket(okTurn(byteArrayOf(1)))
        val t = FakeTransport(listOf({ s }))
        client(t).synthesize("Tom & Jerry <3", voice, speedPct = 0)

        assertEquals(2, s.sent.size)
        assertTrue(s.sent[0].contains("Path:speech.config"))
        assertTrue(s.sent[0].contains("\"wordBoundaryEnabled\":\"true\""))
        assertTrue(s.sent[1].contains("Path:ssml"))
        assertTrue(s.sent[1].contains("<voice name='Microsoft Server Speech Text to Speech Voice (pt-BR, FranciscaNeural)'>"))
        assertTrue(s.sent[1].contains("rate='+0%'"))
        assertTrue(s.sent[1].contains("Tom &amp; Jerry &lt;3"))
    }

    @Test fun urlETokenCookie() = runBlocking {
        val t = FakeTransport(listOf({ FakeSocket(okTurn(byteArrayOf(1))) }))
        client(t).synthesize("oi", voice)

        val url = t.urls.single()
        assertTrue(url.startsWith("wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken="))
        assertTrue(url.contains("&ConnectionId="))
        assertTrue(url.contains("&Sec-MS-GEC=" + EdgeDrm.generateSecMsGec(1763553600.0, EdgeConstants.TRUSTED_CLIENT_TOKEN)))
        assertTrue(url.endsWith("&Sec-MS-GEC-Version=1-143.0.3650.75"))
        val h = t.headers.single()
        assertTrue(Regex("muid=[0-9A-F]{32};").matches(h.getValue("Cookie")))
        assertEquals("chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold", h["Origin"])
    }

    @Test fun textoLongoUsaVariasConexoesECompensaOsTempos() = runBlocking {
        // 6000 bytes de MP3 = 1 s = 10.000.000 ticks na parte 1; os tempos da parte 2 somam isso.
        val s1 = FakeSocket(okTurn(ByteArray(6000), word("um", 2_500_000, 1_000_000)))
        val s2 = FakeSocket(okTurn(ByteArray(3000), word("dois", 2_500_000, 1_000_000)))
        val t = FakeTransport(listOf({ s1 }, { s2 }))
        val r = client(t, max = 12).synthesize("aaaaaaaaaa bbbbbbbbbb", voice)

        assertEquals(2, t.connects)
        assertEquals(9000, r.audioBytes.size)
        assertEquals(0.25f, r.timings[0].startSeconds, 0.0001f)
        assertEquals(1.25f, r.timings[1].startSeconds, 0.0001f)
        assertTrue(s1.sent[1].contains(">aaaaaaaaaa<"))
        assertTrue(s2.sent[1].contains(">bbbbbbbbbb<"))
    }

    @Test fun erro403CorrigeORelogioETentaDeNovo() = runBlocking {
        val serverDate = "Thu, 19 Nov 2026 12:10:00 GMT"
        val serverEpoch = ZonedDateTime.parse(serverDate, DateTimeFormatter.RFC_1123_DATE_TIME).toEpochSecond().toDouble()
        val clock = DrmClock({ 1763553600.0 })
        val t = FakeTransport(
            listOf(
                { throw EdgeHttpException(403, serverDate, "Forbidden") },
                { FakeSocket(okTurn(byteArrayOf(1))) },
            ),
        )
        client(t, clock).synthesize("oi", voice)

        assertEquals(2, t.connects)
        assertEquals(serverEpoch, clock.now(), 0.001)
        // O segundo token usa o relógio corrigido.
        assertTrue(t.urls[1].contains("&Sec-MS-GEC=" + EdgeDrm.generateSecMsGec(serverEpoch, EdgeConstants.TRUSTED_CLIENT_TOKEN)))
    }

    @Test fun doisErros403Falham() = runBlocking {
        val t = FakeTransport(listOf({ throw EdgeHttpException(403, "Thu, 19 Nov 2026 12:10:00 GMT", "x") }, { throw EdgeHttpException(403, "Thu, 19 Nov 2026 12:10:00 GMT", "x") }))
        try {
            client(t).synthesize("oi", voice)
            fail()
        } catch (e: EdgeHttpException) {
            assertEquals(403, e.statusCode)
            assertEquals(2, t.connects)
        }
    }

    @Test fun erro403SemDataNaoTentaDeNovo() = runBlocking {
        val t = FakeTransport(listOf({ throw EdgeHttpException(403, null, "x") }))
        try {
            client(t).synthesize("oi", voice)
            fail()
        } catch (e: SkewAdjustmentError) {
            assertEquals(1, t.connects)
        }
    }

    @Test fun outroCodigoHttpNaoTentaDeNovo() = runBlocking {
        val t = FakeTransport(listOf({ throw EdgeHttpException(500, null, "x") }))
        try {
            client(t).synthesize("oi", voice)
            fail()
        } catch (e: EdgeHttpException) {
            assertEquals(500, e.statusCode)
            assertEquals(1, t.connects)
        }
    }

    @Test fun semAudioFalha() = runBlocking {
        val s = FakeSocket(listOf(text("turn.start"), text("turn.end")))
        try {
            client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
            fail()
        } catch (e: NoAudioReceived) {
            assertTrue(s.closed)
        }
    }

    @Test fun conexaoQueCaiAntesDoTurnEndFalha() = runBlocking {
        val s = FakeSocket(listOf(text("turn.start"), audio(byteArrayOf(1, 2))))
        try {
            client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
            fail()
        } catch (e: WebSocketError) {
            assertTrue(s.closed)
        }
    }

    @Test fun falhaDeRedeNoMeioFalha() = runBlocking {
        val s = FakeSocket(listOf(text("turn.start"), EdgeFrame.Failure(java.io.IOException("queda"))))
        try {
            client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
            fail()
        } catch (e: WebSocketError) {
            assertEquals("queda", e.message)
        }
    }

    @Test fun caminhoDesconhecidoFalha() = runBlocking {
        val s = FakeSocket(listOf(text("coisa.estranha")))
        try {
            client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
            fail()
        } catch (e: UnknownResponse) {
        }
    }

    @Test fun tipoDeConteudoInesperadoFalha() = runBlocking {
        val s = FakeSocket(listOf(audio(byteArrayOf(1), contentType = "audio/ogg")))
        try {
            client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
            fail()
        } catch (e: UnexpectedResponse) {
        }
    }

    @Test fun mensagemFinalSemTipoNemDadosEhIgnorada() = runBlocking {
        val s = FakeSocket(
            listOf(audio(byteArrayOf(9)), audio(ByteArray(0), contentType = null), text("turn.end")),
        )
        val r = client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
        assertArrayEquals(byteArrayOf(9), r.audioBytes)
    }

    @Test fun audioVazioComTipoFalha() = runBlocking {
        val s = FakeSocket(listOf(audio(ByteArray(0))))
        try {
            client(FakeTransport(listOf({ s }))).synthesize("oi", voice)
            fail()
        } catch (e: UnexpectedResponse) {
        }
    }

    @Test fun servidorQueNaoRespondeDaTimeout() = runBlocking {
        val s = FakeSocket(listOf(text("turn.start")), closeAfter = false)
        try {
            client(FakeTransport(listOf({ s })), timeout = 50).synthesize("oi", voice)
            fail()
        } catch (e: WebSocketError) {
            assertTrue(e.message!!.contains("não respondeu"))
            assertTrue(s.closed)
        }
    }

    @Test fun textoVazioEVozInvalida() = runBlocking {
        val t = FakeTransport(emptyList())
        try {
            client(t).synthesize("   ", voice)
            fail()
        } catch (e: NoAudioReceived) {
        }
        try {
            client(t).synthesize("oi", "voz errada")
            fail()
        } catch (e: IllegalArgumentException) {
        }
        assertEquals(0, t.connects)
    }

    @Test fun velocidadeEntraNoSsml() = runBlocking {
        val s = FakeSocket(okTurn(byteArrayOf(1)))
        client(FakeTransport(listOf({ s }))).synthesize("oi", voice, speedPct = -25)
        assertTrue(s.sent[1].contains("rate='-25%'"))
    }

    @Test fun fimDaFalaSemPalavrasEhNulo() {
        assertEquals(null, TTSResult(ByteArray(0), emptyList()).speechEndSeconds)
        assertFalse(TTSResult(ByteArray(0), emptyList()).timings.isNotEmpty())
    }
}
