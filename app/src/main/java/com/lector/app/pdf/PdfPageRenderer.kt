package com.lector.app.pdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import com.lector.app.domain.PageSize
import java.io.Closeable
import kotlin.math.roundToInt

/**
 * Desenha páginas com o PdfRenderer nativo. O PdfRenderer só permite UMA página aberta por vez
 * e não é thread-safe, por isso tudo passa pelo mesmo lock.
 */
class PdfPageRenderer private constructor(
    private val pfd: ParcelFileDescriptor,
    private val renderer: PdfRenderer,
) : Closeable {
    private val lock = Any()
    private var closed = false
    private val sizes = HashMap<Int, PageSize>()

    val pageCount: Int = renderer.pageCount

    fun pageSize(index: Int): PageSize = synchronized(lock) {
        check(!closed) { "PDF fechado" }
        sizes.getOrPut(index) {
            renderer.openPage(index).use { PageSize(it.width.toFloat(), it.height.toFloat()) }
        }
    }

    /** [pixelsPerPoint]: pixels por ponto PDF. O bitmap sai com fundo branco. */
    fun render(index: Int, pixelsPerPoint: Float): Bitmap = synchronized(lock) {
        check(!closed) { "PDF fechado" }
        renderer.openPage(index).use { page ->
            val w = (page.width * pixelsPerPoint).roundToInt().coerceAtLeast(1)
            val h = (page.height * pixelsPerPoint).roundToInt().coerceAtLeast(1)
            val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            bmp.eraseColor(Color.WHITE)
            page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            bmp
        }
    }

    override fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            runCatching { renderer.close() }
            runCatching { pfd.close() }
        }
    }

    companion object {
        fun open(context: Context, uri: Uri): PdfPageRenderer {
            val pfd = context.contentResolver.openFileDescriptor(uri, "r")
                ?: error("Não foi possível abrir o arquivo")
            try {
                return PdfPageRenderer(pfd, PdfRenderer(pfd))
            } catch (e: Throwable) {
                runCatching { pfd.close() }
                throw e
            }
        }
    }
}
