package com.lector.app.domain

import kotlin.math.abs

/**
 * O grifo da Fase 7 só cai no lugar certo se o tamanho da página do PdfBox (cropBox, com rotação)
 * for igual ao do PdfRenderer (que alimenta o PageViewState). Estas funções fazem essa conferência.
 */
object PageGeometry {
    /** O PdfRenderer arredonda a largura/altura para inteiro: tolerância > 1 pt. */
    const val TOLERANCE_PT = 1.5f

    /** Tamanho da página como aparece na tela: com rotação de 90/270 graus, largura e altura trocam. */
    fun rotatedSize(width: Float, height: Float, rotation: Int): PageSize {
        val r = ((rotation % 360) + 360) % 360
        return if (r == 90 || r == 270) PageSize(height, width) else PageSize(width, height)
    }

    fun matches(pdfBox: PageSize, renderer: PageSize, tolerance: Float = TOLERANCE_PT): Boolean =
        abs(pdfBox.width - renderer.width) <= tolerance && abs(pdfBox.height - renderer.height) <= tolerance

    /** null se bate; senão uma descrição legível da diferença. */
    fun mismatch(pdfBox: PageSize, renderer: PageSize, tolerance: Float = TOLERANCE_PT): String? =
        if (matches(pdfBox, renderer, tolerance)) null
        else "PdfBox %.1f x %.1f, PdfRenderer %.1f x %.1f".format(
            java.util.Locale.US, pdfBox.width, pdfBox.height, renderer.width, renderer.height,
        )
}
