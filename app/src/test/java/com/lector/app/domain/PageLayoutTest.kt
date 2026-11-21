package com.lector.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PageLayoutTest {
    private val d = 1e-3f

    // página 572x772 pt -> com margem de 14 pt: 600x800
    @Test fun fitLarguraUsaSoALargura() =
        assertEquals(1000f / 600f, PageLayout.fitScale(1000f, 2000f, 572f, 772f, FitMode.WIDTH), d)

    @Test fun fitPaginaEscolheOMenor() {
        assertEquals(1000f / 600f, PageLayout.fitScale(1000f, 2000f, 572f, 772f, FitMode.PAGE), d) // limitado pela largura
        assertEquals(1000f / 800f, PageLayout.fitScale(1000f, 1000f, 572f, 772f, FitMode.PAGE), d) // limitado pela altura
    }

    @Test fun escalaMultiplicaPeloZoom() =
        assertEquals(2f * 1000f / 600f, PageLayout.scale(1000f, 2000f, 572f, 772f, FitMode.WIDTH, 2f), d)

    @Test fun escalaTemMinimo() =
        assertEquals(PageLayout.MIN_SCALE, PageLayout.scale(1f, 1f, 5000f, 5000f, FitMode.WIDTH, 1f), d)

    @Test fun stepZoom() {
        assertEquals(1.25f, PageLayout.stepZoom(1f, +1), d)
        assertEquals(1f, PageLayout.stepZoom(1f, -1), d)
        assertEquals(5f, PageLayout.stepZoom(5f, +1), d)
        assertEquals(1.35f, PageLayout.stepZoom(1.1f, +1), d)
    }

    @Test fun clampZoom() {
        assertEquals(1f, PageLayout.clampZoom(0.2f), d)
        assertEquals(5f, PageLayout.clampZoom(9f), d)
    }

    @Test fun clampAxisCentraliza() = assertEquals(200f, PageLayout.clampAxis(-77f, 600f, 1000f), d)

    @Test fun clampAxisLimitaConteudoMaior() {
        assertEquals(0f, PageLayout.clampAxis(10f, 3000f, 1000f), d)
        assertEquals(-2000f, PageLayout.clampAxis(-9999f, 3000f, 1000f), d)
        assertEquals(-500f, PageLayout.clampAxis(-500f, 3000f, 1000f), d)
    }

    @Test fun zoomAroundMantemOPontoSobOFocal() {
        val offset = -120f; val focal = 400f; val old = 2f; val new = 3.5f
        val novo = PageLayout.zoomAround(offset, focal, old, new)
        val pontoAntes = (focal - offset) / old
        val pontoDepois = (focal - novo) / new
        assertEquals(pontoAntes, pontoDepois, d)
    }

    @Test fun zoomAroundSemMudancaDeEscala() = assertEquals(-50f, PageLayout.zoomAround(-50f, 300f, 2f, 2f), d)

    @Test fun offsetInicialX_centralizaMesmoSeMaior() {
        assertEquals(200f, PageLayout.initialOffsetX(600f, 1000f), d)
        assertEquals(-1000f, PageLayout.initialOffsetX(3000f, 1000f), d)
    }

    @Test fun offsetInicialY_topoSeMaiorECentroSeMenor() {
        assertEquals(0f, PageLayout.initialOffsetY(3000f, 1000f), d)
        assertEquals(100f, PageLayout.initialOffsetY(800f, 1000f), d)
    }

    @Test fun contentSizeInclueMargens() = assertEquals(600f * 2f, PageLayout.contentSize(572f, 2f), d)

    @Test fun zoomMinimoEhUm() = assertTrue(PageLayout.ZOOM_MIN == 1f && PageLayout.ZOOM_MAX == 5f)
}
