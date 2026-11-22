package com.lector.app.data.audio

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Roda no celular (Run > AudioDaoTest). Banco em memória: nada fica salvo. */
class AudioDaoTest {
    private lateinit var db: AudioDatabase
    private lateinit var dao: AudioDao

    private val book = "livro-a"
    private val v1 = "pt-BR-FranciscaNeural"
    private val v2 = "pt-BR-AntonioNeural"
    private val ver = 1

    @Before fun setUp() {
        val ctx = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(ctx, AudioDatabase::class.java).allowMainThreadQueries().build()
        dao = db.audioDao()
    }

    @After fun tearDown() = db.close()

    private fun rows(voice: String, range: IntRange, bookId: String = book) =
        range.map { AudioChunkEntity(bookId = bookId, voice = voice, plannerVersion = ver, chunkIndex = it) }

    private fun job(voice: String, from: Int, to: Int, bookId: String = book) = DownloadJobEntity(
        bookId = bookId, voice = voice, plannerVersion = ver, fromPage = 0, toPage = 9,
        fromChunk = from, toChunk = to, totalChunks = to - from + 1, updatedAt = 1L,
    )

    private suspend fun done(voice: String, idx: Int, bytes: Long = 1000, bookId: String = book) =
        dao.completeChunk(bookId, voice, ver, idx, "/f/$idx.mp3", bytes, 5000L, "1.0\t2.0\tx\n", 2L)

    // ---------------- unicidade e ordenação ----------------

