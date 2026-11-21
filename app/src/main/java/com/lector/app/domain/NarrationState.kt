package com.lector.app.domain

enum class NarrationStatus { IDLE, LOADING, PLAYING, PAUSED, ENDED, ERROR }

/**
 * O que a tela precisa saber da narração. [wordIndex] é o índice em [timings] da palavra que está sendo falada
 * agora (-1 antes da primeira). A Fase 7 usa isso (com [WordSyncEngine]) para grifar a palavra na página.
 */
data class NarrationState(
    val bookId: String? = null,
    val status: NarrationStatus = NarrationStatus.IDLE,
    val chunk: Chunk? = null,
    val timings: List<WordTiming> = emptyList(),
    val wordIndex: Int = -1,
    val speed: Float = 1f,
    val error: String? = null,
)
