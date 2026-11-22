package com.lector.app.domain

/** Um trecho já baixado, pronto para tocar sem internet. */
data class CachedAudio(val path: String, val endMs: Long?, val timings: List<WordTiming>)

object CachePolicy {
    /**
     * Decide se um trecho do cache serve para tocar: precisa estar pronto, com o arquivo ainda no disco e com os
     * tempos das palavras legíveis. Qualquer falha devolve null e o motor sintetiza on-line como se não houvesse cache.
     */
    fun resolve(
        isDone: Boolean,
        filePath: String?,
        endMs: Long?,
        timings: String?,
        fileExists: (String) -> Boolean,
    ): CachedAudio? {
        if (!isDone || filePath.isNullOrBlank() || timings == null) return null
        if (!fileExists(filePath)) return null
        val decoded = TimingsCodec.decode(timings) ?: return null
        return CachedAudio(filePath, endMs, decoded)
    }
}
