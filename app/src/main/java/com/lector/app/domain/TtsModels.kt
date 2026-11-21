package com.lector.app.domain

/** Uma palavra falada: tempos em segundos desde o início do MP3 (velocidade +0%). */
data class WordTiming(val word: String, val startSeconds: Float, val endSeconds: Float)

/** Resultado de sintetizar um texto: MP3 (24 kHz, 48 kbps, mono) e os tempos de cada palavra. */
data class TTSResult(val audioBytes: ByteArray, val timings: List<WordTiming>) {
    /**
     * Instante em que a fala realmente termina. Todo MP3 do serviço traz ~0,9 s de silêncio no fim;
     * o desktop corta em "última palavra + 0,10 s" (SPEECH_TAIL_MARGIN). Null se não houver palavras.
     */
    val speechEndSeconds: Float?
        get() = timings.lastOrNull()?.let { it.endSeconds + SPEECH_TAIL_MARGIN_SECONDS }

    /** [speechEndSeconds] em milissegundos (fim do corte do MediaItem). */
    val speechEndMs: Long?
        get() = speechEndSeconds?.let { Math.round(it * 1000f).toLong() }

    companion object {
        const val SPEECH_TAIL_MARGIN_SECONDS = 0.10f
    }
}
