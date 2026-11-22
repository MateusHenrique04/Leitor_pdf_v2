package com.lector.app.player

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.net.Uri
import android.os.IBinder
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.lector.app.data.BookRepository
import com.lector.app.data.LectorDatabase
import com.lector.app.data.audio.AudioDatabase
import com.lector.app.data.audio.ChunkStatus
import com.lector.app.domain.BookIndex
import com.lector.app.domain.CachePolicy
import com.lector.app.domain.CachedAudio
import com.lector.app.domain.Chunk
import com.lector.app.domain.NarrationState
import com.lector.app.domain.NarrationStatus
import com.lector.app.domain.TTSResult
import com.lector.app.domain.WordClock
import com.lector.app.domain.WordTiming
import com.lector.app.tts.EdgeHttpException
import com.lector.app.tts.EdgeTtsClient
import com.lector.app.tts.TtsProbe
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Motor da narração (Fase 6b): sintetiza o livro trecho a trecho (síntese on-line, sempre a +0%) e toca com
 * o ExoPlayer, um MediaItem por trecho, cortado em "fim da última palavra + 0,10 s" para não ter pausa entre
 * trechos. A velocidade é do player ([setSpeed]); como os tempos das palavras são a +0%, a posição do player é
 * comparada direto com eles (NÃO dividir pela velocidade).
 *
 * Vive no processo (singleton), não na tela. Tudo roda na main thread (o ExoPlayer exige); a rede e a
 * gravação do MP3 saem para outra thread. Na 6c ele passa a morar num serviço de mídia (tela apagada).
 */
class NarrationEngine private constructor(private val appContext: Context) {

    companion object {
        const val DEFAULT_VOICE = com.lector.app.domain.Voices.DEFAULT_ID
        /** Quantos trechos sintetizar à frente do que está tocando. */
        const val AHEAD = 2
        /** Quantos trechos já tocados manter na playlist (para "Anterior" sem sintetizar de novo). */
        const val KEEP_BEHIND = 2
        const val MAX_ATTEMPTS = 3
        /** "Anterior" depois de tantos ms volta ao início do trecho atual em vez de ir ao anterior. */
        const val RESTART_THRESHOLD_MS = 3000L
        private const val TICK_MS = 40L

        @Volatile private var instance: NarrationEngine? = null

        /** Chamar da main thread (cria o ExoPlayer). */
        fun get(context: Context): NarrationEngine =
            instance ?: synchronized(this) {
                instance ?: NarrationEngine(context.applicationContext).also { instance = it }
            }

        /** O motor, se já foi criado (não cria). */
        fun peek(): NarrationEngine? = instance
    }

    private class Session(
        val bookId: String,
        val title: String,
        val index: BookIndex,
        val voice: String,
        val generation: Int,
    )

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val tts = EdgeTtsClient()
    private val audioDao by lazy { AudioDatabase.get(appContext).audioDao() }
    private val repo by lazy { BookRepository(appContext, LectorDatabase.get(appContext).bookDao()) }
    private val dir = File(appContext.cacheDir, "tts-live").also { it.deleteRecursively(); it.mkdirs() }

