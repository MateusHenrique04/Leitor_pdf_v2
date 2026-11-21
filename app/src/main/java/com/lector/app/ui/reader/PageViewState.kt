package com.lector.app.ui.reader

import android.os.SystemClock
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.setValue
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.unit.IntSize
import com.lector.app.domain.FitMode
import com.lector.app.domain.PageLayout
import com.lector.app.domain.PageSize
import com.lector.app.domain.RevealPolicy
import com.lector.app.domain.WordRect

/**
 * Zoom, modo de ajuste e deslocamento da página. Os gestos e os botões chamam os mesmos métodos.
 * A matemática vive em [PageLayout] (testada em JUnit); aqui só há estado do Compose.
 * [offset] é o canto superior esquerdo do conteúdo (página + margem) na tela, em pixels.
 */
@Stable
class PageViewState(initialZoom: Float = 1f, initialFit: FitMode = FitMode.WIDTH) {
    var zoom by mutableFloatStateOf(PageLayout.clampZoom(initialZoom))
        private set
    var fitMode by mutableStateOf(initialFit)
        private set
    var offset by mutableStateOf(Offset.Zero)
        private set
    var viewport by mutableStateOf(IntSize.Zero)
        private set
    var pageSize by mutableStateOf(PageSize(612f, 792f))
        private set

    /** Pixels de tela por ponto PDF; 0 enquanto a tela não foi medida. */
    val scale: Float
        get() = if (viewport.width <= 0 || viewport.height <= 0) 0f else scaleFor(zoom)

    private fun scaleFor(z: Float) = PageLayout.scale(
        viewport.width.toFloat(), viewport.height.toFloat(), pageSize.width, pageSize.height, fitMode, z,
    )

    fun onViewportChanged(size: IntSize) {
        if (size == viewport) return
        viewport = size
        resetOffset()
    }

    fun onPageChanged(size: PageSize) {
        pageSize = size
        resetOffset()
    }

    fun changeFitMode(mode: FitMode) {
        fitMode = mode
        zoom = 1f
        resetOffset()
    }

    fun resetView() {
        zoom = 1f
        resetOffset()
    }

    fun zoomBy(factor: Float, focal: Offset) = zoomTo(zoom * factor, focal)

    fun zoomStep(direction: Int) = zoomTo(PageLayout.stepZoom(zoom, direction))

    fun zoomTo(newZoom: Float, focal: Offset = viewportCenter()) {
        if (scale <= 0f) {
            zoom = PageLayout.clampZoom(newZoom)
            return
        }
        val oldScale = scale
        zoom = PageLayout.clampZoom(newZoom)
        val newScale = scale
        offset = clamp(
            Offset(
                PageLayout.zoomAround(offset.x, focal.x, oldScale, newScale),
                PageLayout.zoomAround(offset.y, focal.y, oldScale, newScale),
            ),
            newScale,
        )
    }

    fun panBy(delta: Offset) {
        if (scale <= 0f) return
        offset = clamp(offset + delta, scale)
    }

    private var lastUserInteractionMs = 0L

    /** Chamado pelos gestos: a rolagem automática espera um pouco para não brigar com o dedo do usuário. */
    fun markUserInteraction() {
        lastUserInteractionMs = SystemClock.uptimeMillis()
    }

    /**
     * Acompanha a palavra grifada (pontos PDF) sem mudar o zoom: ver [RevealPolicy]. Não faz nada enquanto o
     * usuário está mexendo na página (e por [USER_PAUSE_MS] depois).
     */
    fun ensureVisible(rect: WordRect) {
        val s = scale
        if (s <= 0f) return
        if (SystemClock.uptimeMillis() - lastUserInteractionMs < USER_PAUSE_MS) return
        val m = PageLayout.MARGIN_PT * s
        val d = RevealPolicy.delta(
            left = offset.x + m + rect.x0 * s,
            top = offset.y + m + rect.y0 * s,
            right = offset.x + m + rect.x1 * s,
            bottom = offset.y + m + rect.y1 * s,
            viewW = viewport.width.toFloat(),
            viewH = viewport.height.toFloat(),
            contentW = contentWidthPx(),
        )
        if (!d.isZero) panBy(Offset(d.dx, d.dy))
    }

    /** Largura do conteúdo em pixels (para decidir se dá para arrastar na horizontal). */
    fun contentWidthPx(): Float = PageLayout.contentSize(pageSize.width, scale)

    private fun viewportCenter() = Offset(viewport.width / 2f, viewport.height / 2f)

    private fun clamp(o: Offset, s: Float) = Offset(
        PageLayout.clampAxis(o.x, PageLayout.contentSize(pageSize.width, s), viewport.width.toFloat()),
        PageLayout.clampAxis(o.y, PageLayout.contentSize(pageSize.height, s), viewport.height.toFloat()),
    )

    private fun resetOffset() {
        val s = scale
        if (s <= 0f) return
        offset = Offset(
            PageLayout.initialOffsetX(PageLayout.contentSize(pageSize.width, s), viewport.width.toFloat()),
            PageLayout.initialOffsetY(PageLayout.contentSize(pageSize.height, s), viewport.height.toFloat()),
        )
    }

    companion object {
        /** Depois de um gesto do usuário, a rolagem automática espera este tempo. */
        const val USER_PAUSE_MS = 2500L

        val Saver: Saver<PageViewState, Any> = listSaver(
            save = { listOf(it.zoom, it.fitMode.name) },
            restore = { PageViewState(it[0] as Float, FitMode.valueOf(it[1] as String)) },
        )
    }
}
