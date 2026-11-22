package com.lector.app.domain

/** Vozes oferecidas no app (as que você usa no desktop). [id] é o nome curto aceito pelo EdgeTtsClient. */
data class VoiceOption(val id: String, val label: String, val language: String)

object Voices {
    const val DEFAULT_ID = "pt-BR-AntonioNeural"

    val ALL = listOf(
        VoiceOption(DEFAULT_ID, "Antonio (português do Brasil)", "pt-BR"),
        VoiceOption("en-US-GuyNeural", "Guy (inglês dos EUA)", "en-US"),
        VoiceOption("es-ES-AlvaroNeural", "Alvaro (espanhol da Espanha)", "es-ES"),
    )

    fun byId(id: String): VoiceOption? = ALL.firstOrNull { it.id == id }
}
