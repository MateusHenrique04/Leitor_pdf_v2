package com.lector.app.domain

/** Relógio da fala: dado o tempo de reprodução, qual palavra está sendo dita. */
object WordClock {
    /**
     * Índice da última palavra cujo início já passou (start <= posição). -1 se a posição é anterior à primeira
     * palavra ou se não há palavras. A posição é o tempo de MÍDIA do trecho (não depende da velocidade).
     */
    fun wordIndexAt(timings: List<WordTiming>, positionSeconds: Float): Int {
        var lo = 0
        var hi = timings.size - 1
        var answer = -1
        while (lo <= hi) {
            val mid = (lo + hi) ushr 1
            if (timings[mid].startSeconds <= positionSeconds) {
                answer = mid
                lo = mid + 1
            } else {
                hi = mid - 1
            }
        }
        return answer
    }
}
