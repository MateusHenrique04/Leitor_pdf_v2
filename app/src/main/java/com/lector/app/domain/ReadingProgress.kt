package com.lector.app.domain

/**
 * Lógica pura de progresso. [lastPage] é índice base 0, como no desktop
 * (`last_page` do library.json começa em 0).
 */
object ReadingProgress {
    fun percent(lastPage: Int, totalPages: Int, finished: Boolean): Int {
        if (finished) return 100
        if (totalPages <= 0) return 0
        return (lastPage.coerceIn(0, totalPages) * 100) / totalPages
    }

    /** Texto para humanos: página base 1. */
    fun label(lastPage: Int, totalPages: Int, finished: Boolean): String {
        if (finished) return "Concluído"
        val pagina = if (totalPages > 0) (lastPage + 1).coerceIn(1, totalPages) else lastPage + 1
        return "Página $pagina de $totalPages · ${percent(lastPage, totalPages, false)}%"
    }
}
