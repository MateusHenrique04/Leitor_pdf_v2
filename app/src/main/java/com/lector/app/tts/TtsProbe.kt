package com.lector.app.tts

import java.io.File
import java.time.Instant
import java.util.Locale

/**
 * TEMPORÁRIO (Fase 4): sintetiza UM trecho, grava o MP3 num arquivo e devolve um relatório para conferir
 * o EdgeTtsClient no celular (tempo, tamanho, palavras e tempos). Sai quando o player da Fase 6 existir.
 */
object TtsProbe {
    /** Troque por uma voz do idioma do livro (ex.: "en-US-AriaNeural" para livros em inglês). */
    const val VOICE = "pt-BR-FranciscaNeural"

    /** Relatório de diagnóstico quando o servidor recusa a conexão. */
    fun describeHttpError(e: EdgeHttpException): String = buildString {
        append("HTTP ${e.statusCode} ao conectar (${e.message})\n\n")
        append("Data do servidor: ${e.serverDate ?: "(não veio)"}\n")
        append("Hora do celular (UTC): ${Instant.now()}\n")
        append("Correção de relógio aplicada: %.1f s\n".format(Locale.US, DrmClock.shared.skewSeconds))
        append("\nResposta do servidor:\n")
        append(if (e.details.isBlank()) "  (vazia)\n" else e.details)
        append("\nMande este texto inteiro (tire um print se preferir).")
    }

    suspend fun run(client: EdgeTtsClient, text: String, audioFile: File): String {
        val t0 = System.nanoTime()
        val r = client.synthesize(text, VOICE, 0)
        val ms = (System.nanoTime() - t0) / 1_000_000
        audioFile.parentFile?.mkdirs()
        audioFile.writeBytes(r.audioBytes)

        val loc = Locale.US
        val mp3Seconds = r.audioBytes.size * 8.0 / 48_000.0
        val sb = StringBuilder()
        sb.append("Voz: $VOICE | velocidade +0%\n")
        sb.append("Texto (${text.length} car.):\n\"${if (text.length > 160) text.take(160) + "..." else text}\"\n\n")
        sb.append("Síntese: %d ms | MP3 %.1f KB | %d palavras\n".format(loc, ms, r.audioBytes.size / 1024.0, r.timings.size))
        sb.append("Duração do MP3 (48 kbps): %.2f s\n".format(loc, mp3Seconds))
        val end = r.speechEndSeconds
        if (end != null) {
            sb.append("Fim da fala (última palavra + 0,10 s): %.2f s\n".format(loc, end))
            sb.append("Silêncio cortável no fim: %.2f s\n".format(loc, mp3Seconds - end))
        }
        sb.append("\nPrimeiras palavras (início-fim em s):\n")
        for (w in r.timings.take(6)) sb.append("  %.2f-%.2f  %s\n".format(loc, w.startSeconds, w.endSeconds, w.word))
        if (r.timings.size > 6) {
            sb.append("Últimas:\n")
            for (w in r.timings.takeLast(3)) sb.append("  %.2f-%.2f  %s\n".format(loc, w.startSeconds, w.endSeconds, w.word))
        }
        sb.append("\nToque em \"Ouvir\" para tocar o MP3 e conferir se a voz bate com as palavras.")
        return sb.toString()
    }
}
