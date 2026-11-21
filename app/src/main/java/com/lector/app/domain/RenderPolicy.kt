package com.lector.app.domain

import kotlin.math.ceil
import kotlin.math.min
import kotlin.math.sqrt

/** Quando vale a pena re-renderizar a página (porte de _ensure_quality do desktop). */
object RenderPolicy {
    /** Teto de pixels de uma página renderizada (ARGB_8888 = 4 bytes/pixel; 12M px ~ 48 MB). */
    const val MAX_RENDER_PIXELS = 12_000_000L

    /** Escala (px/pt) que a tela precisa agora, arredondada para cima em passos de 0,05 e limitada pelo teto. */
    fun neededScale(screenScale: Float, maxPixels: Long, pageW: Float, pageH: Float): Float {
        val cap = sqrt(maxPixels.toFloat() / (pageW * pageH).coerceAtLeast(1f))
        val quantized = ceil(screenScale * 20f) / 20f
        return min(quantized, cap)
    }

    /** A imagem atual serve se não está borrada (<95% do necessário) nem desperdiçada (>160%). */
    fun isAcceptable(currentScale: Float, neededScale: Float): Boolean =
        currentScale > 0f && neededScale * 0.95f <= currentScale && currentScale <= neededScale * 1.6f
}
