package com.lector.app.domain

/**
 * Um caractere (ou ligadura) já posicionado, em pontos PDF, origem no canto superior esquerdo
 * (coordenadas "DirAdj" do PdfBox, que já consideram a rotação da página).
 * [baseline] = y da linha de base; [height] = altura do glifo.
 */
data class Glyph(val unicode: String, val x: Float, val baseline: Float, val width: Float, val height: Float)

/** Palavra com retângulo em pontos PDF (origem no canto superior esquerdo). [y1] = linha de base. */
data class WordBox(val text: String, val x0: Float, val y0: Float, val x1: Float, val y1: Float)

/** Linha visual de texto. [y1] = linha de base (mediana das palavras); [y0] = y1 - altura típica. */
data class TextLine(val text: String, val x0: Float, val y0: Float, val x1: Float, val y1: Float) {
    val height: Float get() = y1 - y0
}
