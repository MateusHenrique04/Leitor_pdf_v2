package com.lector.app.download

import android.content.Context
import android.os.StatFs
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import com.lector.app.data.BookEntity
import com.lector.app.data.BookIndexStore
import com.lector.app.data.audio.AudioChunkEntity
import com.lector.app.data.audio.AudioDatabase
import com.lector.app.data.audio.DownloadJobEntity
import com.lector.app.data.audio.JobState
import com.lector.app.domain.DownloadEstimate
import com.lector.app.domain.DownloadEstimator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.concurrent.TimeUnit

sealed interface StartResult {
    data class Started(val job: DownloadJobEntity, val estimate: DownloadEstimate) : StartResult
    /** O livro ainda não foi indexado (abra-o e espere "Preparando o livro"). */
    data object NoIndex : StartResult
    /** Nenhum trecho com texto nas páginas pedidas. */
    data object NoText : StartResult
    data class NotEnoughSpace(val neededBytes: Long, val availableBytes: Long) : StartResult
}

/**
 * Ponto de entrada do download offline: cria o pedido (Room) e agenda o [BookDownloadWorker]. Pausar, retomar,
 * cancelar, tentar de novo e apagar também passam por aqui. Leve de criar: pode ser instanciado onde precisar.
 */
class DownloadManager(private val context: Context) {
    private val dao = AudioDatabase.get(context).audioDao()
    private val indexStore = BookIndexStore(File(context.filesDir, "index"))
    private val work get() = WorkManager.getInstance(context)

    /** Tamanho e tempo de áudio estimados para as páginas pedidas (null se o índice não está pronto ou não há texto). */
    suspend fun estimate(book: BookEntity, fromPage: Int, toPage: Int): DownloadEstimate? = withContext(Dispatchers.IO) {
        val index = indexStore.load(book.id, book.totalPages) ?: return@withContext null
        val range = index.chunkRange(fromPage, toPage) ?: return@withContext null
        DownloadEstimator.estimate(range.map { index.chunks[it].text.length })
    }

    suspend fun start(
        book: BookEntity,
        voice: String,
        fromPage: Int,
        toPage: Int,
        wifiOnly: Boolean,
        chargingOnly: Boolean,
    ): StartResult = withContext(Dispatchers.IO) {
        val index = indexStore.load(book.id, book.totalPages) ?: return@withContext StartResult.NoIndex
        val range = index.chunkRange(fromPage, toPage) ?: return@withContext StartResult.NoText
        val estimate = DownloadEstimator.estimate(range.map { index.chunks[it].text.length })
        val available = StatFs(context.filesDir.path).availableBytes
        if (!DownloadEstimator.enoughSpace(estimate.bytes, available)) {
            return@withContext StartResult.NotEnoughSpace(estimate.bytes, available)
        }
        val now = System.currentTimeMillis()
        val rows = range.map {
            AudioChunkEntity(bookId = book.id, voice = voice, plannerVersion = index.plannerVersion, chunkIndex = it)
        }
        val job = DownloadJobEntity(
            bookId = book.id, voice = voice, plannerVersion = index.plannerVersion,
            fromPage = fromPage, toPage = toPage, fromChunk = range.first, toChunk = range.last,
            totalChunks = rows.size, state = JobState.QUEUED, wifiOnly = wifiOnly, chargingOnly = chargingOnly,
            updatedAt = now,
        )
        dao.startJob(job, rows)
        enqueue(job)
        StartResult.Started(job, estimate)
    }

    /** Pausar: guarda o estado e para o worker. O que já foi baixado fica. */
    suspend fun pause(bookId: String, voice: String) {
        dao.setJobState(bookId, voice, JobState.PAUSED, System.currentTimeMillis())
        work.cancelUniqueWork(workName(bookId, voice))
    }

    /** Retomar: agenda de novo; começa do primeiro trecho que falta. */
    suspend fun resume(bookId: String, voice: String) {
        val job = dao.getJob(bookId, voice) ?: return
        dao.setJobResult(bookId, voice, JobState.QUEUED, null, System.currentTimeMillis())
        enqueue(job)
    }

    /** Cancelar: para e descarta o pedido; os trechos já baixados continuam (use [deleteVoice] para apagar). */
    suspend fun cancel(bookId: String, voice: String) {
        work.cancelUniqueWork(workName(bookId, voice))
        dao.deleteJob(bookId, voice)
    }

    /** "Tentar de novo só os que falharam". */
    suspend fun retryFailed(bookId: String, voice: String) {
        val job = dao.getJob(bookId, voice) ?: return
        val now = System.currentTimeMillis()
        dao.resetFailed(bookId, voice, job.plannerVersion, now)
        dao.setJobResult(bookId, voice, JobState.QUEUED, null, now)
        enqueue(job)
    }

    /** Apaga o áudio de uma voz do livro (arquivos e linhas); as outras vozes e livros ficam intactos. */
    suspend fun deleteVoice(bookId: String, voice: String) = withContext(Dispatchers.IO) {
        work.cancelUniqueWork(workName(bookId, voice))
        dao.deleteVoiceAudio(bookId, voice)
        AudioFiles.voiceDir(context, bookId, voice).deleteRecursively()
    }

    /** Apaga todo o áudio do livro (ao remover o livro da biblioteca). */
    suspend fun deleteBook(bookId: String) = withContext(Dispatchers.IO) {
        work.cancelAllWorkByTag(bookTag(bookId))
        dao.deleteBookAudio(bookId)
        AudioFiles.bookDir(context, bookId).deleteRecursively()
    }

    private fun enqueue(job: DownloadJobEntity) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(if (job.wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED)
            .setRequiresCharging(job.chargingOnly)
            .build()
        val request = OneTimeWorkRequestBuilder<BookDownloadWorker>()
            .setInputData(workDataOf(BookDownloadWorker.KEY_BOOK to job.bookId, BookDownloadWorker.KEY_VOICE to job.voice))
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .addTag(bookTag(job.bookId))
            .build()
        work.enqueueUniqueWork(workName(job.bookId, job.voice), ExistingWorkPolicy.REPLACE, request)
    }

    companion object {
        fun workName(bookId: String, voice: String) = "download:$bookId:$voice"
        fun bookTag(bookId: String) = "download-book:$bookId"
    }
}
