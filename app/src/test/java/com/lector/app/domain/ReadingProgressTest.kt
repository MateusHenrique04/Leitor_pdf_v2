package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Test

class ReadingProgressTest {
    @Test fun inicioEhZero() = assertEquals(0, ReadingProgress.percent(0, 300, false))
    @Test fun meioDoLivro() = assertEquals(50, ReadingProgress.percent(150, 300, false))
    @Test fun ultimaPaginaNaoEh100SemConcluir() = assertEquals(99, ReadingProgress.percent(299, 300, false))
    @Test fun concluidoEh100() = assertEquals(100, ReadingProgress.percent(10, 300, true))
    @Test fun totalZeroNaoDivide() = assertEquals(0, ReadingProgress.percent(5, 0, false))
    @Test fun paginaForaDoLimiteEhCortada() = assertEquals(100, ReadingProgress.percent(999, 300, false))
    @Test fun rotuloUsaPaginaBase1() = assertEquals("Página 1 de 300 · 0%", ReadingProgress.label(0, 300, false))
    @Test fun rotuloConcluido() = assertEquals("Concluído", ReadingProgress.label(299, 300, true))
}
