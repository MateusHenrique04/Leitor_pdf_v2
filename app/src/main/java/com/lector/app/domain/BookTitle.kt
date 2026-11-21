package com.lector.app.domain

/** Lógica pura (sem Android): deriva o título exibido a partir do nome do arquivo. */
object BookTitle {
    const val UNTITLED = "Sem título"

    fun fromFileName(fileName: String?): String {
        if (fileName.isNullOrBlank()) return UNTITLED
        val semExtensao = fileName.trim().replace(Regex("(?i)\\.pdf$"), "")
        val limpo = semExtensao.replace('_', ' ').replace(Regex("\\s+"), " ").trim()
        return limpo.ifBlank { UNTITLED }
    }
}
