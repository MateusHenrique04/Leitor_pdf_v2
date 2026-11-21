package com.lector.app.domain

import kotlin.math.max
import kotlin.math.min
import kotlin.math.round

enum class FitMode { WIDTH, PAGE }

/**
 * Matemática de zoom/pan, porte da lógica de ui/page_view.py do desktop.
 * Tudo em floats simples (sem tipos do Compose) para testar em JUnit puro.
 * "scale" = pixels de tela por ponto PDF. O conteúdo é a página mais uma margem de [MARGIN_PT].
 */
object PageLayout {
    const val MARGIN_PT = 14f
    const val ZOOM_MIN = 1f
    const val ZOOM_MAX = 5f
    const val ZOOM_STEP = 0.25f
    const val MIN_SCALE = 0.05f

    fun clampZoom(zoom: Float): Float = zoom.coerceIn(ZOOM_MIN, ZOOM_MAX)

    /** direction = +1 (aproximar) ou -1 (afastar). Arredonda em 2 casas, como o desktop. */
    fun stepZoom(zoom: Float, direction: Int): Float =
        clampZoom(round((zoom + direction * ZOOM_STEP) * 100f) / 100f)

    fun fitScale(viewW: Float, viewH: Float, pageW: Float, pageH: Float, mode: FitMode): Float {
        val sw = pageW + 2 * MARGIN_PT
        val sh = pageH + 2 * MARGIN_PT
        return if (mode == FitMode.WIDTH) viewW / sw else min(viewW / sw, viewH / sh)
    }

    fun scale(viewW: Float, viewH: Float, pageW: Float, pageH: Float, mode: FitMode, zoom: Float): Float =
        max(MIN_SCALE, fitScale(viewW, viewH, pageW, pageH, mode) * zoom)

    fun contentSize(pagePt: Float, scale: Float): Float = (pagePt + 2 * MARGIN_PT) * scale

    /** Limita o deslocamento de um eixo: conteúdo menor que a tela fica centralizado. */
    fun clampAxis(offset: Float, content: Float, view: Float): Float =
        if (content <= view) (view - content) / 2f else offset.coerceIn(view - content, 0f)

    /** Novo deslocamento (um eixo) para o ponto sob [focal] continuar no mesmo lugar ao mudar a escala. */
    fun zoomAround(offset: Float, focal: Float, oldScale: Float, newScale: Float): Float =
        focal - (focal - offset) * (newScale / oldScale)

    /** Ao abrir uma página: centralizado na horizontal... */
    fun initialOffsetX(content: Float, view: Float): Float = (view - content) / 2f

    /** ...e no topo na vertical (se a página for mais alta que a tela). */
    fun initialOffsetY(content: Float, view: Float): Float =
        if (content > view) 0f else (view - content) / 2f
}
