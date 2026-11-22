package com.lector.app.ui.downloads

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.lector.app.data.BookEntity
import com.lector.app.data.BookRepository
import com.lector.app.data.LectorDatabase
import com.lector.app.data.LectorPrefs
import com.lector.app.data.audio.AudioDatabase
import com.lector.app.data.audio.DownloadJobEntity
import com.lector.app.domain.DownloadEstimate
import com.lector.app.domain.Formatters
import com.lector.app.domain.PageRangeParser
import com.lector.app.domain.Voices
import com.lector.app.download.DownloadManager
import com.lector.app.download.StartResult
import com.lector.app.player.NarrationEngine
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class DownloadsUiState(
    val loading: Boolean = true,
    val totalPages: Int = 0,
    val voice: String = Voices.DEFAULT_ID,
    val wholeBook: Boolean = true,
    val fromText: String = "1",
    val toText: String = "",
    val wifiOnly: Boolean = true,
    val chargingOnly: Boolean = false,
    val estimate: DownloadEstimate? = null,
    val estimateError: String? = null,
    /** Pedido da voz escolhida (null = nunca baixou ou foi cancelado). */
    val job: DownloadJobEntity? = null,
    /** Espaço ocupado por voz (só as que têm áudio). */
    val voiceBytes: Map<String, Long> = emptyMap(),
    val busy: Boolean = false,
    val message: String? = null,
)

@OptIn(ExperimentalCoroutinesApi::class)
class DownloadsViewModel(app: Application, private val bookId: String) : AndroidViewModel(app) {
    private val prefs = LectorPrefs(app)
    private val dao = AudioDatabase.get(app).audioDao()
    private val repo = BookRepository(app, LectorDatabase.get(app).bookDao())
    private val manager = DownloadManager(app)
    private var book: BookEntity? = null
    private var estimateJob: Job? = null

    private val _ui = MutableStateFlow(DownloadsUiState())
    val ui: StateFlow<DownloadsUiState> = _ui.asStateFlow()

    init {
        viewModelScope.launch {
            val b = repo.getBook(bookId) ?: return@launch
            book = b
            _ui.update { it.copy(loading = false, totalPages = b.totalPages, toText = b.totalPages.toString()) }
            recomputeEstimate()
        }
        viewModelScope.launch { prefs.voice.collect { v -> _ui.update { it.copy(voice = v) } } }
        viewModelScope.launch { prefs.wifiOnly.collect { v -> _ui.update { it.copy(wifiOnly = v) } } }
        viewModelScope.launch { prefs.chargingOnly.collect { v -> _ui.update { it.copy(chargingOnly = v) } } }
        viewModelScope.launch {
            prefs.voice.flatMapLatest { v -> dao.observeJob(bookId, v) }.collect { job ->
                _ui.update { it.copy(job = job) }
                refreshBytes() // o espaço ocupado cresce a cada trecho baixado
            }
        }
        viewModelScope.launch { dao.observeVoicesWithAudio(bookId).collect { refreshBytes() } }
    }

    private suspend fun refreshBytes() {
        val map = Voices.ALL.associate { it.id to dao.totalBytes(bookId, it.id) }.filterValues { it > 0 }
        _ui.update { it.copy(voiceBytes = map) }
    }

    // ---------------- escolhas ----------------

    /** A voz vale para a narração e para os downloads. Narrando agora, recomeça o trecho atual com a voz nova. */
    fun selectVoice(id: String) {
        viewModelScope.launch {
            prefs.setVoice(id)
            NarrationEngine.peek()?.setVoice(id)
        }
    }

    fun setWholeBook(whole: Boolean) { _ui.update { it.copy(wholeBook = whole) }; recomputeEstimate() }
    fun setFrom(text: String) { _ui.update { it.copy(fromText = text.filter(Char::isDigit).take(5)) }; recomputeEstimate() }
    fun setTo(text: String) { _ui.update { it.copy(toText = text.filter(Char::isDigit).take(5)) }; recomputeEstimate() }
    fun setWifiOnly(v: Boolean) { viewModelScope.launch { prefs.setWifiOnly(v) } }
    fun setChargingOnly(v: Boolean) { viewModelScope.launch { prefs.setChargingOnly(v) } }

    private fun recomputeEstimate() {
        estimateJob?.cancel()
        estimateJob = viewModelScope.launch {
            val b = book ?: return@launch
            val s = _ui.value
            val range = PageRangeParser.parse(s.wholeBook, s.fromText, s.toText, b.totalPages)
            if (range == null) {
                _ui.update { it.copy(estimate = null, estimateError = "Páginas inválidas (use de 1 a ${b.totalPages}).") }
                return@launch
            }
            val e = manager.estimate(b, range.first, range.last)
            _ui.update {
                it.copy(
                    estimate = e,
                    estimateError = if (e == null) "O livro ainda não foi preparado para narração (abra-o e espere o índice) ou essas páginas não têm texto." else null,
                )
            }
        }
    }

    // ---------------- ações ----------------

    fun start() {
        val b = book ?: return
        val s = _ui.value
        val range = PageRangeParser.parse(s.wholeBook, s.fromText, s.toText, b.totalPages) ?: return
        viewModelScope.launch {
            _ui.update { it.copy(busy = true, message = null) }
            val msg = when (val r = manager.start(b, s.voice, range.first, range.last, s.wifiOnly, s.chargingOnly)) {
                is StartResult.Started -> null
                StartResult.NoIndex -> "O livro ainda não foi preparado. Abra-o e espere o índice terminar."
                StartResult.NoText -> "Essas páginas não têm texto para narrar."
                is StartResult.NotEnoughSpace ->
                    "Sem espaço: precisa de ~${Formatters.bytes(r.neededBytes)} e há ${Formatters.bytes(r.availableBytes)} livres."
            }
            _ui.update { it.copy(busy = false, message = msg) }
        }
    }

    fun pause() = act { manager.pause(bookId, _ui.value.voice) }
    fun resume() = act { manager.resume(bookId, _ui.value.voice) }
    fun cancel() = act { manager.cancel(bookId, _ui.value.voice) }
    fun retryFailed() = act { manager.retryFailed(bookId, _ui.value.voice) }

    fun deleteAudio() = act {
        manager.deleteVoice(bookId, _ui.value.voice)
        refreshBytes()
    }

    private fun act(block: suspend () -> Unit) {
        viewModelScope.launch {
            _ui.update { it.copy(message = null) }
            block()
        }
    }

    class Factory(private val app: Application, private val bookId: String) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = DownloadsViewModel(app, bookId) as T
    }
}