    private val player: ExoPlayer = ExoPlayer.Builder(appContext).build().apply {
        setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH)
                .build(),
            /* handleAudioFocus = */ true,
        )
        setHandleAudioBecomingNoisy(true)
        setWakeMode(C.WAKE_MODE_NETWORK) // CPU e Wi-Fi acordados enquanto toca (a síntese usa a rede)
    }

    /** O player que o serviço de mídia (NarrationService) expõe como MediaSession. */
    val sessionPlayer: Player get() = player

    private val _state = MutableStateFlow(NarrationState())
    val state: StateFlow<NarrationState> = _state.asStateFlow()

    // Estado da sessão (só mexer na main thread).
    private var session: Session? = null
    private var generation = 0
    private var pipeline: Job? = null
    private var ticker: Job? = null
    private val currentChunk = MutableStateFlow(0)
    /** MP3 temporários da sessão (tts-live), apagados ao passar. Os do cache baixado NUNCA entram aqui. */
    private val liveFiles = HashMap<Int, File>()
    private val fromCacheByChunk = HashMap<Int, Boolean>()
    private val timingsByChunk = HashMap<Int, List<WordTiming>>()
    private var pipelineDone = false
    private var pipelineError: String? = null
    private var playerFailure: String? = null

    init {
        player.addListener(object : Player.Listener {
            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
                mediaItem?.mediaId?.toIntOrNull()?.let(::onChunkStarted)
            }

            override fun onPlaybackStateChanged(playbackState: Int) = refreshStatus()

            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) = refreshStatus()

            override fun onIsPlayingChanged(isPlaying: Boolean) {
                refreshStatus()
                if (isPlaying) startTicker()
            }

            override fun onPlayerError(error: PlaybackException) {
                playerFailure = "Erro no player: ${error.errorCodeName}"
                refreshStatus()
            }
        })
    }

    // ---------------- API pública (main thread) ----------------

    /** Começa (ou recomeça) a narrar [index] a partir de [from]. */
    fun play(bookId: String, title: String, index: BookIndex, from: Chunk, voice: String = DEFAULT_VOICE) {
        if (from.index !in index.chunks.indices) return
        begin(bookId, title, index, from.index, voice)
    }

    fun pause() {
        player.playWhenReady = false
    }

    /** Continua; depois de erro ou do fim do livro, recomeça do trecho atual. */
    fun resume() {
        val s = session ?: return
        val st = _state.value
        if (st.status == NarrationStatus.ERROR || st.status == NarrationStatus.ENDED) {
            val c = st.chunk ?: return
            begin(s.bookId, s.title, s.index, c.index, s.voice)
        } else {
            player.playWhenReady = true
        }
    }

    fun next() {
        val s = session ?: return
        val cur = _state.value.chunk ?: return
        val target = cur.index + 1
        if (target >= s.index.chunks.size) return
        jumpTo(s, target)
    }

    fun previous() {
        val s = session ?: return
        val cur = _state.value.chunk ?: return
        if (cur.index == 0 || player.currentPosition > RESTART_THRESHOLD_MS) {
            player.seekTo(0L)
            _state.update { it.copy(wordIndex = -1) }
            player.playWhenReady = true
        } else {
            jumpTo(s, cur.index - 1)
        }
    }

    /** Troca a voz da narração em andamento: recomeça do trecho atual com a voz nova (respeitando a pausa). */
    fun setVoice(voice: String) {
        val s = session ?: return
        if (s.voice == voice) return
        val chunk = _state.value.chunk ?: return
        val wasPlaying = player.playWhenReady
        begin(s.bookId, s.title, s.index, chunk.index, voice)
        if (!wasPlaying) player.playWhenReady = false
    }

    fun setSpeed(speed: Float) {
        player.setPlaybackParameters(PlaybackParameters(speed))
        _state.update { it.copy(speed = speed) }
    }

    fun stop() {
        pipeline?.cancel()
        resetPlayback()
        _state.update { NarrationState(speed = it.speed) } // o serviço observa o IDLE e se encerra
        releaseService()
    }

    fun stopIfBook(bookId: String) {
        if (_state.value.bookId == bookId) stop()
    }

    // ---------------- sessão ----------------

    private fun begin(bookId: String, title: String, index: BookIndex, startChunk: Int, voice: String) {
        pipeline?.cancel()
        resetPlayback()
        val s = Session(bookId, title, index, voice, ++generation)
        session = s
        currentChunk.value = startChunk
        _state.update {
            it.copy(
                bookId = bookId,
                status = NarrationStatus.LOADING,
                chunk = index.chunks[startChunk],
                timings = emptyList(),
                wordIndex = -1,
                error = null,
            )
        }
        player.playWhenReady = true
        ensureService() // depois de o estado sair de IDLE (o serviço se encerra se vir IDLE)
        pipeline = scope.launch { runPipeline(s, startChunk) }
    }

    // ---------------- serviço de mídia (6c) ----------------

    private var serviceConnection: ServiceConnection? = null

    /** Liga ao NarrationService (cria o serviço, que expõe a sessão e a notificação). */
    private fun ensureService() {
        if (serviceConnection != null) return
        val connection = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName?, service: IBinder?) = Unit
            override fun onServiceDisconnected(name: ComponentName?) = Unit
        }
        val intent = Intent(appContext, NarrationService::class.java)
            .setAction("androidx.media3.session.MediaSessionService")
        if (appContext.bindService(intent, connection, Context.BIND_AUTO_CREATE)) serviceConnection = connection
    }

    private fun releaseService() {
        serviceConnection?.let { runCatching { appContext.unbindService(it) } }
        serviceConnection = null
    }

    private fun resetPlayback() {
        session = null
        ticker?.cancel()
        player.stop()
        player.clearMediaItems()
        liveFiles.clear()
        fromCacheByChunk.clear()
        timingsByChunk.clear()
        dir.listFiles()?.forEach { it.delete() }
        pipelineDone = false
        pipelineError = null
        playerFailure = null
    }

    private fun jumpTo(s: Session, target: Int) {
        val pos = positionOf(target)
        if (pos >= 0) {
            player.seekTo(pos, 0L)
            _state.update { it.copy(wordIndex = -1) }
            player.playWhenReady = true
        } else {
            begin(s.bookId, s.title, s.index, target, s.voice)
        }
    }

    /** Posição do trecho na playlist do player (-1 se não está lá). */
    private fun positionOf(chunkIndex: Int): Int {
        val id = chunkIndex.toString()
        for (i in 0 until player.mediaItemCount) if (player.getMediaItemAt(i).mediaId == id) return i
        return -1
    }

    // ---------------- síntese ----------------

    private suspend fun runPipeline(s: Session, start: Int) {
        val chunks = s.index.chunks
        var next = start
        while (next < chunks.size) {
            currentChunk.first { next - it <= AHEAD } // não sintetiza longe demais do que está tocando
            val chunk = chunks[next]
            // Fase 8.4: se o trecho já foi baixado (mesma voz e versão do planner), toca do arquivo, sem internet.
            val cached = withContext(Dispatchers.IO) { lookupCache(s, chunk.index) }
            val audio = if (cached != null) {
                ChunkAudio(File(cached.path), cached.timings, cached.endMs, temporary = false)
            } else {
                val result = synthesize(chunk.text, s.voice)
                if (result == null) { // falhou depois de todas as tentativas
                    refreshStatus()
                    return
                }
                val file = withContext(Dispatchers.IO) {
                    File(dir, "g${s.generation}-c${chunk.index}.mp3").also { it.writeBytes(result.audioBytes) }
                }
                ChunkAudio(file, result.timings, result.speechEndMs, temporary = true)
            }
            enqueue(chunk, audio)
            next++
        }
        pipelineDone = true
        refreshStatus()
    }

    private suspend fun synthesize(text: String, voice: String): TTSResult? {
        var last: Throwable? = null
        repeat(MAX_ATTEMPTS) { attempt ->
            try {
                return withContext(Dispatchers.IO) { tts.synthesize(text, voice, 0) }
            } catch (e: CancellationException) {
                throw e
            } catch (t: Throwable) {
                last = t
                delay(800L * (attempt + 1))
            }
        }
        pipelineError = when (val t = last) {
            is EdgeHttpException -> TtsProbe.describeHttpError(t)
            else -> "Falha na síntese: ${t?.javaClass?.simpleName}: ${t?.message}"
        }
        return null
    }

    private class ChunkAudio(val file: File, val timings: List<WordTiming>, val endMs: Long?, val temporary: Boolean)

    /** Trecho baixado e utilizável (ver [CachePolicy]); null se não há, ou se o arquivo sumiu. */
    private suspend fun lookupCache(s: Session, chunkIndex: Int): CachedAudio? = runCatching {
        val row = audioDao.getChunk(s.bookId, s.voice, s.index.plannerVersion, chunkIndex)
        CachePolicy.resolve(row?.status == ChunkStatus.DONE, row?.filePath, row?.durationMs, row?.timings) { File(it).isFile }
    }.getOrNull()

    private fun enqueue(chunk: Chunk, audio: ChunkAudio) {
        val file = audio.file
        if (audio.temporary) liveFiles[chunk.index] = file
        fromCacheByChunk[chunk.index] = !audio.temporary
        timingsByChunk[chunk.index] = audio.timings // antes do addMediaItem: o listener já vai precisar deles
        val clip = MediaItem.ClippingConfiguration.Builder()
        audio.endMs?.let { clip.setEndPositionMs(it) }
        val item = MediaItem.Builder()
            .setMediaId(chunk.index.toString())
            .setUri(Uri.fromFile(file))
            .setClippingConfiguration(clip.build())
            .setMediaMetadata(
                MediaMetadata.Builder()
                    .setTitle(session?.title)
                    .setArtist("Página ${chunk.pageIndex + 1}")
                    .build(),
            )
            .build()
        val wasEnded = player.playbackState == Player.STATE_ENDED
        player.addMediaItem(item)
        if (player.playbackState == Player.STATE_IDLE) {
            player.prepare()
        } else if (wasEnded) {
            player.seekTo(player.mediaItemCount - 1, 0L) // o player tinha acabado esperando este trecho
        }
        refreshStatus()
    }

    // ---------------- player -> estado ----------------

    private fun onChunkStarted(chunkIndex: Int) {
        val s = session ?: return
        val chunk = s.index.chunks.getOrNull(chunkIndex) ?: return
        currentChunk.value = chunkIndex
        _state.update {
            it.copy(
                chunk = chunk,
                timings = timingsByChunk[chunkIndex].orEmpty(),
                wordIndex = -1,
                fromCache = fromCacheByChunk[chunkIndex] == true,
            )
        }
        prune(chunkIndex)
        saveProgress(s.bookId, chunk)
    }

    /** Tira da playlist (e apaga o MP3 de) o que já passou há mais de [KEEP_BEHIND] trechos. */
    private fun prune(current: Int) {
        while (player.mediaItemCount > 0) {
            val first = player.getMediaItemAt(0).mediaId.toIntOrNull() ?: break
            if (first >= current - KEEP_BEHIND) break
            player.removeMediaItem(0)
            liveFiles.remove(first)?.delete() // só os temporários; o áudio baixado fica
            fromCacheByChunk.remove(first)
            timingsByChunk.remove(first)
        }
    }

    /** Fase 7: guarda onde a narração está (página + índice do trecho na página), mesmo com a tela fechada. */
    private fun saveProgress(bookId: String, chunk: Chunk) {
        scope.launch(Dispatchers.IO) {
            runCatching { repo.savePosition(bookId, chunk.pageIndex, chunk.indexInPage) }
        }
    }

    private fun refreshStatus() {
        if (session == null) return
        val ended = player.playbackState == Player.STATE_ENDED
        val starved = ended || player.mediaItemCount == 0
        val failure = playerFailure
        val synthError = pipelineError
        val (status, error) = when {
            failure != null -> NarrationStatus.ERROR to failure
            synthError != null && starved -> NarrationStatus.ERROR to synthError
            pipelineDone && ended -> NarrationStatus.ENDED to null
            !player.playWhenReady -> NarrationStatus.PAUSED to null
            player.isPlaying -> NarrationStatus.PLAYING to null
            else -> NarrationStatus.LOADING to null
        }
        _state.update { if (it.status == status && it.error == error) it else it.copy(status = status, error = error) }
    }

    /** Enquanto toca, acompanha a palavra falada (a cada 40 ms; só emite quando a palavra muda). */
    private fun startTicker() {
        if (ticker?.isActive == true) return
        ticker = scope.launch {
            while (isActive && player.isPlaying) {
                val timings = _state.value.timings
                if (timings.isNotEmpty()) {
                    val word = WordClock.wordIndexAt(timings, player.currentPosition / 1000f)
                    _state.update { if (it.wordIndex == word) it else it.copy(wordIndex = word) }
                }
                delay(TICK_MS)
            }
        }
    }
}
