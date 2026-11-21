package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PageNavigatorTest {
    @Test fun clampLimitaAosExtremos() {
        assertEquals(0, PageNavigator.clamp(-5, 300))
        assertEquals(299, PageNavigator.clamp(999, 300))
        assertEquals(10, PageNavigator.clamp(10, 300))
    }
    @Test fun clampComTotalZero() = assertEquals(0, PageNavigator.clamp(5, 0))
    @Test fun nextNaoPassaDoFim() = assertEquals(299, PageNavigator.next(299, 300))
    @Test fun prevNaoPassaDoInicio() = assertEquals(0, PageNavigator.prev(0, 300))
    @Test fun nextEPrevAndamUm() {
        assertEquals(6, PageNavigator.next(5, 300))
        assertEquals(4, PageNavigator.prev(5, 300))
    }
    @Test fun parseConverteParaBase0() = assertEquals(11, PageNavigator.parseUserPage("12", 300))
    @Test fun parseAceitaEspacos() = assertEquals(4, PageNavigator.parseUserPage(" 5 ", 300))
    @Test fun parseLimites() {
        assertEquals(0, PageNavigator.parseUserPage("1", 300))
        assertEquals(299, PageNavigator.parseUserPage("300", 300))
        assertNull(PageNavigator.parseUserPage("0", 300))
        assertNull(PageNavigator.parseUserPage("301", 300))
    }
    @Test fun parseInvalido() {
        assertNull(PageNavigator.parseUserPage("", 300))
        assertNull(PageNavigator.parseUserPage("abc", 300))
        assertNull(PageNavigator.parseUserPage("3", 0))
    }
}
