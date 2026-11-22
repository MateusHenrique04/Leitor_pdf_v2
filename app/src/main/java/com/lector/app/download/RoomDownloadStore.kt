package com.lector.app.download

import com.lector.app.data.audio.AudioDao
import java.io.File

/** [DownloadStore] sobre o Room, amarrado a um livro, uma voz e um intervalo. */
class RoomDownloadStore(
    private val dao: AudioDao,
    private val bookId: String,
    private val voice: String,
    private val version: Int,
    private val toChunk: Int,
) : DownloadStore {

    override suspend fun next(afterChunk: Int): PendingChunk? =
        dao.nextToDownload(bookId, voice, version, afterChunk, toChunk, BookDownloader.MAX_ATTEMPTS)
            ?.let { PendingChunk(it.chunkIndex, it.attempts) }

    override suspend fun complete(chunkIndex: Int, file: File, bytes: Long, durationMs: Long?, timings: String) =
        dao.completeChunk(bookId, voice, version, chunkIndex, file.absolutePath, bytes, durationMs, timings, System.currentTimeMillis())

    override suspend fun fail(chunkIndex: Int) =
        dao.markFailed(bookId, voice, version, chunkIndex, System.currentTimeMillis())
}
