package com.lector.app.tts

import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.security.SecureRandom
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID

/** Uma fronteira de palavra do serviço. Tempos em ticks de 100 ns, já com a compensação entre trechos. */
data class Boundary(val type: String, val offsetTicks: Long, val durationTicks: Long, val text: String)

data class TextMessage(val path: String?, val body: String)

data class BinaryMessage(val path: String?, val contentType: String?, val body: ByteArray)

/**
 * Parte "pura" do protocolo do Edge-TTS (porte de edge_tts/communicate.py e data_classes.py, versão 7.2.8):
 * monta e lê mensagens, divide o texto e valida os parâmetros. Sem rede e sem Android, para testar com JUnit.
 */
object EdgeProtocol {
    // ---------- parâmetros (data_classes.py) ----------

    private val VOICE_SHORT = Regex("^([a-z]{2,})-([A-Z]{2,})-(.+Neural)$")
    private val VOICE_FULL = Regex("""^Microsoft Server Speech Text to Speech Voice \(.+,.+\)$""")

    /** "pt-BR-FranciscaNeural" -> "Microsoft Server Speech Text to Speech Voice (pt-BR, FranciscaNeural)". */
    fun normalizeVoice(voice: String): String {
        var v = voice
        val m = VOICE_SHORT.find(v)
        if (m != null) {
            val lang = m.groupValues[1]
            var region = m.groupValues[2]
            var name = m.groupValues[3]
            val dash = name.indexOf('-')
            if (dash != -1) {
                region = "$region-${name.substring(0, dash)}"
                name = name.substring(dash + 1)
            }
            v = "Microsoft Server Speech Text to Speech Voice ($lang-$region, $name)"
        }
        require(VOICE_FULL.matches(v)) { "Voz inválida: '$voice'" }
        return v
    }

    /** Velocidade em % ("+0%", "-25%", "+50%"). */
    fun rateString(speedPct: Int): String = if (speedPct >= 0) "+$speedPct%" else "$speedPct%"

    // ---------- texto ----------

    /** O serviço recusa alguns caracteres de controle (ex.: tab vertical, comum em PDF com OCR): vira espaço. */
    fun removeIncompatibleCharacters(s: String): String {
        val chars = s.toCharArray()
        for (i in chars.indices) {
            val code = chars[i].code
            if (code in 0..8 || code in 11..12 || code in 14..31) chars[i] = ' '
        }
        return String(chars)
    }

    /** Equivale a xml.sax.saxutils.escape: só & < > . */
    fun escapeXml(s: String): String = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    fun unescapeXml(s: String): String = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

    /**
     * Divide em partes de no máximo [byteLength] bytes (UTF-8), preferindo quebrar em "\n" e depois em espaço,
     * sem cortar caractere multibyte nem entidade XML (&amp;). Diferença do original: sem espaço no trecho, o
     * original procura o ponto seguro no texto inteiro (pode passar do limite); aqui, só dentro do limite.
     */
    fun splitByByteLength(text: String, byteLength: Int): List<String> {
        require(byteLength > 0) { "byteLength deve ser positivo" }
        var bytes = text.toByteArray(Charsets.UTF_8)
        val out = ArrayList<String>()
        while (bytes.size > byteLength) {
            var splitAt = lastIndexOfByte(bytes, '\n', byteLength)
            if (splitAt < 0) splitAt = lastIndexOfByte(bytes, ' ', byteLength)
            if (splitAt < 0) splitAt = safeUtf8SplitPoint(bytes, byteLength)
            splitAt = adjustSplitForXmlEntity(bytes, splitAt)
            val chunk = decodeStripped(bytes, 0, splitAt)
            if (chunk.isNotEmpty()) out.add(chunk)
            bytes = bytes.copyOfRange(if (splitAt > 0) splitAt else 1, bytes.size)
        }
        val rest = decodeStripped(bytes, 0, bytes.size)
        if (rest.isNotEmpty()) out.add(rest)
        return out
    }

    private fun lastIndexOfByte(b: ByteArray, value: Char, endExclusive: Int): Int {
        val v = value.code.toByte()
        var i = minOf(endExclusive, b.size) - 1
        while (i >= 0) {
            if (b[i] == v) return i
            i--
        }
        return -1
    }

    private fun indexOfByte(b: ByteArray, value: Char, from: Int, endExclusive: Int): Int {
        val v = value.code.toByte()
        for (i in from until minOf(endExclusive, b.size)) if (b[i] == v) return i
        return -1
    }

    private fun safeUtf8SplitPoint(b: ByteArray, limit: Int): Int {
        var split = minOf(limit, b.size)
        while (split > 0) {
            if (isValidUtf8(b, split)) return split
            split--
        }
        return 0
    }

