package com.lector.app.download

import com.lector.app.domain.BookIndex
import com.lector.app.domain.Chunk
import com.lector.app.domain.TTSResult
import com.lector.app.domain.TimingsCodec
import com.lector.app.domain.WordTiming
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

class BookDownloaderTest {
    @get:Rule val tmp = TemporaryFolder()

    private val voice = "pt-BR-AntonioNeural"
    private fun index(n: Int) = BookIndex(1, 1, List(n) { Chunk(it, 0, 0, it, "t$it") })
    private fun audioFor(text: String) = text.toByteArray()
    private fun result(text: String) = TTSResult(audioFor(text), listOf(WordTiming(text, 0.25f, 0.8f)))

    /** Porta fiel do que o Room faz: PENDING, ou FAILED com menos de 3 tentativas, em ordem de índice. */
    private class FakeStore(val toChunk: Int, preDone: Set<Int> = emptySet()) : DownloadStore {
        val status = ConcurrentHashMap<Int, String>()
        val attempts = ConcurrentHashMap<Int, Int>()
        val completed = ConcurrentHashMap<Int, Triple<File, Long?, String>>()

        init { for (i in 0..toChunk) status[i] = if (i in preDone) "DONE" else "PENDING" }

        @Synchronized override suspend fun next(afterChunk: Int): PendingChunk? =
            (afterChunk + 1..toChunk).firstOrNull { i ->
                val s = status[i]
                s == "PENDING" || (s == "FAILED" && (attempts[i] ?: 0) < BookDownloader.MAX_ATTEMPTS)
            }?.let { PendingChunk(it, attempts[it] ?: 0) }

        @Synchronized override suspend fun complete(chunkIndex: Int, file: File, bytes: Long, durationMs: Long?, timings: String) {
            status[chunkIndex] = "DONE"
            completed[chunkIndex] = Triple(file, durationMs, timings)
        }

        @Synchronized override suspend fun fail(chunkIndex: Int) {
            status[chunkIndex] = "FAILED"
            attempts[chunkIndex] = (attempts[chunkIndex] ?: 0) + 1
        }

        fun done() = status.filterValues { it == "DONE" }.keys.sorted()
    }

    private fun downloader(
        store: DownloadStore,
        synth: Synthesizer,
        concurrency: Int = 2,
        maxConsecutiveFailures: Int = 5,
    ) = BookDownloader(
        store, synth, File(tmp.root, "dl"),
        concurrency = concurrency, pauseBetweenMs = 0, maxConsecutiveFailures = maxConsecutiveFailures, backoffMs = { 0L },
    )

    @Test fun baixaTodosOsTrechosGravaOArquivoEGuardaOsTempos() = runBlocking {
        val store = FakeStore(5)
        val out = downloader(store, { text, _ -> result(text) }).run(index(6), voice, -1)

        assertEquals(BookDownloader.Outcome.Finished(6), out)
        assertEquals((0..5).toList(), store.done())
        val (file, durationMs, timings) = store.completed.getValue(3)
        assertEquals("3.mp3", file.name)
        assertArrayEquals(audioFor("t3"), file.readBytes())
        assertEquals(900L, durationMs) // 0,8 s + 0,10 s de margem
        assertEquals(listOf(WordTiming("t3", 0.25f, 0.8f)), TimingsCodec.decode(timings))
    }

    @Test fun retomadaNaoBaixaDeNovoOQueJaEstavaPronto() = runBlocking {
        val store = FakeStore(5, preDone = setOf(0, 1, 2))
        val asked = ConcurrentHashMap.newKeySet<String>()
        downloader(store, { text, _ -> asked.add(text); result(text) }).run(index(6), voice, -1)
        assertEquals(setOf("t3", "t4", "t5"), asked)
        assertEquals((0..5).toList(), store.done())
    }

    @Test fun falhaPontualEhTentadaDeNovoEDaCerto() = runBlocking {
        val store = FakeStore(4)
        val calls = AtomicInteger(0)
        val out = downloader(store, { text, _ ->
            if (text == "t2" && calls.incrementAndGet() == 1) error("falha passageira")
            result(text)
        }).run(index(5), voice, -1)

        assertEquals(BookDownloader.Outcome.Finished(5), out)
        assertEquals((0..4).toList(), store.done())
        assertEquals(1, store.attempts[2])
    }

