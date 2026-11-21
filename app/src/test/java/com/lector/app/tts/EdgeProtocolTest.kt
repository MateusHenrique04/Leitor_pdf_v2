package com.lector.app.tts

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.time.Instant

class EdgeProtocolTest {
    private val prefix = "Microsoft Server Speech Text to Speech Voice"

    // ---- parâmetros ----

    @Test fun vozCurtaViraNomeLongo() =
        assertEquals("$prefix (pt-BR, FranciscaNeural)", EdgeProtocol.normalizeVoice("pt-BR-FranciscaNeural"))

    @Test fun vozComRegiaoComposta() =
        assertEquals("$prefix (zh-CN-liaoning, XiaobeiNeural)", EdgeProtocol.normalizeVoice("zh-CN-liaoning-XiaobeiNeural"))

    @Test fun nomeLongoPassaIgual() {
        val long = "$prefix (en-US, AriaNeural)"
        assertEquals(long, EdgeProtocol.normalizeVoice(long))
    }

    @Test fun vozInvalidaFalha() {
        try {
            EdgeProtocol.normalizeVoice("qualquer coisa")
            fail()
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message!!.contains("Voz inválida"))
        }
    }

    @Test fun velocidade() {
        assertEquals("+0%", EdgeProtocol.rateString(0))
        assertEquals("+50%", EdgeProtocol.rateString(50))
        assertEquals("-25%", EdgeProtocol.rateString(-25))
    }

    // ---- texto ----

    @Test fun caracteresDeControleViramEspaco() =
        assertEquals("a b c d", EdgeProtocol.removeIncompatibleCharacters("a\u000Bb\u0001c\u001Fd"))

    @Test fun quebraDeLinhaETabContinuam() =
        assertEquals("a\nb\tc", EdgeProtocol.removeIncompatibleCharacters("a\nb\tc"))

    @Test fun escapeEUnescape() {
        assertEquals("a &amp; b &lt;c&gt;", EdgeProtocol.escapeXml("a & b <c>"))
        assertEquals("a & b <c>", EdgeProtocol.unescapeXml("a &amp; b &lt;c&gt;"))
        assertEquals("&lt;", EdgeProtocol.unescapeXml("&amp;lt;")) // só uma camada
    }

    @Test fun textoCurtoNaoDivide() =
        assertEquals(listOf("olá mundo"), EdgeProtocol.splitByByteLength("  olá mundo ", 4096))

    @Test fun divideNoUltimoEspacoDentroDoLimite() =
        assertEquals(listOf("aaaa bbbb", "cccc"), EdgeProtocol.splitByByteLength("aaaa bbbb cccc", 10))

    @Test fun preferenciaPorQuebraDeLinha() =
        assertEquals(listOf("aa bb", "cc dd ee"), EdgeProtocol.splitByByteLength("aa bb\ncc dd ee", 9))

    @Test fun naoCortaCaractereMultibyte() =
        assertEquals(listOf("éé", "éé", "é"), EdgeProtocol.splitByByteLength("ééééé", 5))

    @Test fun naoCortaEntidadeXml() =
        assertEquals(listOf("ab", "&amp;", "cd", "efg"), EdgeProtocol.splitByByteLength("ab&amp;cd efg", 5))

    @Test fun nenhumaParteExcedeOLimite() {
        val text = (1..400).joinToString(" ") { "palavra$it ação &amp;" }
        for (part in EdgeProtocol.splitByByteLength(text, 100)) {
            assertTrue(part.toByteArray(Charsets.UTF_8).size <= 100)
        }
    }

    // ---- mensagens enviadas ----

    @Test fun dataNoEstiloJavaScript() =
        assertEquals(
            "Thu Nov 19 2026 12:55:01 GMT+0000 (Coordinated Universal Time)",
            EdgeProtocol.dateToString(Instant.parse("2026-11-19T12:55:01Z")),
        )

    @Test fun mensagemDeConfiguracao() =
        assertEquals(
            "X-Timestamp:D\r\nContent-Type:application/json; charset=utf-8\r\nPath:speech.config\r\n\r\n" +
                "{\"context\":{\"synthesis\":{\"audio\":{\"metadataoptions\":{\"sentenceBoundaryEnabled\":\"false\"," +
                "\"wordBoundaryEnabled\":\"true\"},\"outputFormat\":\"audio-24khz-48kbitrate-mono-mp3\"}}}}\r\n",
            EdgeProtocol.configMessage("D"),
        )

    @Test fun mensagemSsml() {
        val ssml = EdgeProtocol.mkSsml("V (a, b)", "+0%", "+0%", "+0Hz", "oi")
        assertEquals(
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>" +
                "<voice name='V (a, b)'><prosody pitch='+0Hz' rate='+0%' volume='+0%'>oi</prosody></voice></speak>",
            ssml,
        )
        assertEquals(
            "X-RequestId:ID\r\nContent-Type:application/ssml+xml\r\nX-Timestamp:DATEZ\r\nPath:ssml\r\n\r\n$ssml",
            EdgeProtocol.ssmlMessage("ID", "DATE", ssml),
        )
    }

    @Test fun idsTemOFormatoCerto() {
        assertEquals(32, EdgeProtocol.connectId().length)
        assertTrue(EdgeProtocol.connectId().none { it == '-' })
        assertTrue(Regex("[0-9A-F]{32}").matches(EdgeProtocol.muid()))
    }

    // ---- mensagens recebidas ----

    @Test fun mensagemDeTexto() {
        val m = EdgeProtocol.parseTextMessage("X-Timestamp:t\r\nPath:turn.end\r\n\r\n{}")
        assertEquals("turn.end", m.path)
        assertEquals("{}", m.body)
    }

    @Test fun mensagemDeTextoSemSeparadorFalha() {
        try {
            EdgeProtocol.parseTextMessage("sem separador")
            fail()
        } catch (e: UnexpectedResponse) {
        }
    }

    private fun binary(header: String, body: ByteArray): ByteArray {
        val h = header.toByteArray(Charsets.UTF_8)
        return byteArrayOf((h.size shr 8).toByte(), (h.size and 0xFF).toByte()) + h + body
    }

    @Test fun mensagemBinariaDeAudio() {
        val body = byteArrayOf(1, 2, 3, 4)
        val m = EdgeProtocol.parseBinaryMessage(
            binary("X-RequestId:a\r\nContent-Type:audio/mpeg\r\nPath:audio\r\n", body),
        )
        assertEquals("audio", m.path)
        assertEquals("audio/mpeg", m.contentType)
        assertArrayEquals(body, m.body)
    }

    @Test fun mensagemBinariaSemTipoNemDados() {
        val m = EdgeProtocol.parseBinaryMessage(binary("X-RequestId:a\r\nPath:audio\r\n", ByteArray(0)))
        assertNull(m.contentType)
        assertEquals(0, m.body.size)
    }

    @Test fun binarioCurtoOuComCabecalhoGrandeFalha() {
        for (bad in listOf(byteArrayOf(1), byteArrayOf(0, 50, 65))) {
            try {
                EdgeProtocol.parseBinaryMessage(bad)
                fail()
            } catch (e: UnexpectedResponse) {
            }
        }
    }

    private val metadata = """{"Metadata":[{"Type":"WordBoundary","Data":{"Offset":2500000,"Duration":3000000,
        "text":{"Text":"Tom &amp; Jerry","Length":11,"BoundaryType":"WordBoundary"}}}]}"""

    @Test fun fronteiraDePalavraComCompensacao() {
        val b = EdgeProtocol.parseBoundaries(metadata, 10_000_000L).single()
        assertEquals("WordBoundary", b.type)
        assertEquals(12_500_000L, b.offsetTicks)
        assertEquals(3_000_000L, b.durationTicks)
        assertEquals("Tom & Jerry", b.text)
    }

    @Test fun metadadoDeOutroTipoEhIgnorado() {
        assertTrue(EdgeProtocol.parseBoundaries("""{"Metadata":[{"Type":"SessionEnd"}]}""", 0).isEmpty())
    }

    @Test fun metadadoQuebradoFalha() {
        for (bad in listOf("nao e json", "{}", """{"Metadata":[{"Type":"WordBoundary","Data":{}}]}""")) {
            try {
                EdgeProtocol.parseBoundaries(bad, 0)
                fail(bad)
            } catch (e: UnexpectedResponse) {
            }
        }
    }

    @Test fun compensacaoPelosBytesDeMp3() {
        // 48 kbps = 6000 bytes por segundo.
        assertEquals(0L, EdgeProtocol.compensationTicks(0))
        assertEquals(10_000_000L, EdgeProtocol.compensationTicks(6_000))
        assertEquals(80_000_000L, EdgeProtocol.compensationTicks(48_000))
    }
}
