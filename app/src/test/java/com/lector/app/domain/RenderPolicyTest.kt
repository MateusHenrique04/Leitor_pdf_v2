package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RenderPolicyTest {
    @Test fun arredondaParaCimaEmPassosDe005() =
        assertEquals(1.05f, RenderPolicy.neededScale(1.01f, 1_000_000_000L, 612f, 792f), 1e-4f)

    @Test fun escalaJaNoPassoNaoSobe() =
        assertEquals(2.0f, RenderPolicy.neededScale(2.0f, 1_000_000_000L, 612f, 792f), 1e-4f)

    @Test fun tetoDePixelsLimita() =
        assertEquals(1.0f, RenderPolicy.neededScale(3f, 1_000_000L, 1000f, 1000f), 1e-4f)

    @Test fun semImagemNaoEhAceitavel() = assertFalse(RenderPolicy.isAcceptable(0f, 2f))
    @Test fun igualEhAceitavel() = assertTrue(RenderPolicy.isAcceptable(2f, 2f))
    @Test fun borradaNaoEhAceitavel() = assertFalse(RenderPolicy.isAcceptable(1.8f, 2f))
    @Test fun ligeiramenteMenorEhAceitavel() = assertTrue(RenderPolicy.isAcceptable(1.95f, 2f))
    @Test fun grandeDemaisNaoEhAceitavel() = assertFalse(RenderPolicy.isAcceptable(3.4f, 2f))
    @Test fun ate160PorCentoEhAceitavel() = assertTrue(RenderPolicy.isAcceptable(3.0f, 2f))
}
