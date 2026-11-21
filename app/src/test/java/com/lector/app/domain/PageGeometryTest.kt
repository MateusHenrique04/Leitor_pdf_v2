package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PageGeometryTest {
    @Test fun semRotacaoMantemTamanho() =
        assertEquals(PageSize(595f, 842f), PageGeometry.rotatedSize(595f, 842f, 0))

    @Test fun rotacao90e270TrocamLarguraEAltura() {
        assertEquals(PageSize(842f, 595f), PageGeometry.rotatedSize(595f, 842f, 90))
        assertEquals(PageSize(842f, 595f), PageGeometry.rotatedSize(595f, 842f, 270))
        assertEquals(PageSize(842f, 595f), PageGeometry.rotatedSize(595f, 842f, -90))
        assertEquals(PageSize(842f, 595f), PageGeometry.rotatedSize(595f, 842f, 450))
    }

    @Test fun rotacao180MantemTamanho() =
        assertEquals(PageSize(595f, 842f), PageGeometry.rotatedSize(595f, 842f, 180))

    @Test fun toleraArredondamentoDoPdfRenderer() {
        assertTrue(PageGeometry.matches(PageSize(595.276f, 841.89f), PageSize(595f, 842f)))
        assertNull(PageGeometry.mismatch(PageSize(595.276f, 841.89f), PageSize(595f, 842f)))
    }

    @Test fun detectaTamanhoDiferente() {
        assertFalse(PageGeometry.matches(PageSize(612f, 792f), PageSize(595f, 842f)))
        assertNotNull(PageGeometry.mismatch(PageSize(612f, 792f), PageSize(595f, 842f)))
    }
}
