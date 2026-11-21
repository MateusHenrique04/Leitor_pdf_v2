package com.lector.app.tts

import com.lector.app.domain.TTSResult
import com.lector.app.domain.WordTiming
import kotlinx.coroutines.withTimeoutOrNull
import java.io.ByteArrayOutputStream
import java.time.Instant

/**
 * Cliente do Edge-TTS (porte de communicate.py, edge-tts 7.2.8): sintetiza um texto e devolve o MP3 e os
 * tempos de cada palavra. Sempre pede fronteiras de PALAVRA (o padrão da lib nova é de frase).
 *
 * Diferença deliberada do original: se a conexão cair antes de "turn.end", falha (WebSocketError) em vez de
 * devolver áudio cortado, porque na Fase 8 o resultado vai para o cache.
 */
class EdgeTtsClient(
    private val transport: EdgeTransport = OkHttpEdgeTransport(),
    private val clock: DrmClock = DrmClock.shared,
    private val receiveTimeoutMs: Long = EdgeConstants.RECEIVE_TIMEOUT_MS,
    private val maxTextBytes: Int = EdgeConstants.MAX_TEXT_BYTES,
    private val now: () -> Instant = { Instant.now() },
) {
    private class State {
        val audio = ByteArrayOutputStream()
        val timings = ArrayList<WordTiming>()
        var cumulativeAudioBytes = 0L
        var compensationTicks = 0L
        var chunkAudioBytes = 0L
    }

    /**
     * @param voice "pt-BR-FranciscaNeural" ou o nome longo da Microsoft.
     * @param speedPct velocidade em % (+0 para o cache offline; varia-se no player).
     * @throws EdgeTtsException em falhas do serviço/rede; IllegalArgumentException em voz inválida.
     */
    suspend fun synthesize(text: String, voice: String, speedPct: Int = 0): TTSResult {
        val voiceName = EdgeProtocol.normalizeVoice(voice)
        val rate = EdgeProtocol.rateString(speedPct)
        val parts = EdgeProtocol.splitByByteLength(
            EdgeProtocol.escapeXml(EdgeProtocol.removeIncompatibleCharacters(text)),
            maxTextBytes,
        )
        if (parts.isEmpty()) throw NoAudioReceived("O texto está vazio.")

        val state = State()
        for (part in parts) streamPart(part, voiceName, rate, state)
        return TTSResult(state.audio.toByteArray(), state.timings)
    }

    /** Uma parte = uma conexão. Com 403 (relógio fora de hora), corrige o relógio e tenta mais uma vez. */
    private suspend fun streamPart(part: String, voiceName: String, rate: String, st: State) {
        for (attempt in 0..1) {
            try {
                runPart(part, voiceName, rate, st)
                return
            } catch (e: EdgeHttpException) {
                if (e.statusCode != 403 || attempt == 1) throw e
                clock.adjustFromServerDate(e.serverDate)
            }
        }
    }

    private suspend fun runPart(part: String, voiceName: String, rate: String, st: State) {
        st.chunkAudioBytes = 0
        val socket = transport.connect(buildUrl(), buildHeaders())
        try {
            socket.send(EdgeProtocol.configMessage(EdgeProtocol.dateToString(now())))
            socket.send(
                EdgeProtocol.ssmlMessage(
                    EdgeProtocol.connectId(),
                    EdgeProtocol.dateToString(now()),
                    EdgeProtocol.mkSsml(voiceName, rate, "+0%", "+0Hz", part),
                ),
            )

            var audioReceived = false
            while (true) {
                val result = withTimeoutOrNull(receiveTimeoutMs) { socket.frames.receiveCatching() }
                    ?: throw WebSocketError("O servidor não respondeu em ${receiveTimeoutMs / 1000} s.")
                val frame = result.getOrNull()
                    ?: throw WebSocketError("A conexão foi encerrada antes do fim da síntese.")

                when (frame) {
                    is EdgeFrame.Text -> {
                        val msg = EdgeProtocol.parseTextMessage(frame.data)
                        when (msg.path) {
                            "audio.metadata" -> {
                                for (b in EdgeProtocol.parseBoundaries(msg.body, st.compensationTicks)) {
                                    st.timings.add(toTiming(b))
                                }
                            }
                            "turn.end" -> {
                                if (!audioReceived) {
                                    throw NoAudioReceived("Nenhum áudio recebido. Confira a voz e os parâmetros.")
                                }
                                st.cumulativeAudioBytes += st.chunkAudioBytes
                                st.compensationTicks = EdgeProtocol.compensationTicks(st.cumulativeAudioBytes)
                                return
                            }
                            "response", "turn.start" -> Unit
                            else -> throw UnknownResponse("Caminho desconhecido: ${msg.path}")
                        }
                    }
                    is EdgeFrame.Binary -> {
                        val msg = EdgeProtocol.parseBinaryMessage(frame.data)
                        if (msg.path != "audio") throw UnexpectedResponse("Mensagem binária que não é áudio.")
                        if (msg.contentType != null && msg.contentType != "audio/mpeg") {
                            throw UnexpectedResponse("Tipo de conteúdo inesperado: ${msg.contentType}")
                        }
                        if (msg.contentType == null) {
                            // Mensagem final do serviço: sem tipo e sem dados. Com dados, é erro.
                            if (msg.body.isEmpty()) continue
                            throw UnexpectedResponse("Mensagem sem tipo de conteúdo, mas com dados.")
                        }
                        if (msg.body.isEmpty()) throw UnexpectedResponse("Mensagem de áudio vazia.")
                        audioReceived = true
                        st.chunkAudioBytes += msg.body.size
                        st.audio.write(msg.body)
                    }
                    is EdgeFrame.Failure ->
                        throw WebSocketError(frame.error.message ?: "Erro no WebSocket", frame.error)
                }
            }
        } finally {
            socket.close()
        }
    }

    private fun toTiming(b: Boundary): WordTiming {
        val ticks = EdgeConstants.TICKS_PER_SECOND.toDouble()
        return WordTiming(
            word = b.text,
            startSeconds = (b.offsetTicks / ticks).toFloat(),
            endSeconds = ((b.offsetTicks + b.durationTicks) / ticks).toFloat(),
        )
    }

    private fun buildUrl(): String =
        "${EdgeConstants.WSS_URL}&ConnectionId=${EdgeProtocol.connectId()}" +
            "&Sec-MS-GEC=${EdgeDrm.generateSecMsGec(clock.now(), EdgeConstants.TRUSTED_CLIENT_TOKEN)}" +
            "&Sec-MS-GEC-Version=${EdgeConstants.SEC_MS_GEC_VERSION}"

    private fun buildHeaders(): Map<String, String> =
        EdgeConstants.WSS_HEADERS + ("Cookie" to "muid=${EdgeProtocol.muid()};")
}