    @Test fun chaveRepetidaEhIgnoradaENaoApagaOQueJaFoiBaixado() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4))
        done(v1, 2)
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4)) // pedir de novo
        assertEquals(ChunkStatus.DONE, dao.getChunk(book, v1, ver, 2)?.status)
        assertEquals(1, dao.countDone(book, v1, ver, 0, 4))
    }

    @Test fun proximoADownloadEOMenorIndicePendente() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4).shuffled())
        assertEquals(0, dao.nextToDownload(book, v1, ver, -1, 4, 3)?.chunkIndex)
    }

    @Test fun respeitaOIntervaloPedido() = runBlocking {
        dao.startJob(job(v1, 3, 5), rows(v1, 0..9))
        assertEquals(3, dao.nextToDownload(book, v1, ver, 2, 5, 3)?.chunkIndex)
        done(v1, 3); done(v1, 4); done(v1, 5)
        assertNull(dao.nextToDownload(book, v1, ver, 2, 5, 3))
    }

    @Test fun afterChunkPulaOsAnterioresParaDoisDownloadsNaoPegaremOMesmo() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4))
        assertEquals(2, dao.nextToDownload(book, v1, ver, 1, 4, 3)?.chunkIndex)
        assertNull(dao.nextToDownload(book, v1, ver, 4, 4, 3))
    }

    @Test fun pedidoGuardaMotivoERestricoes() = runBlocking {
        dao.startJob(job(v1, 0, 0).copy(wifiOnly = true, chargingOnly = true), rows(v1, 0..0))
        dao.setJobResult(book, v1, JobState.FAILED, "Sem espaço", 5L)
        val j = dao.getJob(book, v1)!!
        assertEquals(JobState.FAILED, j.state)
        assertEquals("Sem espaço", j.lastError)
        assertTrue(j.wifiOnly && j.chargingOnly)
        dao.setJobResult(book, v1, JobState.QUEUED, null, 6L)
        assertNull(dao.getJob(book, v1)?.lastError)
    }

    // ---------------- retomada e falhas ----------------

    @Test fun retomadaPulaOsProntosEContinuaDoPrimeiroPendente() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4))
        done(v1, 0); done(v1, 1)
        assertEquals(2, dao.nextToDownload(book, v1, ver, -1, 4, 3)?.chunkIndex)
    }

    @Test fun falhaContaTentativaEDepoisDeTresSaiDaFila() = runBlocking {
        dao.startJob(job(v1, 0, 1), rows(v1, 0..1))
        repeat(2) { dao.markFailed(book, v1, ver, 0, 3L) }
        assertEquals(0, dao.nextToDownload(book, v1, ver, -1, 1, 3)?.chunkIndex) // 2 falhas: ainda tenta
        dao.markFailed(book, v1, ver, 0, 3L)
        assertEquals(1, dao.nextToDownload(book, v1, ver, -1, 1, 3)?.chunkIndex) // 3 falhas: pula para o 1
        assertEquals(1, dao.countFailed(book, v1, ver, 0, 1, 3))
    }

    @Test fun resetFailedDevolveOsFalhosParaPendente() = runBlocking {
        dao.startJob(job(v1, 0, 0), rows(v1, 0..0))
        repeat(3) { dao.markFailed(book, v1, ver, 0, 3L) }
        assertNull(dao.nextToDownload(book, v1, ver, -1, 0, 3))
        dao.resetFailed(book, v1, ver, 4L)
        val c = dao.nextToDownload(book, v1, ver, -1, 0, 3)
        assertNotNull(c)
        assertEquals(0, c!!.attempts)
        assertEquals(ChunkStatus.PENDING, c.status)
    }

    // ---------------- andamento, espaço, vozes ----------------

    @Test fun completeChunkAtualizaOAndamentoDoPedido() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4))
        assertEquals(0, dao.getJob(book, v1)?.doneChunks)
        done(v1, 0); done(v1, 1)
        assertEquals(2, dao.getJob(book, v1)?.doneChunks)
        assertEquals(2, dao.observeJob(book, v1).first()?.doneChunks)
    }

    @Test fun andamentoSoContaTrechosDoIntervaloDoPedido() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..9))
        done(v1, 7) // fora do intervalo do pedido
        done(v1, 1)
        assertEquals(1, dao.getJob(book, v1)?.doneChunks)
    }

    @Test fun guardaOsDadosDoTrechoPronto() = runBlocking {
        dao.startJob(job(v1, 0, 0), rows(v1, 0..0))
        done(v1, 0, bytes = 4321)
        val c = dao.getChunk(book, v1, ver, 0)!!
        assertEquals("/f/0.mp3", c.filePath)
        assertEquals(4321L, c.fileBytes)
        assertEquals(5000L, c.durationMs)
        assertEquals("1.0\t2.0\tx\n", c.timings)
    }

    @Test fun somaOEspacoPorVozOuDeTodas() = runBlocking {
        dao.startJob(job(v1, 0, 1), rows(v1, 0..1))
        dao.startJob(job(v2, 0, 1), rows(v2, 0..1))
        done(v1, 0, 1000); done(v1, 1, 500); done(v2, 0, 200)
        assertEquals(1500L, dao.totalBytes(book, v1))
        assertEquals(1700L, dao.totalBytes(book, null))
    }

    @Test fun listaOsIndicesProntosEAsVozesComAudio() = runBlocking {
        dao.startJob(job(v1, 0, 4), rows(v1, 0..4))
        done(v1, 3); done(v1, 1)
        assertEquals(listOf(1, 3), dao.observeDoneIndexes(book, v1, ver).first())
        assertEquals(listOf(v1), dao.observeVoicesWithAudio(book).first())
    }

    @Test fun listaOsLivrosQueTemAudioBaixado() = runBlocking {
        dao.startJob(job(v1, 0, 1), rows(v1, 0..1))
        dao.startJob(job(v1, 0, 1, "livro-b"), rows(v1, 0..1, "livro-b")) // sem nada pronto
        done(v1, 0)
        assertEquals(listOf(book), dao.observeBookIdsWithAudio().first())
    }

    // ---------------- apagar ----------------

    @Test fun apagarUmaVozNaoMexeNaOutraNemEmOutroLivro() = runBlocking {
        dao.startJob(job(v1, 0, 1), rows(v1, 0..1))
        dao.startJob(job(v2, 0, 1), rows(v2, 0..1))
        dao.startJob(job(v1, 0, 1, "livro-b"), rows(v1, 0..1, "livro-b"))
        done(v1, 0); done(v2, 0); done(v1, 0, bookId = "livro-b")

        dao.deleteVoiceAudio(book, v1)

        assertNull(dao.getChunk(book, v1, ver, 0))
        assertNull(dao.getJob(book, v1))
        assertEquals(ChunkStatus.DONE, dao.getChunk(book, v2, ver, 0)?.status)
        assertEquals(ChunkStatus.DONE, dao.getChunk("livro-b", v1, ver, 0)?.status)
    }

    @Test fun apagarOLivroRemoveTudoDele() = runBlocking {
        dao.startJob(job(v1, 0, 1), rows(v1, 0..1))
        dao.startJob(job(v2, 0, 1), rows(v2, 0..1))
        dao.startJob(job(v1, 0, 1, "livro-b"), rows(v1, 0..1, "livro-b"))
        done(v1, 0); done(v2, 0)

        dao.deleteBookAudio(book)

        assertTrue(dao.filePaths(book, null).isEmpty())
        assertTrue(dao.observeJobsOfBook(book).first().isEmpty())
        assertNotNull(dao.getJob("livro-b", v1))
    }

    @Test fun listaOsCaminhosDosArquivosParaApagar() = runBlocking {
        dao.startJob(job(v1, 0, 2), rows(v1, 0..2))
        done(v1, 0); done(v1, 2)
        assertEquals(setOf("/f/0.mp3", "/f/2.mp3"), dao.filePaths(book, v1).toSet())
    }

    @Test fun estadoDoPedido() = runBlocking {
        dao.startJob(job(v1, 0, 0), rows(v1, 0..0))
        assertEquals(JobState.QUEUED, dao.getJob(book, v1)?.state)
        dao.setJobState(book, v1, JobState.PAUSED, 9L)
        assertEquals(JobState.PAUSED, dao.getJob(book, v1)?.state)
    }
}
