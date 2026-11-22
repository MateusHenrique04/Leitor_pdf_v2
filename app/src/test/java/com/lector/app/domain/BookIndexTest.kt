package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BookIndexTest {
    // pág 0: 2 trechos | pág 1: nenhum começa (vazia) | pág 2: 1 trecho | pág 3: 2 trechos
    private val c = listOf(
        Chunk(0, 0, 0, 0, "a"), Chunk(1, 0, 2, 1, "b"),
        Chunk(2, 2, 2, 0, "c"),
        Chunk(3, 3, 3, 0, "d"), Chunk(4, 3, 3, 1, "e"),
    )
    private val index = BookIndex(1, 4, c)

    @Test fun trechosQueComecamNaPagina() {
        assertEquals(listOf(c[0], c[1]), index.chunksStartingOn(0))
        assertTrue(index.chunksStartingOn(1).isEmpty())
        assertTrue(index.chunksStartingOn(99).isEmpty())
    }

    @Test fun findUsaIndiceNaPagina() {
        assertEquals(c[1], index.find(0, 1))
        assertEquals(c[4], index.find(3, 1))
        assertNull(index.find(3, 2))
        assertNull(index.find(1, 0))
    }

    @Test fun firstFromPulaPaginasSemTexto() {
        assertEquals(c[2], index.firstFrom(1))
        assertEquals(c[0], index.firstFrom(0))
        assertNull(index.firstFrom(4))
    }

    @Test fun resumePointUsaOSalvoOuOPrimeiroDaPagina() {
        assertEquals(c[1], index.resumePoint(0, 1))
        assertEquals(c[3], index.resumePoint(3, 0))
        assertEquals(c[3], index.resumePoint(3, 9)) // índice salvo não existe mais
        assertEquals(c[2], index.resumePoint(1, 0)) // página sem texto
        assertNull(index.resumePoint(4, 0))
    }

    @Test fun proximoEAnterior() {
        assertEquals(c[1], index.next(c[0]))
        assertNull(index.next(c[4]))
        assertEquals(c[2], index.previous(c[3]))
        assertNull(index.previous(c[0]))
    }

    @Test fun intervaloDeTrechosPorPaginas() {
        assertEquals(0..1, index.chunkRange(0, 0))
        assertEquals(2..2, index.chunkRange(1, 2)) // pág. 1 não tem trechos que comecem nela
        assertEquals(0..4, index.chunkRange(0, 3))
        assertEquals(2..4, index.chunkRange(2, 3))
        assertNull(index.chunkRange(1, 1))
        assertNull(index.chunkRange(3, 1)) // intervalo invertido
        assertNull(index.chunkRange(10, 20))
    }

    @Test fun vazio() {
        assertTrue(BookIndex(1, 3, emptyList()).isEmpty)
        assertTrue(!index.isEmpty)
    }
}
