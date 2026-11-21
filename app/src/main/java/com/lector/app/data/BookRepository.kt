package com.lector.app.data

import android.content.Context
import android.content.Intent
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.provider.OpenableColumns
import com.lector.app.domain.BookTitle
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

sealed interface AddBookResult {
    data class Added(val book: BookEntity) : AddBookResult
    data class AlreadyExists(val book: BookEntity) : AddBookResult
    data class Failed(val reason: String) : AddBookResult
}

class BookRepository(
    private val context: Context,
    private val dao: BookDao,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    fun observeAll(): Flow<List<BookEntity>> = dao.observeAll()

    suspend fun addFromUri(uri: Uri): AddBookResult = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver
        try {
            // 1) Permissão persistente: sem isso o URI deixa de funcionar quando o app fecha.
            resolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)

            val existing = dao.getByUri(uri.toString())
            if (existing != null) return@withContext AddBookResult.AlreadyExists(existing)

            // 2) Valida que é um PDF legível e conta as páginas.
            val pages = resolver.openFileDescriptor(uri, "r")?.use { pfd ->
                PdfRenderer(pfd).use { it.pageCount }
            }
            if (pages == null || pages <= 0) {
                releaseQuietly(uri)
                return@withContext AddBookResult.Failed("Não consegui ler as páginas deste PDF.")
            }

            // 3) Título a partir do nome do arquivo.
            val displayName = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }

            val now = clock()
            val book = BookEntity(
                id = UUID.randomUUID().toString(),
                uri = uri.toString(),
                title = BookTitle.fromFileName(displayName),
                totalPages = pages,
                addedAt = now,
                lastOpenedAt = now,
            )
            dao.insert(book)
            AddBookResult.Added(book)
        } catch (e: CancellationException) {
            throw e
        } catch (e: SecurityException) {
            releaseQuietly(uri)
            AddBookResult.Failed("Sem permissão para abrir este arquivo (PDF protegido por senha?).")
        } catch (e: Exception) {
            releaseQuietly(uri)
            AddBookResult.Failed("Não consegui abrir este arquivo como PDF.")
        }
    }

    suspend fun remove(book: BookEntity) = withContext(Dispatchers.IO) {
        dao.deleteById(book.id)
        runCatching { BookIndexStore(File(context.filesDir, "index")).delete(book.id) }
        releaseQuietly(Uri.parse(book.uri)) // libera a cota de permissões persistentes
    }

    suspend fun getBook(id: String): BookEntity? = dao.getById(id)

    suspend fun touch(id: String) = dao.touch(id, clock())

    suspend fun savePosition(bookId: String, page: Int, chunkIndex: Int) =
        dao.updatePosition(bookId, page, chunkIndex, clock())

    private fun releaseQuietly(uri: Uri) {
        try {
            context.contentResolver.releasePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: Exception) {
        }
    }
}
