package com.lector.app.domain

object PageRangeParser {
    /**
     * Intervalo de páginas (base 0, inclusive) a partir do que o usuário digitou (base 1). [wholeBook] ignora os
     * textos. Campo em branco = começo / fim do livro. null se for inválido (fora do livro, invertido, não numérico).
     */
    fun parse(wholeBook: Boolean, fromText: String, toText: String, totalPages: Int): IntRange? {
        if (totalPages <= 0) return null
        if (wholeBook) return 0..totalPages - 1
        val from = if (fromText.isBlank()) 1 else fromText.trim().toIntOrNull() ?: return null
        val to = if (toText.isBlank()) totalPages else toText.trim().toIntOrNull() ?: return null
        if (from < 1 || to > totalPages || from > to) return null
        return (from - 1)..(to - 1)
    }
}
