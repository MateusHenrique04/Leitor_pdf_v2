package com.lector.app.domain

data class DownloadEstimate(val chunks: Int, val audioSeconds: Long, val bytes: Long)

/**
 * Estimativas ANTES de baixar (o tamanho real só se sabe depois). Os números são palpites a conferir com um
 * download real: ritmo da fala e o overhead de silêncio de cada MP3 (~0,25 s no início e ~0,9 s no fim).
 */
object DownloadEstimator {
    const val CHARS_PER_SECOND = 14.5f
    const val OVERHEAD_SECONDS_PER_CHUNK = 1.2f
    /** audio-24khz-48kbitrate-mono-mp3 = 48 kbps = 6000 bytes por segundo. */
    const val BYTES_PER_SECOND = 6000L
    const val SAFETY_FACTOR = 1.15
    /** Espaço livre que sempre sobra no aparelho, além do necessário. */
    const val RESERVE_BYTES = 100L * 1024 * 1024

    fun estimate(chunkLengths: List<Int>): DownloadEstimate {
        var seconds = 0f
        for (len in chunkLengths) seconds += len / CHARS_PER_SECOND + OVERHEAD_SECONDS_PER_CHUNK
        val secs = seconds.toLong()
        return DownloadEstimate(chunkLengths.size, secs, Math.round(seconds * BYTES_PER_SECOND.toFloat()).toLong())
    }

    fun enoughSpace(neededBytes: Long, availableBytes: Long): Boolean =
        availableBytes >= (neededBytes * SAFETY_FACTOR).toLong() + RESERVE_BYTES
}