    private fun isValidUtf8(b: ByteArray, length: Int): Boolean = try {
        Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(b, 0, length))
        true
    } catch (e: CharacterCodingException) {
        false
    }

    private fun adjustSplitForXmlEntity(b: ByteArray, splitAt: Int): Int {
        var s = splitAt
        while (s > 0 && indexOfByte(b, '&', 0, s) != -1) {
            val amp = lastIndexOfByte(b, '&', s)
            if (indexOfByte(b, ';', amp, s) != -1) break
            s = amp
        }
        return s
    }

    private fun isAsciiSpace(x: Byte): Boolean = x.toInt() == 0x20 || x.toInt() in 0x09..0x0D

    private fun decodeStripped(b: ByteArray, from: Int, to: Int): String {
        var s = from
        var e = to
        while (s < e && isAsciiSpace(b[s])) s++
        while (e > s && isAsciiSpace(b[e - 1])) e--
        return String(b, s, e - s, Charsets.UTF_8)
    }

    // ---------- mensagens enviadas ----------

    private val DATE_FORMAT: DateTimeFormatter =
        DateTimeFormatter.ofPattern("EEE MMM dd yyyy HH:mm:ss", Locale.US).withZone(ZoneOffset.UTC)

    /** Data no estilo JavaScript que o serviço espera. */
    fun dateToString(now: Instant): String = DATE_FORMAT.format(now) + " GMT+0000 (Coordinated Universal Time)"

    fun connectId(): String = UUID.randomUUID().toString().replace("-", "")

    private val random = SecureRandom()

    /** Valor do cookie muid: 16 bytes aleatórios em hexadecimal maiúsculo. */
    fun muid(): String {
        val b = ByteArray(16)
        random.nextBytes(b)
        return b.joinToString("") { "%02X".format(it) }
    }

    /** Primeira mensagem: configura fronteiras de PALAVRA e o formato de saída. */
    fun configMessage(date: String): String =
        "X-Timestamp:$date\r\n" +
            "Content-Type:application/json; charset=utf-8\r\n" +
            "Path:speech.config\r\n\r\n" +
            "{\"context\":{\"synthesis\":{\"audio\":{\"metadataoptions\":{" +
            "\"sentenceBoundaryEnabled\":\"false\",\"wordBoundaryEnabled\":\"true\"}," +
            "\"outputFormat\":\"${EdgeConstants.OUTPUT_FORMAT}\"" +
            "}}}}\r\n"

    fun mkSsml(voiceFull: String, rate: String, volume: String, pitch: String, escapedText: String): String =
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>" +
            "<voice name='$voiceFull'>" +
            "<prosody pitch='$pitch' rate='$rate' volume='$volume'>" +
            escapedText +
            "</prosody></voice></speak>"

    /** O "Z" depois do X-Timestamp é intencional (bug do Microsoft Edge que o serviço espera). */
    fun ssmlMessage(requestId: String, date: String, ssml: String): String =
        "X-RequestId:$requestId\r\n" +
            "Content-Type:application/ssml+xml\r\n" +
            "X-Timestamp:${date}Z\r\n" +
            "Path:ssml\r\n\r\n" +
            ssml

    // ---------- mensagens recebidas ----------

    private fun parseHeaders(block: String): Map<String, String> {
        val map = HashMap<String, String>()
        for (line in block.split("\r\n")) {
            val i = line.indexOf(':')
            if (i > 0) map[line.substring(0, i)] = line.substring(i + 1).trim()
        }
        return map
    }

    fun parseTextMessage(raw: String): TextMessage {
        val idx = raw.indexOf("\r\n\r\n")
        if (idx < 0) throw UnexpectedResponse("Mensagem de texto sem separador de cabeçalho.")
        return TextMessage(parseHeaders(raw.substring(0, idx))["Path"], raw.substring(idx + 4))
    }

    /** Binário: 2 bytes (big-endian) com o tamanho do cabeçalho, o cabeçalho em texto e depois o áudio. */
    fun parseBinaryMessage(data: ByteArray): BinaryMessage {
        if (data.size < 2) throw UnexpectedResponse("Mensagem binária sem o tamanho do cabeçalho.")
        val headerLength = ((data[0].toInt() and 0xFF) shl 8) or (data[1].toInt() and 0xFF)
        if (2 + headerLength > data.size) throw UnexpectedResponse("Tamanho do cabeçalho maior que a mensagem.")
        val headers = parseHeaders(String(data, 2, headerLength, Charsets.UTF_8))
        return BinaryMessage(headers["Path"], headers["Content-Type"], data.copyOfRange(2 + headerLength, data.size))
    }

    /** Fronteiras de palavra de uma mensagem "audio.metadata". Outros tipos de metadado são ignorados. */
    fun parseBoundaries(body: String, offsetCompensationTicks: Long): List<Boundary> {
        val root = try {
            MiniJson.parse(body)
        } catch (e: IllegalArgumentException) {
            throw UnexpectedResponse("Metadados ilegíveis: ${e.message}")
        }
        val items = (asMap(root)["Metadata"] as? List<*>) ?: throw UnexpectedResponse("Metadados sem o campo 'Metadata'.")
        val out = ArrayList<Boundary>()
        for (item in items) {
            val obj = asMap(item)
            val type = obj["Type"] as? String ?: continue
            if (type != "WordBoundary" && type != "SentenceBoundary") continue
            val data = asMap(obj["Data"])
            val offset = (data["Offset"] as? Number)?.toLong() ?: throw UnexpectedResponse("Fronteira sem Offset.")
            val duration = (data["Duration"] as? Number)?.toLong() ?: throw UnexpectedResponse("Fronteira sem Duration.")
            val text = asMap(data["text"])["Text"] as? String ?: throw UnexpectedResponse("Fronteira sem texto.")
            out.add(Boundary(type, offset + offsetCompensationTicks, duration, unescapeXml(text)))
        }
        return out
    }

    private fun asMap(x: Any?): Map<*, *> = x as? Map<*, *> ?: throw UnexpectedResponse("Metadado fora do formato.")

    /**
     * Deslocamento (ticks) a somar aos tempos do próximo trecho: calculado pelos bytes de áudio já recebidos.
     * Em MP3 CBR de 48 kbps a conta é exata (substitui os tempos informados pelo servidor, que derivam).
     */
    fun compensationTicks(cumulativeAudioBytes: Long): Long =
        cumulativeAudioBytes * 8 * EdgeConstants.TICKS_PER_SECOND / EdgeConstants.MP3_BITRATE_BPS
}
