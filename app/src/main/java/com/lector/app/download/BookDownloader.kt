package com.lector.app.download

import com.lector.app.domain.BookIndex
import com.lector.app.domain.TTSResult
import com.lector.app.domain.TimingsCodec
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Um trecho ainda por baixar e quantas vezes já falhou. */
data class PendingChunk(val chunkIndex: Int, val attempts: Int)

/** Onde o andamento é guardado (no app, o Room; nos testes, uma lista em memória). Já amarrado a um livro e voz. */
interface DownloadStore {
    /** Próximo trecho depois de [afterChunk] (PENDING, ou FAILED com tentativas sobrando); null se acabou. */
    suspend fun next(afterChunk: Int): PendingChunk?
    suspend fun complete(chunkIndex: Int, file: File, bytes: Long, durationMs: Long?, timings: String)
    suspend fun fail(chunkIndex: Int)
}

fun interface Synthesizer {
    suspend fun synthesize(text: String, voice: String): TTSResult
}

/**
 * Baixa a narração de um intervalo de trechos (Fase 8.3). Lógica pura, sem Android (testável no PC).
 *
 * - Até [concurrency] trechos ao mesmo tempo, cada um pegando o próximo índice (ninguém repete trecho).
 * - Escrita atômica: grava `N.mp3.tmp` e só então renomeia para `N.mp3`; sobras `.tmp` de execuções
 *   interrompidas são apagadas ao começar.
 * - Falha de um trecho: conta a tentativa, espera (backoff) e ele volta numa nova passada, até o limite de
 *   tentativas do [DownloadStore]; depois fica FAILED e o resto segue.
 * - Falhas seguidas demais (rede caiu, servidor recusou): para com [Outcome.Aborted], sem queimar as tentativas
 *   do livro inteiro; quem chamou reagenda.
 * - Cancelar é cancelar a coroutine: responde entre trechos e dentro da chamada de rede.
 */
class BookDownloader(
    private val store: DownloadStore,
    private val synthesizer: Synthesizer,
    private val dir: File,
    private val concurrency: Int = DEFAULT_CONCURRENCY,
    private val pauseBetweenMs: Long = 150L,
    private val maxConsecutiveFailures: Int = 5,
    private val backoffMs: (attempts: Int) -> Long = { attempts -> 1000L shl attempts.coerceIn(0, 4) },
) {
    sealed interface Outcome {
        /** Não há mais nada a baixar (pode haver trechos FAILED sem tentativas sobrando). */
        data class Finished(val downloaded: Int) : Outcome

        /** Parou por falhas seguidas demais. */
        data class Aborted(val downloaded: Int, val cause: Throwable) : Outcome
    }

    /** [afterChunk]: use `fromChunk - 1` do pedido. [onChunkDone] recebe quantos já foram baixados NESTA execução. */
    suspend fun run(
        index: BookIndex,
        voice: String,
        afterChunk: Int,
        onChunkDone: suspend (downloadedInThisRun: Int) -> Unit = {},
    ): Outcome {
        dir.mkdirs()
        dir.listFiles { f -> f.name.endsWith(TMP) }?.forEach { it.delete() }
        var downloaded = 0
        var passes = 0
        while (passes < MAX_PASSES && store.next(afterChunk) != null) {
            passes++
            val base = downloaded
            val (n, error) = pass(index, voice, afterChunk) { onChunkDone(base + it) }
            downloaded += n
            if (error != null) return Outcome.Aborted(downloaded, error)
            if (store.next(afterChunk) != null) delay(backoffMs(passes)) // sobraram falhas: espera antes de tentar de novo
        }
        return Outcome.Finished(downloaded)
    }

    private suspend fun pass(
        index: BookIndex,
        voice: String,
        afterStart: Int,
        onDone: suspend (Int) -> Unit,
    ): Pair<Int, Throwable?> = coroutineScope {
        val mutex = Mutex()
        var cursor = afterStart
        val done = AtomicInteger(0)
        val consecutive = AtomicInteger(0)
        val abort = AtomicReference<Throwable?>(null)

        val workers = List(concurrency.coerceAtLeast(1)) {
            launch {
                while (isActive && abort.get() == null) {
                    val row = mutex.withLock { store.next(cursor)?.also { cursor = it.chunkIndex } } ?: break
                    val chunk = index.chunks.getOrNull(row.chunkIndex)
                    if (chunk == null) {
                        store.fail(row.chunkIndex)
                        continue
                    }
                    try {
                        val result = synthesizer.synthesize(chunk.text, voice)
                        val file = writeAtomically(row.chunkIndex, result.audioBytes)
                        store.complete(row.chunkIndex, file, file.length(), result.speechEndMs, TimingsCodec.encode(result.timings))
                        consecutive.set(0)
                        onDone(done.incrementAndGet())
                    } catch (e: CancellationException) {
                        throw e
                    } catch (t: Throwable) {
                        store.fail(row.chunkIndex)
                        if (consecutive.incrementAndGet() >= maxConsecutiveFailures) {
                            abort.compareAndSet(null, t)
                            break
                        }
                        delay(backoffMs(row.attempts))
                    }
                    if (pauseBetweenMs > 0) delay(pauseBetweenMs)
                }
            }
        }
        workers.joinAll()
        done.get() to abort.get()
    }

    private suspend fun writeAtomically(chunkIndex: Int, bytes: ByteArray): File = withContext(Dispatchers.IO) {
        val target = File(dir, "$chunkIndex.mp3")
        val tmp = File(dir, "$chunkIndex.mp3$TMP")
        tmp.writeBytes(bytes)
        if (!tmp.renameTo(target)) {
            target.delete()
            if (!tmp.renameTo(target)) {
                tmp.delete()
                throw IOException("Não consegui gravar ${target.name}")
            }
        }
        target
    }

    companion object {
        const val DEFAULT_CONCURRENCY = 2
        const val MAX_ATTEMPTS = 3
        private const val TMP = ".tmp"
        private const val MAX_PASSES = 10
    }
}
