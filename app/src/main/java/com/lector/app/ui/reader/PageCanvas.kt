package com.lector.app.ui.reader

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateCentroid
import androidx.compose.foundation.gestures.calculateCentroidSize
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.isSpecified
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.lector.app.domain.Highlight
import com.lector.app.domain.PageLayout
import kotlin.math.abs
import kotlin.math.roundToInt

private val LINE_COLOR = Color(0xFFFFF9C4) // amarelo bem claro: linhas do trecho
private val WORD_COLOR = Color(0xFFFFB74D) // laranja: palavra falada

/**
 * Desenha a página (papel branco na hora, imagem nítida quando chega) com pinça, arrasto,
 * toque duplo e deslize horizontal para virar de página. Na Fase 7 os grifos serão
 * desenhados aqui, com a mesma escala/deslocamento.
 */
@Composable
fun PageCanvas(
    page: Int,
    state: PageViewState,
    rendered: RenderedPage?,
    highlight: Highlight?,
    onSwipePage: (direction: Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val swipeCallback by rememberUpdatedState(onSwipePage)

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .onSizeChanged { state.onViewportChanged(it) }
            .pointerInput(Unit) {
                detectTapGestures(
                    onDoubleTap = { p -> state.markUserInteraction(); if (state.zoom > 1.05f) state.resetView() else state.zoomTo(2.5f, p) },
                )
            }
            .pointerInput(Unit) {
                val slop = viewConfiguration.touchSlop
                val swipeThreshold = 80.dp.toPx()
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    var pastSlop = false
                    var accZoom = 1f
                    var accPan = Offset.Zero
                    var totalPan = Offset.Zero
                    var multiTouch = false
                    do {
                        val event = awaitPointerEvent()
                        if (event.changes.any { it.isConsumed }) break
                        if (event.changes.size > 1) multiTouch = true
                        val zoomChange = event.calculateZoom()
                        val pan = event.calculatePan()
                        totalPan += pan
                        if (!pastSlop) {
                            accZoom *= zoomChange
                            accPan += pan
                            val zoomMotion = abs(1f - accZoom) * event.calculateCentroidSize(useCurrent = false)
                            if (zoomMotion > slop || accPan.getDistance() > slop) pastSlop = true
                        }
                        if (pastSlop) {
                            state.markUserInteraction()
                            val centroid = event.calculateCentroid(useCurrent = true)
                            if (zoomChange != 1f && centroid.isSpecified) state.zoomBy(zoomChange, centroid)
                            if (pan != Offset.Zero) state.panBy(pan)
                            event.changes.forEach { if (it.positionChanged()) it.consume() }
                        }
                    } while (event.changes.any { it.pressed })

                    // Deslize horizontal só vira a página quando não há como arrastar na horizontal.
                    val cannotPanSideways = state.contentWidthPx() <= state.viewport.width + 1f
                    if (!multiTouch && cannotPanSideways &&
                        abs(totalPan.x) > swipeThreshold && abs(totalPan.x) > 2f * abs(totalPan.y)
                    ) {
                        swipeCallback(if (totalPan.x < 0) +1 else -1)
                    }
                }
            },
    ) {
        val s = state.scale
        if (s <= 0f) return@Canvas
        val m = PageLayout.MARGIN_PT * s
        val left = state.offset.x + m
        val top = state.offset.y + m
        val pw = state.pageSize.width * s
        val ph = state.pageSize.height * s

        drawRect(Color.White, topLeft = Offset(left, top), size = Size(pw, ph))
        rendered?.takeIf { it.page == page }?.let { r ->
            drawImage(
                image = r.image,
                srcOffset = IntOffset.Zero,
                srcSize = IntSize(r.image.width, r.image.height),
                dstOffset = IntOffset(left.roundToInt(), top.roundToInt()),
                dstSize = IntSize(pw.roundToInt(), ph.roundToInt()),
                filterQuality = FilterQuality.High,
            )
        }
        // Grifo da narração (Fase 7): mesma escala e deslocamento da página. Multiply: o texto continua escuro.
        highlight?.takeIf { it.page == page }?.let { h ->
            for (l in h.lines) drawRect(LINE_COLOR, Offset(left + l.x0 * s, top + l.y0 * s), Size((l.x1 - l.x0) * s, (l.y1 - l.y0) * s), blendMode = BlendMode.Multiply)
            h.word?.let { w ->
                val pad = 1.5f * s
                drawRect(WORD_COLOR, Offset(left + w.x0 * s - pad, top + w.y0 * s - pad), Size((w.x1 - w.x0) * s + 2 * pad, (w.y1 - w.y0) * s + 2 * pad), blendMode = BlendMode.Multiply)
            }
        }
    }
}
