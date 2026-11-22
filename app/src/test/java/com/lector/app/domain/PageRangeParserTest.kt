package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PageRangeParserTest {
    private fun p(whole: Boolean, from: String, to: String, total: Int = 78) = PageRangeParser.parse(whole, from, to, total)

    @Test fun livroInteiroIgnoraOsCampos() = assertEquals(0..77, p(true, "lixo", "x"))

    @Test fun paginasDigitadasSaoBase1ViramBase0() = assertEquals(4..9, p(false, "5", "10"))

    @Test fun campoEmBrancoEhComecoOuFim() {
        assertEquals(0..9, p(false, "", "10"))
        assertEquals(4..77, p(false, "5", " "))
        assertEquals(0..77, p(false, "", ""))
    }

    @Test fun aceitaEspacos() = assertEquals(2..2, p(false, " 3 ", " 3 "))

    @Test fun invalidosDevolvemNull() {
        assertNull(p(false, "0", "5"))
        assertNull(p(false, "1", "79"))
        assertNull(p(false, "10", "5"))
        assertNull(p(false, "abc", "5"))
        assertNull(p(false, "1", "x"))
        assertNull(p(false, "-1", "5"))
    }

    @Test fun livroSemPaginas() {
        assertNull(p(true, "", "", total = 0))
        assertNull(p(false, "1", "1", total = 0))
    }
}
