package com.lector.app.pdf

import android.content.Context
import android.net.Uri
import com.lector.app.domain.Glyph
import com.lector.app.domain.LineBuilder
import com.lector.app.domain.PageGeometry
import com.lector.app.domain.PageSize
import com.lector.app.domain.ParagraphGrouper
import com.lector.app.domain.RawPage
import com.lector.app.domain.TextLine
import com.lector.app.domain.WordAssembler
import com.lector.app.domain.WordBox
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import com.tom_roush.pdfbox.text.TextPosition
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.Closeable
import java.io.File
import java.io.Writer
import java.security.MessageDigest

/** Resultado da extração de UMA página. Coordenadas em pontos PDF, origem no canto superior esquerdo. */
data class ExtractedPage(
    val index: Int,
    val words: List<WordBox>,
    val lines: List<TextLine>,
    val raw: RawPage,
    /** Tamanho da página segundo o PdfBox (cropBox, já com rotação). Deve bater com o PdfRenderer. */
    val size: PageSize,
    val rotation: Int,
    val extractMs: Long,
)

/**
 * Extrai texto e palavras com retângulos (PdfBox-Android). NÃO use na thread principal: os métodos
 * `suspend` já trocam para Dispatchers.IO; os métodos sem `suspend` bloqueiam.
 * Tudo passa por um lock (o PDDocument não é thread-safe). Mantém um cache pequeno de páginas.
 */
class PdfEngine private constructor(
    private val doc: PDDocument,
    val openMs: Long,
) : Closeable {
    private val lock = Any()
    private var closed = false

    val pageCount: Int = doc.numberOfPages

    private val cache = object : LinkedHashMap<Int, ExtractedPage>(8, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Int, ExtractedPage>?): Boolean =
            size > MAX_CACHED_PAGES
    }

    /** Palavras da página, em ordem de leitura. */
    suspend fun getPageWords(pageIndex: Int): List<WordBox> = page(pageIndex).words

    /** Texto bruto da página (blocos = parágrafos), entrada do TextCleaner. */
    suspend fun extractRawPage(pageIndex: Int): RawPage = page(pageIndex).raw

    suspend fun page(pageIndex: Int): ExtractedPage = withContext(Dispatchers.IO) { extractPage(pageIndex) }

    /** Pré-busca (a próxima página: frases cruzam páginas). Erros são ignorados. */
    suspend fun prefetch(pageIndex: Int) {
        if (pageIndex !in 0 until pageCount) return
        runCatching { page(pageIndex) }
    }

    /** Versão bloqueante. [useCache] = false força extrair de novo (usado na medição de tempo). */
    fun extractPage(index: Int, useCache: Boolean = true): ExtractedPage = synchronized(lock) {
        check(!closed) { "PDF fechado" }
        require(index in 0 until pageCount) { "Página fora do intervalo: $index" }
        val hit = if (useCache) cache[index] else null
        hit ?: extract(index).also { cache[index] = it }
    }

    private fun extract(index: Int): ExtractedPage {
        val t0 = System.nanoTime()
        val page = doc.getPage(index)
        val crop = page.cropBox
        val rotation = ((page.rotation % 360) + 360) % 360
        val size = PageGeometry.rotatedSize(crop.width, crop.height, rotation)

        val stripper = GlyphStripper()
        stripper.setSortByPosition(SORT_BY_POSITION)
        stripper.setStartPage(index + 1)
        stripper.setEndPage(index + 1)
        stripper.writeText(doc, DiscardWriter)

        val words = WordAssembler.assemble(stripper.glyphs)
        val lines = LineBuilder.build(words)
        val raw = RawPage(ParagraphGrouper.group(lines))
        val ms = (System.nanoTime() - t0) / 1_000_000
        return ExtractedPage(index, words, lines, raw, size, rotation, ms)
    }

    override fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            cache.clear()
            runCatching { doc.close() }
        }
    }

    /**
     * Coleta cada caractere com posição. writeString é chamado pelo PdfBox por palavra; guardamos os glifos e
     * uma separação entre chamadas, e a montagem das palavras fica no [WordAssembler] (Kotlin puro, testado).
     * Coordenadas "DirAdj": já ajustadas à rotação da página, origem no canto superior esquerdo.
     */
    private class GlyphStripper : PDFTextStripper() {
        val glyphs = ArrayList<Glyph>()

        override fun writeString(text: String?, textPositions: MutableList<TextPosition>?) {
            if (textPositions == null) return
            for (tp in textPositions) {
                glyphs.add(Glyph(tp.unicode ?: "", tp.xDirAdj, tp.yDirAdj, tp.widthDirAdj, tp.heightDir))
            }
            glyphs.add(Glyph(" ", 0f, 0f, 0f, 0f)) // fim de palavra
        }
    }

    private object DiscardWriter : Writer() {
        override fun write(cbuf: CharArray, off: Int, len: Int) {}
        override fun flush() {}
        override fun close() {}
    }

    companion object {
        /**
         * false = ordem do fluxo do PDF (como o PyMuPDF do desktop). Em PDF de várias colunas isso costuma
         * dar a ordem certa; ordenar por posição misturaria as colunas linha a linha.
         */
        const val SORT_BY_POSITION = false
        const val MAX_CACHED_PAGES = 6

        /** Abre o PDF. Bloqueante: chame fora da main thread. */
        fun open(context: Context, uri: Uri): PdfEngine {
            val t0 = System.nanoTime()
            PDFBoxResourceLoader.init(context.applicationContext) // obrigatório antes de usar o PdfBox
            val file = copyToCache(context, uri)
            // load(File) lê sob demanda (não carrega o PDF inteiro na memória).
            val doc = PDDocument.load(file)
            return PdfEngine(doc, (System.nanoTime() - t0) / 1_000_000)
        }

        /** Apaga a cópia local do PDF (chame ao remover o livro da biblioteca). */
        fun deleteCachedCopy(context: Context, uri: Uri) {
            runCatching { cacheFile(context, uri).delete() }
        }

        private fun cacheFile(context: Context, uri: Uri): File {
            val dir = File(context.cacheDir, "pdfbox").apply { mkdirs() }
            val hash = MessageDigest.getInstance("SHA-1").digest(uri.toString().toByteArray())
                .joinToString("") { "%02x".format(it) }
            return File(dir, "$hash.pdf")
        }

        /** O SAF só dá um fluxo; o PdfBox precisa de acesso aleatório, então copiamos para o cache do app. */
        private fun copyToCache(context: Context, uri: Uri): File {
            val target = cacheFile(context, uri)
            val size = context.contentResolver.openFileDescriptor(uri, "r")?.use { it.statSize } ?: -1L
            if (target.exists() && size >= 0 && target.length() == size) return target
            val tmp = File(target.parentFile, target.name + ".tmp")
            val input = context.contentResolver.openInputStream(uri) ?: error("Não foi possível abrir o arquivo")
            input.use { src -> tmp.outputStream().use { dst -> src.copyTo(dst) } }
            target.delete()
            check(tmp.renameTo(target)) { "Falha ao gravar a cópia do PDF" }
            return target
        }
    }
}
