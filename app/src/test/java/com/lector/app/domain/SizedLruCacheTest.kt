package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class SizedLruCacheTest {
    private fun cache() = SizedLruCache<String, Int>(10L) { it.toLong() }

    @Test fun guardaEBusca() {
        val c = cache(); c.put("a", 4)
        assertEquals(4, c.get("a")); assertEquals(4L, c.currentSize)
    }

    @Test fun removeOMenosRecenteQuandoEstoura() {
        val c = cache(); c.put("a", 4); c.put("b", 4); c.put("c", 4)
        assertNull(c.get("a")); assertNotNull(c.get("b")); assertNotNull(c.get("c"))
        assertEquals(8L, c.currentSize)
    }

    @Test fun acessoRenovaARecencia() {
        val c = cache(); c.put("a", 4); c.put("b", 4)
        c.get("a")
        c.put("c", 4)
        assertNotNull(c.get("a")); assertNull(c.get("b"))
    }

    @Test fun itemMaiorQueOTetoNaoEntra() {
        val c = cache(); c.put("a", 4); c.put("x", 11)
        assertNull(c.get("x")); assertEquals(4L, c.currentSize)
    }

    @Test fun substituirMesmaChaveAtualizaOTamanho() {
        val c = cache(); c.put("a", 4); c.put("a", 7)
        assertEquals(7, c.get("a")); assertEquals(7L, c.currentSize); assertEquals(1, c.count)
    }

    @Test fun clearZera() {
        val c = cache(); c.put("a", 4); c.clear()
        assertEquals(0L, c.currentSize); assertEquals(0, c.count)
    }
}
