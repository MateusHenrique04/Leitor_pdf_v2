package com.lector.app.data.audio

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

enum class ChunkStatus { PENDING, DONE, FAILED }

enum class JobState { QUEUED, RUNNING, PAUSED, DONE, FAILED }

/**
 * Um trecho de narração baixado (ou por baixar). Chave do cache: livro + voz + versão do ChunkPlanner + índice do
 * trecho. O MP3 fica em arquivo ([filePath]); os tempos das palavras, em [timings] (formato do TimingsCodec).
 * Gerado sempre a +0% de velocidade: a velocidade é do player.
 */
@Entity(
    tableName = "audio_chunks",
    indices = [Index(value = ["bookId", "voice", "plannerVersion", "chunkIndex"], unique = true)],
)
data class AudioChunkEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val bookId: String,
    val voice: String,
    val plannerVersion: Int,
    val chunkIndex: Int,
    val status: ChunkStatus = ChunkStatus.PENDING,
    val attempts: Int = 0,
    val filePath: String? = null,
    val fileBytes: Long = 0,
    /** Fim da fala em ms (última palavra + margem): onde o MediaItem é cortado. */
    val durationMs: Long? = null,
    val timings: String? = null,
    val updatedAt: Long = 0,
)

/** Um pedido de download por livro + voz: o intervalo de trechos/páginas pedido e o andamento. */
@Entity(tableName = "download_jobs", primaryKeys = ["bookId", "voice"])
data class DownloadJobEntity(
    val bookId: String,
    val voice: String,
    val plannerVersion: Int,
    val fromPage: Int,
    val toPage: Int,
    val fromChunk: Int,
    val toChunk: Int,
    val totalChunks: Int,
    val doneChunks: Int = 0,
    val state: JobState = JobState.QUEUED,
    /** Último motivo de falha/espera, para a tela mostrar (sem espaço, sem rede, trechos que falharam...). */
    val lastError: String? = null,
    val wifiOnly: Boolean = false,
    val chargingOnly: Boolean = false,
    val updatedAt: Long = 0,
)
