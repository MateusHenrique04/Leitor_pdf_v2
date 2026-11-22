package com.lector.app.ui.reader

import android.app.Application
import android.os.SystemClock
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.lector.app.data.BookRepository
import com.lector.app.data.LectorDatabase
import com.lector.app.data.LectorPrefs
import com.lector.app.data.BookIndexStore
import com.lector.app.domain.BookIndex
import com.lector.app.domain.BookIndexer
import com.lector.app.domain.ChunkPlanner
import com.lector.app.domain.Highlight
import com.lector.app.domain.HighlightBuilder
import com.lector.app.domain.NarrationState
import com.lector.app.domain.NarrationStatus
import com.lector.app.player.NarrationEngine
import com.lector.app.domain.PageNavigator
import com.lector.app.domain.PageWord
import com.lector.app.domain.SyncCursor
import com.lector.app.domain.SyncedWord
import com.lector.app.domain.WordSyncEngine
import com.lector.app.domain.PageSize
import com.lector.app.pdf.PdfEngine
import com.lector.app.pdf.PdfPageRenderer
import com.lector.app.pdf.TextProbe
import com.lector.app.domain.SizedLruCache
import com.lector.app.domain.TextCleaner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.roundToInt

sealed interface ReaderUiState {
    data object Loading : ReaderUiState
    data class Error(val message: String) : ReaderUiState
    data class Ready(
        val title: String,
        val totalPages: Int,
        val page: Int,
        val pageSize: PageSize,
    ) : ReaderUiState
}

/** Estado do índice de narração (Fase 6a). */
sealed interface IndexState {
    data object Idle : IndexState
    data class Building(val donePages: Int, val totalPages: Int) : IndexState
    data class Ready(val index: BookIndex, val fromCache: Boolean, val buildMs: Long) : IndexState
    data object NoText : IndexState
    data class Failed(val message: String) : IndexState
}

/** Imagem de uma página renderizada na escala [pixelsPerPoint] (px por ponto PDF). */
data class RenderedPage(val page: Int, val pixelsPerPoint: Float, val image: ImageBitmap)

private data class RenderKey(val page: Int, val scaleKey: Int)

class ReaderViewModel(app: Application, private val bookId: String) : AndroidViewModel(app) {
    private val repo = BookRepository(app, LectorDatabase.get(app).bookDao())
    private val prefs = LectorPrefs(app)

    private val _state = MutableStateFlow<ReaderUiState>(ReaderUiState.Loading)
    val state: StateFlow<ReaderUiState> = _state.asStateFlow()

    private val _rendered = MutableStateFlow<RenderedPage?>(null)
    val rendered: StateFlow<RenderedPage?> = _rendered.asStateFlow()

    private var pdf: PdfPageRenderer? = null
    private var title = ""
    private var bookUri: String? = null
    private var total = 0
    private var pageJob: Job? = null
    private var renderJob: Job? = null

    // Cache pequeno (limitado por pixels) para a virada de página ficar instantânea.
    private val cache = SizedLruCache<RenderKey, Bitmap>(CACHE_MAX_PIXELS) { it.width.toLong() * it.height }

    init {
        viewModelScope.launch { open() }
    }

