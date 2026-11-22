package com.lector.app.download

import com.lector.app.domain.TTSResult
import com.lector.app.tts.EdgeTtsClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Sintetiza sempre a +0%: a velocidade é do player, então um download por voz serve para todas as velocidades. */
class EdgeSynthesizer(private val client: EdgeTtsClient = EdgeTtsClient()) : Synthesizer {
    override suspend fun synthesize(text: String, voice: String): TTSResult =
        withContext(Dispatchers.IO) { client.synthesize(text, voice, 0) }
}
