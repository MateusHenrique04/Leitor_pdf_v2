package com.lector.app.data.audio

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

/** Trechos e downloads num DAO só, para as operações compostas serem uma transação. */
@Dao
abstract class AudioDao {

    // ---------------- trechos ----------------

    /** Linhas que já existem (mesma chave) são mantidas: pedir de novo não apaga o que já foi baixado. */
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    abstract suspend fun insertChunks(rows: List<AudioChunkEntity>)

    @Query(
        "SELECT * FROM audio_chunks WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version " +
            "AND chunkIndex = :chunkIndex",
    )
    abstract suspend fun getChunk(bookId: String, voice: String, version: Int, chunkIndex: Int): AudioChunkEntity?

    /**
     * Próximo trecho a baixar depois de [afterChunk] (use fromChunk - 1 para começar) até [toChunk]: PENDING, ou
     * FAILED com menos de [maxAttempts] tentativas. O [afterChunk] deixa dois downloads simultâneos não pegarem o mesmo.
     */
    @Query(
        "SELECT * FROM audio_chunks WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version " +
            "AND chunkIndex > :afterChunk AND chunkIndex <= :toChunk " +
            "AND (status = 'PENDING' OR (status = 'FAILED' AND attempts < :maxAttempts)) " +
            "ORDER BY chunkIndex LIMIT 1",
    )
    abstract suspend fun nextToDownload(
        bookId: String, voice: String, version: Int, afterChunk: Int, toChunk: Int, maxAttempts: Int,
    ): AudioChunkEntity?

    @Query(
        "UPDATE audio_chunks SET status = 'DONE', filePath = :filePath, fileBytes = :fileBytes, " +
            "durationMs = :durationMs, timings = :timings, updatedAt = :now " +
            "WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version AND chunkIndex = :chunkIndex",
    )
    abstract suspend fun markDone(
        bookId: String, voice: String, version: Int, chunkIndex: Int,
        filePath: String, fileBytes: Long, durationMs: Long?, timings: String, now: Long,
    )

    @Query(
        "UPDATE audio_chunks SET status = 'FAILED', attempts = attempts + 1, updatedAt = :now " +
            "WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version AND chunkIndex = :chunkIndex",
    )
    abstract suspend fun markFailed(bookId: String, voice: String, version: Int, chunkIndex: Int, now: Long)

    /** Trechos que falharam todas as tentativas voltam a PENDING ("tentar de novo só os que falharam"). */
    @Query(
        "UPDATE audio_chunks SET status = 'PENDING', attempts = 0, updatedAt = :now " +
            "WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version AND status = 'FAILED'",
    )
    abstract suspend fun resetFailed(bookId: String, voice: String, version: Int, now: Long)

    @Query(
        "SELECT COUNT(*) FROM audio_chunks WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version " +
            "AND status = 'DONE' AND chunkIndex BETWEEN :fromChunk AND :toChunk",
    )
    abstract suspend fun countDone(bookId: String, voice: String, version: Int, fromChunk: Int, toChunk: Int): Int

    @Query(
        "SELECT COUNT(*) FROM audio_chunks WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version " +
            "AND status = 'FAILED' AND attempts >= :maxAttempts AND chunkIndex BETWEEN :fromChunk AND :toChunk",
    )
    abstract suspend fun countFailed(
        bookId: String, voice: String, version: Int, fromChunk: Int, toChunk: Int, maxAttempts: Int,
    ): Int

    /** Índices dos trechos prontos (para o player saber o que dá para tocar offline), em ordem. */
    @Query(
        "SELECT chunkIndex FROM audio_chunks WHERE bookId = :bookId AND voice = :voice AND plannerVersion = :version " +
            "AND status = 'DONE' ORDER BY chunkIndex",
    )
    abstract fun observeDoneIndexes(bookId: String, voice: String, version: Int): Flow<List<Int>>

    /** Vozes com algum trecho pronto neste livro. */
    @Query("SELECT DISTINCT voice FROM audio_chunks WHERE bookId = :bookId AND status = 'DONE' ORDER BY voice")
    abstract fun observeVoicesWithAudio(bookId: String): Flow<List<String>>

    /** Livros que têm algum trecho baixado (selo "Disponível offline" da biblioteca). */
    @Query("SELECT DISTINCT bookId FROM audio_chunks WHERE status = 'DONE'")
    abstract fun observeBookIdsWithAudio(): Flow<List<String>>

