package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RevealPolicyTest {
    // tela 1000 x 2000; página cabendo na largura (contentW = 1000) salvo nos testes de zoom
    private fun d(l: Float, t: Float, r: Float, b: Float, contentW: Float = 1000f) =
        RevealPolicy.delta(l, t, r, b, 1000f, 2000f, contentW)

    @Test fun palavraVisivelSemZoomNaoRola() {
        assertTrue(d(100f, 800f, 200f, 830f).isZero)
    }

    @Test fun palavraAbaixoDaTelaVaiPara30PorCento() {
        val r = d(100f, 2100f, 200f, 2130f)
        assertEquals(600f - 2100f, r.dy, 0.001f) // 30% de 2000 = 600
        assertEquals(0f, r.dx, 0.001f)
    }

    @Test fun palavraAcimaDaTelaTambemVaiPara30PorCento() {
        assertEquals(650f, d(100f, -50f, 200f, -20f).dy, 0.001f)
    }

    @Test fun palavraPerigosamenteNaBordaRola() {
        assertTrue(!d(100f, 1890f, 200f, 1910f).isZero) // margem de 10%: 1900 é o limite
    }

    @Test fun comZoomAPalavraVaiSempreParaOCentroNaHorizontal() {
        // página com 3000 px de largura na tela de 1000: mesmo visível, a palavra é centralizada
        val r = d(700f, 800f, 800f, 830f, contentW = 3000f)
        assertEquals(500f - 750f, r.dx, 0.001f)
        assertEquals(0f, r.dy, 0.001f)
    }

    @Test fun comZoomPalavraJaNoCentroNaoRola() {
        assertTrue(d(450f, 800f, 550f, 830f, contentW = 3000f).isZero)
    }

    @Test fun semZoomNuncaRolaNaHorizontal() {
        assertEquals(0f, d(950f, 800f, 990f, 830f, contentW = 1000f).dx, 0.001f)
    }
}