    private suspend fun open() {
        val book = repo.getBook(bookId)
        if (book == null) {
            _state.value = ReaderUiState.Error("Livro não encontrado na biblioteca.")
            return
        }
        val renderer = try {
            withContext(Dispatchers.IO) { PdfPageRenderer.open(getApplication(), Uri.parse(book.uri)) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            _state.value = ReaderUiState.Error(
                "Não consegui abrir este PDF. Se você moveu ou apagou o arquivo, remova-o da biblioteca e adicione de novo."
            )
            return
        }
        pdf = renderer
        title = book.title
        bookUri = book.uri
        total = renderer.pageCount
        repo.touch(bookId)
        showPage(PageNavigator.clamp(book.lastPage, total), save = false)
        startIndexing()
        startNarrationWatcher()
        viewModelScope.launch { // velocidade guardada (só se não há narração em andamento)
            val saved = prefs.speed.first()
            if (narrationEngine.state.value.status == NarrationStatus.IDLE) narrationEngine.setSpeed(saved)
        }
    }

    // --- Fase 6a: índice de narração do livro inteiro (feito uma vez e guardado em arquivo). ---
    private val indexStore by lazy { BookIndexStore(File(getApplication<Application>().filesDir, "index")) }
    private var indexJob: Job? = null
    private val _index = MutableStateFlow<IndexState>(IndexState.Idle)
    val indexState: StateFlow<IndexState> = _index.asStateFlow()

    fun retryIndex() = startIndexing()

    private fun startIndexing() {
        if (indexJob?.isActive == true) return
        val pages = total
        indexJob = viewModelScope.launch {
            _index.value = IndexState.Building(0, pages)
            try {
                val t0 = System.nanoTime()
                val cached = withContext(Dispatchers.IO) { indexStore.load(bookId, pages) }
                if (cached != null) {
                    _index.value = readyOrNoText(cached, fromCache = true, ms = 0)
                    return@launch
                }
                val engine = getEngine()
                val built = withContext(Dispatchers.IO) {
                    BookIndexer.build(
                        pageCount = pages,
                        extract = { engine.extractPage(it, useCache = false).raw },
                        onProgress = { done, all -> _index.value = IndexState.Building(done, all) },
                    ).also { indexStore.save(bookId, it) }
                }
                _index.value = readyOrNoText(built, fromCache = false, ms = (System.nanoTime() - t0) / 1_000_000)
            } catch (e: CancellationException) {
                throw e
            } catch (t: Throwable) {
                _index.value = IndexState.Failed("${t.javaClass.simpleName}: ${t.message}")
            }
        }
    }

    private fun readyOrNoText(index: BookIndex, fromCache: Boolean, ms: Long): IndexState =
        if (index.isEmpty) IndexState.NoText else IndexState.Ready(index, fromCache, ms)

    /** Última navegação feita pelo usuário (botões, deslize, "ir para"): a narração espera um pouco antes de puxar a tela de volta. */
    private var lastManualNavMs = 0L
    private var lastFollowMs = 0L

    fun goTo(page: Int) {
        lastManualNavMs = SystemClock.uptimeMillis()
        showPage(PageNavigator.clamp(page, total), save = true)
    }

    fun next() = currentPage()?.let { goTo(PageNavigator.next(it, total)) }
    fun prev() = currentPage()?.let { goTo(PageNavigator.prev(it, total)) }

    private fun currentPage(): Int? = (_state.value as? ReaderUiState.Ready)?.page

    private fun showPage(page: Int, save: Boolean) {
        val renderer = pdf ?: return
        pageJob?.cancel()
        pageJob = viewModelScope.launch {
            val size = try {
                withContext(Dispatchers.IO) { renderer.pageSize(page) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.value = ReaderUiState.Error("Falha ao ler a página ${page + 1}.")
                return@launch
            }
            _state.value = ReaderUiState.Ready(title, total, page, size)
            // O índice do trecho (lastChunkIndex) só passa a existir nas fases de áudio.
            if (save) repo.savePosition(bookId, page, 0)
        }
    }

    /** Pede a página [page] na escala [pixelsPerPoint]; a imagem anterior fica na tela até a nova chegar. */
    fun requestRender(page: Int, pixelsPerPoint: Float) {
        val renderer = pdf ?: return
        renderJob?.cancel()
        renderJob = viewModelScope.launch(Dispatchers.IO) {
            val bmp = renderCached(renderer, page, pixelsPerPoint) ?: return@launch
            ensureActive()
            _rendered.value = RenderedPage(page, pixelsPerPoint, bmp.asImageBitmap())
            // Prefetch da próxima página na mesma escala.
            if (page + 1 < total) {
                ensureActive()
                renderCached(renderer, page + 1, pixelsPerPoint)
            }
        }
    }

    private fun renderCached(renderer: PdfPageRenderer, page: Int, scale: Float): Bitmap? {
        val key = RenderKey(page, (scale * 100f).roundToInt())
        synchronized(cache) { cache.get(key) }?.let { return it }
        return try {
            val bmp = renderer.render(page, scale)
            synchronized(cache) { cache.put(key, bmp) }
            bmp
        } catch (e: CancellationException) {
            throw e
        } catch (e: Throwable) { // inclui OutOfMemoryError em zoom alto: mantém a imagem anterior
            null
        }
    }

    // --- Fase 3b: PdfEngine (texto). Aberto só quando necessário, para não atrasar a abertura da leitura. ---
    private val engineMutex = Mutex()
    private var engine: PdfEngine? = null
    private var probeJob: Job? = null
    private val _probe = MutableStateFlow<String?>(null)
    val probeReport: StateFlow<String?> = _probe.asStateFlow()

    private suspend fun getEngine(): PdfEngine = engineMutex.withLock {
        engine ?: withContext(Dispatchers.IO) {
            PdfEngine.open(getApplication(), Uri.parse(requireNotNull(bookUri)))
        }.also { engine = it }
    }

    /** TEMPORÁRIO: mede a extração de texto de 5 páginas a partir da atual e mostra o relatório. */
    fun runTextProbe() {
        val renderer = pdf ?: return
        val page = currentPage() ?: return
        probeJob?.cancel()
        _probe.value = "Medindo..."
        probeJob = viewModelScope.launch {
            _probe.value = try {
                TextProbe.run(getEngine(), { renderer.pageSize(it) }, page)
            } catch (e: CancellationException) {
                throw e
            } catch (t: Throwable) {
                "Falhou: ${t.javaClass.simpleName}: ${t.message}"
            }
        }
    }

    // --- Fase 6b: narração (o motor mora no processo, não na tela). ---
    private val narrationEngine by lazy { NarrationEngine.get(getApplication<Application>()) }
    val narration: StateFlow<NarrationState> get() = narrationEngine.state

    private fun readyIndex(): BookIndex? = (_index.value as? IndexState.Ready)?.index

    /**
     * Ouvir / Pausar. Se ainda não está narrando este livro: retoma do trecho salvo quando a página aberta é a da
     * posição salva (lastPage + lastChunkIndex); senão começa no 1º trecho da página atual.
     */
    fun toggleNarration() {
        val e = narrationEngine
        val s = e.state.value
        if (s.bookId == bookId) {
            when (s.status) {
                NarrationStatus.PLAYING, NarrationStatus.LOADING -> { e.pause(); return }
                NarrationStatus.PAUSED, NarrationStatus.ERROR, NarrationStatus.ENDED -> { e.resume(); return }
                NarrationStatus.IDLE -> Unit
            }
        }
        val index = readyIndex() ?: return
        val page = currentPage() ?: return
        viewModelScope.launch {
            val saved = repo.getBook(bookId)
            val resume = saved?.takeIf { it.lastPage == page }?.let { index.find(page, it.lastChunkIndex) }
            val chunk = resume ?: index.firstFrom(page) ?: return@launch
            e.play(bookId, title, index, chunk, prefs.voice.first())
        }
    }

    // --- Fase 7: grifo da palavra falada + a página acompanha a narração. ---
    private val _highlight = MutableStateFlow<Highlight?>(null)
    val highlight: StateFlow<Highlight?> = _highlight.asStateFlow()

    private var syncCursor = SyncCursor()
    private var syncedChunk = -1
    private var syncedWords: List<SyncedWord> = emptyList()
    private var lastNarratedPage: Int? = null

    private fun startNarrationWatcher() {
        viewModelScope.launch {
            narrationEngine.state.collect { s ->
                try {
                    onNarrationState(s)
                } catch (e: CancellationException) {
                    throw e
                } catch (_: Throwable) {
                    _highlight.value = null // sem grifo, mas a narração (e o app) seguem
                }
            }
        }
    }

    private suspend fun onNarrationState(s: NarrationState) {
        val chunk = s.chunk
        if (s.bookId != bookId || chunk == null || s.status == NarrationStatus.IDLE) {
            syncedChunk = -1
            syncedWords = emptyList()
            lastNarratedPage = null
            _highlight.value = null
            return
        }
        if (s.timings.isEmpty()) { // 1º trecho ainda sendo sintetizado
            _highlight.value = null
            return
        }
        if (chunk.index != syncedChunk || syncedWords.isEmpty()) {
            if (chunk.index <= syncedChunk) syncCursor = SyncCursor(chunk.pageIndex, 0) // voltou: busca desde o início da página
            val engine = getEngine()
            val pages = total
            val result = withContext(Dispatchers.IO) {
                val cache = HashMap<Int, List<PageWord>>()
                WordSyncEngine { p ->
                    cache.getOrPut(p) { if (p in 0 until pages) PageWord.fromAll(engine.extractPage(p).words) else emptyList() }
                }.sync(chunk.pageIndex, chunk.endPageIndex, s.timings, syncCursor)
            }
            syncedChunk = chunk.index
            syncedWords = result.words
            syncCursor = result.cursor
            engine.prefetch(chunk.endPageIndex + 1) // a próxima página já fica pronta para o próximo trecho
        }
        val h = HighlightBuilder.build(chunk.pageIndex, syncedWords, s.wordIndex)
        _highlight.value = h
        // A página acompanha a narração: quando a fala passa para outra página e também quando o usuário se afastou
        // da página falada e já passou FOLLOW_RESUME_MS desde a última navegação dele (a tela volta sozinha).
        val shown = currentPage()
        if (shown != null) {
            val now = SystemClock.uptimeMillis()
            val narratedPageChanged = h.page != lastNarratedPage
            val userAway = shown != h.page && now - lastManualNavMs >= FOLLOW_RESUME_MS
            if ((narratedPageChanged || userAway) && now - lastFollowMs > 800) {
                lastNarratedPage = h.page
                if (shown != h.page) {
                    lastFollowMs = now
                    showPage(h.page, save = false) // o progresso é salvo pelo motor
                }
            }
        }
    }

    private fun mine() = narrationEngine.state.value.bookId == bookId

    /** A narração em andamento é deste livro? (o motor é um só para o app todo) */
    fun isMine(state: NarrationState) = state.bookId == bookId

    fun narrationNext() { if (mine()) narrationEngine.next() }
    fun narrationPrevious() { if (mine()) narrationEngine.previous() }
    fun setNarrationSpeed(speed: Float) {
        narrationEngine.setSpeed(speed)
        viewModelScope.launch { prefs.setSpeed(speed) }
    }

    fun dismissProbe() {
        probeJob?.cancel()
        _probe.value = null
    }

    override fun onCleared() {
        val toClose = pdf
        val engineToClose = engine
        // A narração NÃO para aqui: ela segue em segundo plano (serviço de mídia, 6c).
        pdf = null
        engine = null
        // Fechar fora da main thread: pode esperar um render em andamento.
        CoroutineScope(Dispatchers.IO).launch {
            toClose?.close()
            engineToClose?.close()
        }
    }

    class Factory(private val app: Application, private val bookId: String) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = ReaderViewModel(app, bookId) as T
    }

    private companion object {
        const val CACHE_MAX_PIXELS = 16_000_000L

        /** Depois de o usuário trocar de página, a narração espera isto antes de trazer a tela de volta à página falada. */
        const val FOLLOW_RESUME_MS = 3000L
    }
}