    /** Espaço ocupado pelos MP3 do livro; [voice] = null soma todas as vozes. */
    @Query(
        "SELECT COALESCE(SUM(fileBytes), 0) FROM audio_chunks " +
            "WHERE bookId = :bookId AND (:voice IS NULL OR voice = :voice) AND status = 'DONE'",
    )
    abstract suspend fun totalBytes(bookId: String, voice: String?): Long

    @Query(
        "SELECT filePath FROM audio_chunks " +
            "WHERE bookId = :bookId AND (:voice IS NULL OR voice = :voice) AND filePath IS NOT NULL",
    )
    abstract suspend fun filePaths(bookId: String, voice: String?): List<String>

    @Query("DELETE FROM audio_chunks WHERE bookId = :bookId AND voice = :voice")
    abstract suspend fun deleteChunks(bookId: String, voice: String)

    @Query("DELETE FROM audio_chunks WHERE bookId = :bookId")
    abstract suspend fun deleteChunksOfBook(bookId: String)

    // ---------------- pedidos de download ----------------

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun upsertJob(job: DownloadJobEntity)

    @Query("SELECT * FROM download_jobs WHERE bookId = :bookId AND voice = :voice")
    abstract suspend fun getJob(bookId: String, voice: String): DownloadJobEntity?

    @Query("SELECT * FROM download_jobs WHERE bookId = :bookId AND voice = :voice")
    abstract fun observeJob(bookId: String, voice: String): Flow<DownloadJobEntity?>

    @Query("SELECT * FROM download_jobs WHERE bookId = :bookId ORDER BY voice")
    abstract fun observeJobsOfBook(bookId: String): Flow<List<DownloadJobEntity>>

    @Query("UPDATE download_jobs SET state = :state, updatedAt = :now WHERE bookId = :bookId AND voice = :voice")
    abstract suspend fun setJobState(bookId: String, voice: String, state: JobState, now: Long)

    /** Muda o estado e o motivo (null limpa o motivo anterior). */
    @Query(
        "UPDATE download_jobs SET state = :state, lastError = :lastError, updatedAt = :now " +
            "WHERE bookId = :bookId AND voice = :voice",
    )
    abstract suspend fun setJobResult(bookId: String, voice: String, state: JobState, lastError: String?, now: Long)

    /** Recalcula doneChunks do pedido a partir dos trechos prontos dentro do intervalo dele. */
    @Query(
        "UPDATE download_jobs SET updatedAt = :now, doneChunks = (" +
            "SELECT COUNT(*) FROM audio_chunks c WHERE c.bookId = download_jobs.bookId " +
            "AND c.voice = download_jobs.voice AND c.plannerVersion = download_jobs.plannerVersion " +
            "AND c.status = 'DONE' AND c.chunkIndex BETWEEN download_jobs.fromChunk AND download_jobs.toChunk) " +
            "WHERE bookId = :bookId AND voice = :voice",
    )
    abstract suspend fun refreshJobProgress(bookId: String, voice: String, now: Long)

    @Query("DELETE FROM download_jobs WHERE bookId = :bookId AND voice = :voice")
    abstract suspend fun deleteJob(bookId: String, voice: String)

    @Query("DELETE FROM download_jobs WHERE bookId = :bookId")
    abstract suspend fun deleteJobsOfBook(bookId: String)

    // ---------------- operações compostas (transação) ----------------

    /** Cria o pedido e as linhas PENDING do intervalo; o que já estava pronto é mantido. */
    @Transaction
    open suspend fun startJob(job: DownloadJobEntity, rows: List<AudioChunkEntity>) {
        insertChunks(rows)
        upsertJob(job)
        refreshJobProgress(job.bookId, job.voice, job.updatedAt)
    }

    /** Marca o trecho como pronto e atualiza o andamento do pedido, juntos. */
    @Transaction
    open suspend fun completeChunk(
        bookId: String, voice: String, version: Int, chunkIndex: Int,
        filePath: String, fileBytes: Long, durationMs: Long?, timings: String, now: Long,
    ) {
        markDone(bookId, voice, version, chunkIndex, filePath, fileBytes, durationMs, timings, now)
        refreshJobProgress(bookId, voice, now)
    }

    @Transaction
    open suspend fun deleteVoiceAudio(bookId: String, voice: String) {
        deleteChunks(bookId, voice)
        deleteJob(bookId, voice)
    }

    @Transaction
    open suspend fun deleteBookAudio(bookId: String) {
        deleteChunksOfBook(bookId)
        deleteJobsOfBook(bookId)
    }
}
