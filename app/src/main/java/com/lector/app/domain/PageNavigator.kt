package com.lector.app.domain

/** Navegação entre páginas. Índices base 0 internamente; o usuário digita base 1. */
object PageNavigator {
    fun clamp(page: Int, total: Int): Int =
        if (total <= 0) 0 else page.coerceIn(0, total - 1)

    fun next(page: Int, total: Int): Int = clamp(page + 1, total)
    fun prev(page: Int, total: Int): Int = clamp(page - 1, total)

    /** "12" -> índice 11. Devolve null se vazio, não numérico ou fora de 1..total. */
    fun parseUserPage(input: String, total: Int): Int? {
        val n = input.trim().toIntOrNull() ?: return null
        return if (n in 1..total) n - 1 else null
    }
}