    @Test fun falhaPermanenteSaiDaFilaDepoisDeTresTentativasEOsOutrosSeguem() = runBlocking {
        val store = FakeStore(4)
        val callsOn3 = AtomicInteger(0)
        val out = downloader(store, { text, _ ->
            if (text == "t3") { callsOn3.incrementAndGet(); error("trecho ruim") }
            result(text)
        }).run(index(5), voice, -1)

        assertTrue(out is BookDownloader.Outcome.Finished)
        assertEquals(listOf(0, 1, 2, 4), store.done())
        assertEquals("FAILED", store.status[3])
        assertEquals(BookDownloader.MAX_ATTEMPTS, store.attempts[3])
        assertEquals(BookDownloader.MAX_ATTEMPTS, callsOn3.get()) // não insiste além do limite
    }

    @Test fun redeCaidaParaCedoSemQueimarAsTentativasDoLivroTodo() = runBlocking {
        val store = FakeStore(99)
        val calls = AtomicInteger(0)
        val out = downloader(store, { _, _ -> calls.incrementAndGet(); error("sem rede") }, concurrency = 1, maxConsecutiveFailures = 5)
            .run(index(100), voice, -1)

        assertTrue(out is BookDownloader.Outcome.Aborted)
        assertEquals(5, calls.get())
        assertEquals(emptyList<Int>(), store.done())
        assertEquals(95, store.status.values.count { it == "PENDING" }) // o resto nem foi tocado
    }

    @Test fun cancelarNoMeioDeixaOsProntosEOsDemaisPendentesESemArquivoPela() = runBlocking {
        val store = FakeStore(5)
        val gate = CompletableDeferred<Unit>()
        val reached2 = CompletableDeferred<Unit>()
        val d = downloader(store, { text, _ ->
            if (text == "t2") { reached2.complete(Unit); gate.await() }
            result(text)
        }, concurrency = 1)

        val job = launch(Dispatchers.Default) { d.run(index(6), voice, -1) }
        withTimeout(5_000) { reached2.await() }
        job.cancelAndJoin()

        assertEquals(listOf(0, 1), store.done())
        assertEquals("PENDING", store.status[2])
        assertEquals(emptyList<String>(), File(tmp.root, "dl").listFiles()!!.filter { it.name.endsWith(".tmp") }.map { it.name })
    }

    @Test fun apagaArquivoTemporarioOrfaoDeUmaExecucaoAnterior() = runBlocking {
        val dir = File(tmp.root, "dl").apply { mkdirs() }
        val orfao = File(dir, "7.mp3.tmp").apply { writeText("metade") }
        val prontoDeAntes = File(dir, "0.mp3").apply { writeText("ok") }

        downloader(FakeStore(1), { text, _ -> result(text) }).run(index(2), voice, -1)

        assertTrue(!orfao.exists())
        assertTrue(prontoDeAntes.exists())
    }

    @Test fun nuncaDeixaArquivoTemporarioQuandoTerminaBem() = runBlocking {
        downloader(FakeStore(3), { text, _ -> result(text) }).run(index(4), voice, -1)
        val names = File(tmp.root, "dl").listFiles()!!.map { it.name }.sorted()
        assertEquals(listOf("0.mp3", "1.mp3", "2.mp3", "3.mp3"), names)
    }

    @Test fun duasRequisicoesAoMesmoTempoNoMaximoENenhumTrechoRepetido() = runBlocking {
        val store = FakeStore(9)
        val inFlight = AtomicInteger(0)
        val maxSeen = AtomicInteger(0)
        val perChunk = ConcurrentHashMap<String, AtomicInteger>()
        downloader(store, { text, _ ->
            perChunk.getOrPut(text) { AtomicInteger() }.incrementAndGet()
            val now = inFlight.incrementAndGet()
            maxSeen.accumulateAndGet(now) { a, b -> maxOf(a, b) }
            delay(20)
            inFlight.decrementAndGet()
            result(text)
        }, concurrency = 2).run(index(10), voice, -1)

        assertEquals(2, maxSeen.get())
        assertTrue(perChunk.values.all { it.get() == 1 })
        assertEquals((0..9).toList(), store.done())
    }

    @Test fun respeitaOIntervaloDoPedido() = runBlocking {
        // pedido de 2..3: o store só entrega até toChunk = 3 e começa depois de afterChunk = 1
        val store = FakeStore(3, preDone = setOf(0, 1))
        val asked = ConcurrentHashMap.newKeySet<String>()
        downloader(store, { text, _ -> asked.add(text); result(text) }).run(index(10), voice, afterChunk = 1)
        assertEquals(setOf("t2", "t3"), asked)
    }

    @Test fun informaProgressoDestaExecucao() = runBlocking {
        val seen = ConcurrentHashMap.newKeySet<Int>()
        downloader(FakeStore(3), { text, _ -> result(text) }, concurrency = 1)
            .run(index(4), voice, -1) { seen.add(it) }
        assertEquals(setOf(1, 2, 3, 4), seen)
    }
}
