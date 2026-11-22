package com.lector.app.download

import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.StatFs
import android.os.SystemClock
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import com.lector.app.data.BookIndexStore
import com.lector.app.data.BookRepository
import com.lector.app.data.LectorDatabase
import com.lector.app.data.audio.AudioDatabase
import com.lector.app.data.audio.JobState
import com.lector.app.domain.DownloadEstimator
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Baixa a narração de um livro (um pedido por livro + voz; ver [DownloadManager]). Retomável: o andamento está no
 * Room, então depois de uma interrupção continua do primeiro trecho que falta. Roda em primeiro plano quando o
 * Android permite (notificação com Pausar/Cancelar); se não permitir, roda como trabalho comum.
 */
class BookDownloadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun getForegroundInfo(): ForegroundInfo {
        val bookId = inputData.getString(KEY_BOOK).orEmpty()
        val voice = inputData.getString(KEY_VOICE).orEmpty()
        return foregroundInfo(bookId, voice, "Livro", 0, 0)
    }

    private fun foregroundInfo(bookId: String, voice: String, title: String, done: Int, total: Int): ForegroundInfo {
        val notification = DownloadNotifications.build(applicationContext, bookId, voice, title, done, total)
        val id = DownloadNotifications.notificationId(bookId, voice)
        return if (Build.VERSION.SDK_INT >= 29) {
            ForegroundInfo(id, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            ForegroundInfo(id, notification)
        }
    }

    override suspend fun doWork(): Result {
        val bookId = inputData.getString(KEY_BOOK) ?: return Result.failure()
        val voice = inputData.getString(KEY_VOICE) ?: return Result.failure()
        val ctx = applicationContext
        val dao = AudioDatabase.get(ctx).audioDao()
        val job = dao.getJob(bookId, voice) ?: return Result.failure()
        val book = BookRepository(ctx, LectorDatabase.get(ctx).bookDao()).getBook(bookId)
        val title = book?.title ?: "Livro"
        val now = { System.currentTimeMillis() }

        val index = book?.let { BookIndexStore(File(ctx.filesDir, "index")).load(bookId, it.totalPages) }
        if (index == null) {
            dao.setJobResult(bookId, voice, JobState.FAILED, "O livro ainda não foi preparado para narração. Abra-o e espere o índice.", now())
            return Result.failure()
        }

        // Espaço: o que falta baixar (proporcional ao que já está pronto) contra o espaço livre agora.
        val done0 = dao.countDone(bookId, voice, job.plannerVersion, job.fromChunk, job.toChunk)
        val lengths = (job.fromChunk..job.toChunk).mapNotNull { index.chunks.getOrNull(it)?.text?.length }
        val full = DownloadEstimator.estimate(lengths).bytes
        val remaining = if (job.totalChunks > 0) full * (job.totalChunks - done0) / job.totalChunks else full
        val available = StatFs(ctx.filesDir.path).availableBytes
        if (!DownloadEstimator.enoughSpace(remaining, available)) {
            dao.setJobResult(bookId, voice, JobState.FAILED, "Sem espaço livre suficiente (precisa de ~${remaining / (1024 * 1024)} MB).", now())
            return Result.failure()
        }

        runCatching { setForeground(foregroundInfo(bookId, voice, title, done0, job.totalChunks)) } // pode ser negado: segue sem
        dao.setJobResult(bookId, voice, JobState.RUNNING, null, now())

        val store = RoomDownloadStore(dao, bookId, voice, job.plannerVersion, job.toChunk)
        val downloader = BookDownloader(store, EdgeSynthesizer(), AudioFiles.voiceDir(ctx, bookId, voice))
        var lastUpdate = 0L
        try {
            val outcome = downloader.run(index, voice, job.fromChunk - 1) { n ->
                val t = SystemClock.elapsedRealtime()
                if (t - lastUpdate > 2_000) { // não atualizar a notificação a cada trecho
                    lastUpdate = t
                    runCatching { setForeground(foregroundInfo(bookId, voice, title, done0 + n, job.totalChunks)) }
                }
            }
            return when (outcome) {
                is BookDownloader.Outcome.Finished -> {
                    val failed = dao.countFailed(bookId, voice, job.plannerVersion, job.fromChunk, job.toChunk, BookDownloader.MAX_ATTEMPTS)
                    if (failed > 0) {
                        dao.setJobResult(bookId, voice, JobState.FAILED, "$failed trechos falharam.", now())
                    } else {
                        dao.setJobResult(bookId, voice, JobState.DONE, null, now())
                    }
                    Result.success()
                }
                is BookDownloader.Outcome.Aborted -> {
                    // Rede caiu ou o servidor recusou várias vezes seguidas: espera e tenta de novo (WorkManager).
                    dao.setJobResult(bookId, voice, JobState.QUEUED, "Sem conexão ou servidor recusou: ${outcome.cause.message}", now())
                    Result.retry()
                }
            }
        } catch (e: CancellationException) {
            // Pausar e Cancelar já gravaram o estado deles; se foi o sistema que parou, volta para a fila.
            withContext(NonCancellable) {
                if (dao.getJob(bookId, voice)?.state == JobState.RUNNING) {
                    dao.setJobState(bookId, voice, JobState.QUEUED, now())
                }
            }
            throw e
        }
    }

    companion object {
        const val KEY_BOOK = "bookId"
        const val KEY_VOICE = "voice"
    }
}
