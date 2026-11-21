package com.lector.app.tts

import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

/**
 * Relógio usado no token Sec-MS-GEC, com correção de atraso/adiantamento (DRM.clock_skew_seconds no Python).
 * Se o relógio do celular estiver errado, o serviço responde 403 com o horário certo no cabeçalho Date.
 */
class DrmClock(private val wallClockSeconds: () -> Double = { System.currentTimeMillis() / 1000.0 }) {
    @Volatile
    var skewSeconds: Double = 0.0
        private set

    fun now(): Double = wallClockSeconds() + skewSeconds

    /** Ajusta a correção para que now() passe a coincidir com a data do servidor (RFC 1123). */
    fun adjustFromServerDate(date: String?) {
        if (date == null) throw SkewAdjustmentError("A resposta do servidor não trouxe a data.")
        val server = try {
            ZonedDateTime.parse(date, DateTimeFormatter.RFC_1123_DATE_TIME).toEpochSecond().toDouble()
        } catch (e: DateTimeParseException) {
            throw SkewAdjustmentError("Data do servidor ilegível: $date")
        }
        skewSeconds += server - now()
    }

    companion object {
        /** Compartilhado pelo app inteiro, como o atributo de classe do Python. */
        val shared = DrmClock()
    }
}
