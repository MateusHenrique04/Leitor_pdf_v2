package com.lector.app.ui.reader

import android.Manifest
import android.app.Application
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lector.app.domain.FitMode
import com.lector.app.domain.NarrationState
import com.lector.app.domain.NarrationStatus
import com.lector.app.domain.PageNavigator
import com.lector.app.domain.RenderPolicy
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlin.math.max
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReaderScreen(bookId: String, onBack: () -> Unit) {
    val app = LocalContext.current.applicationContext as Application
    val vm: ReaderViewModel = viewModel(key = bookId, factory = ReaderViewModel.Factory(app, bookId))
    val uiState by vm.state.collectAsStateWithLifecycle()
    val rendered by vm.rendered.collectAsStateWithLifecycle()
    val probe by vm.probeReport.collectAsStateWithLifecycle()
    val narration by vm.narration.collectAsStateWithLifecycle()
    val highlight by vm.highlight.collectAsStateWithLifecycle()
    // Android 13+: pede a permissão de notificações na 1ª vez que o usuário toca em "Ouvir" (a notificação traz
    // os controles com a tela apagada). Negada, a narração funciona do mesmo jeito, só sem a notificação visível.
    val context = LocalContext.current
    var askedNotifications by rememberSaveable { mutableStateOf(false) }
    val notificationLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        vm.toggleNarration()
    }
    val onToggleNarration = {
        val needs = Build.VERSION.SDK_INT >= 33 && !askedNotifications &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        if (needs) {
            askedNotifications = true
            notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            vm.toggleNarration()
        }
    }
    val indexState by vm.indexState.collectAsStateWithLifecycle()
    val pageState = rememberSaveable(saver = PageViewState.Saver) { PageViewState() }
    // Acompanha a palavra grifada (a cada palavra: com zoom a página desliza junto; ver RevealPolicy).
    val shown = (uiState as? ReaderUiState.Ready)?.page
    LaunchedEffect(highlight?.page, highlight?.word, shown) {
        val h = highlight ?: return@LaunchedEffect
        val w = h.word ?: return@LaunchedEffect
        if (h.page == shown) pageState.ensureVisible(w)
    }
    var showJump by remember { mutableStateOf(false) }
    val ready = uiState as? ReaderUiState.Ready

    // Página nova: reposiciona (topo, centralizada).
    LaunchedEffect(ready?.page, ready?.pageSize) {
        ready?.let { pageState.onPageChanged(it.pageSize) }
    }

    // Pede imagem nítida quando a escala muda (com pequena espera, para a pinça não renderizar a cada quadro).
    LaunchedEffect(ready?.page, rendered?.page, rendered?.pixelsPerPoint) {
        val r = ready ?: return@LaunchedEffect
        snapshotFlow { pageState.scale to pageState.viewport }.collectLatest { (scale, _) ->
            if (scale <= 0f) return@collectLatest
            delay(80)
            val needed = RenderPolicy.neededScale(
                scale, RenderPolicy.MAX_RENDER_PIXELS, r.pageSize.width, r.pageSize.height,
            )
            val current = rendered?.takeIf { it.page == r.page }?.pixelsPerPoint ?: 0f
            if (!RenderPolicy.isAcceptable(current, needed)) vm.requestRender(r.page, needed)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(ready?.title ?: "Lector", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Voltar à biblioteca")
                    }
                },
                actions = {
                    if (ready != null) {
                        TextButton(onClick = vm::runTextProbe) { Text("Texto") } // temporário (Fase 3b)
                        TextButton(onClick = {
                            pageState.changeFitMode(
                                if (pageState.fitMode == FitMode.WIDTH) FitMode.PAGE else FitMode.WIDTH
                            )
                        }) { Text(if (pageState.fitMode == FitMode.WIDTH) "Largura" else "Página") }
                        TextButton(onClick = { pageState.zoomStep(-1) }) { Text("−") }
                        TextButton(onClick = { pageState.resetView() }) {
                            Text("${(pageState.zoom * 100).roundToInt()}%")
                        }
                        TextButton(onClick = { pageState.zoomStep(+1) }) { Text("+") }
                    }
                },
            )
        },
        bottomBar = {
            ready?.let { r ->
                PageNavBar(
                    indexInfo = indexInfo(indexState, r.page, narration, vm.isMine(narration)),
                    narrationEnabled = indexState is IndexState.Ready,
                    narration = narration,
                    narrationMine = vm.isMine(narration),
                    onToggleNarration = onToggleNarration,
                    onNarrationPrev = vm::narrationPrevious,
                    onNarrationNext = vm::narrationNext,
                    onSpeed = vm::setNarrationSpeed,
                    page = r.page,
                    total = r.totalPages,
                    onPrev = vm::prev,
                    onNext = vm::next,
                    onSeek = vm::goTo,
                    onLabelClick = { showJump = true },
                )
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            when (val s = uiState) {
                ReaderUiState.Loading ->
                    CircularProgressIndicator(Modifier.align(Alignment.Center))
                is ReaderUiState.Error ->
                    Column(
                        Modifier.align(Alignment.Center).padding(32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Text(s.message, style = MaterialTheme.typography.bodyLarge)
                        Button(onClick = onBack) { Text("Voltar") }
                    }
                is ReaderUiState.Ready ->
                    PageCanvas(
                        page = s.page,
                        state = pageState,
                        rendered = rendered,
                        highlight = highlight,
                        onSwipePage = { dir -> if (dir > 0) vm.next() else vm.prev() },
                    )
            }
            // Sobreposta à página (não empurra o layout, para o zoom não ser reposicionado quando ela some).
            Box(Modifier.align(Alignment.TopCenter)) { IndexBanner(indexState, onRetry = vm::retryIndex) }
        }
    }

    if (showJump && ready != null) {
        JumpToPageDialog(
            total = ready.totalPages,
            onDismiss = { showJump = false },
            onConfirm = { index -> vm.goTo(index); showJump = false },
        )
    }

    probe?.let { report ->
        AlertDialog(
            onDismissRequest = vm::dismissProbe,
            title = { Text("Medição do texto (temporário)") },
            text = {
                SelectionContainer {
                    Text(
                        report,
                        fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.verticalScroll(rememberScrollState()),
                    )
                }
            },
            confirmButton = { TextButton(onClick = vm::dismissProbe) { Text("Fechar") } },
        )
    }
}

/** Faixa fina no topo: progresso ao preparar o livro (1ª vez) ou erro com "Tentar de novo". */
@Composable
private fun IndexBanner(state: IndexState, onRetry: () -> Unit) {
    when (state) {
        is IndexState.Building -> Surface(tonalElevation = 2.dp) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
                Text(
                    "Preparando o livro para narração… ${state.donePages}/${state.totalPages} páginas",
                    style = MaterialTheme.typography.labelMedium,
                )
                LinearProgressIndicator(
                    progress = { if (state.totalPages > 0) state.donePages / state.totalPages.toFloat() else 0f },
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                )
            }
        }
        is IndexState.Failed -> Surface(tonalElevation = 2.dp, color = MaterialTheme.colorScheme.errorContainer) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Não consegui preparar o livro: ${state.message}",
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onRetry) { Text("Tentar de novo") }
            }
        }
        else -> Unit
    }
}

/** Texto temporário (Fases 6a/6b), sempre 2 linhas para a altura da barra não mudar. */
private fun indexInfo(state: IndexState, page: Int, narration: NarrationState, mine: Boolean): String {
    if (mine && narration.status != NarrationStatus.IDLE) {
        val chunk = narration.chunk
        val total = (state as? IndexState.Ready)?.index?.chunks?.size ?: 0
        val where = if (chunk != null) "trecho ${chunk.index + 1}/$total • pág. ${chunk.pageIndex + 1}" else ""
        val word = narration.timings.getOrNull(narration.wordIndex)?.word.orEmpty()
        val status = when (narration.status) {
            NarrationStatus.LOADING -> "sintetizando…"
            NarrationStatus.PLAYING -> "falando: $word"
            NarrationStatus.PAUSED -> "pausado"
            NarrationStatus.ENDED -> "fim do livro"
            NarrationStatus.ERROR -> "erro: ${narration.error.orEmpty()}"
            NarrationStatus.IDLE -> ""
        }
        return "$where\n$status"
    }
    return when (state) {
        is IndexState.Ready -> {
            val here = state.index.chunksStartingOn(page).size
            val origem = if (state.fromCache) "do arquivo" else "montado em %.1f s".format(java.util.Locale.US, state.buildMs / 1000.0)
            "Narração: ${state.index.chunks.size} trechos ($origem) | começam nesta página: $here\n "
        }
        IndexState.NoText -> "Narração: este PDF não tem texto (escaneado?)\n "
        is IndexState.Building -> "Narração: preparando o livro…\n "
        is IndexState.Failed -> "Narração: indisponível\n "
        IndexState.Idle -> " \n "
    }
}

@Composable
private fun PageNavBar(
    indexInfo: String,
    narrationEnabled: Boolean,
    narration: NarrationState,
    narrationMine: Boolean,
    onToggleNarration: () -> Unit,
    onNarrationPrev: () -> Unit,
    onNarrationNext: () -> Unit,
    onSpeed: (Float) -> Unit,
    page: Int,
    total: Int,
    onPrev: () -> Unit,
    onNext: () -> Unit,
    onSeek: (Int) -> Unit,
    onLabelClick: () -> Unit,
) {
    var sliderValue by remember(page) { mutableFloatStateOf(page.toFloat()) }
    Surface(tonalElevation = 3.dp) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp)) {
            // Temporário (Fase 6a). Sempre uma linha, para a altura da barra não mudar e o zoom não ser reposicionado.
            Text(
                indexInfo,
                style = MaterialTheme.typography.labelSmall,
                minLines = 2,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.align(Alignment.CenterHorizontally),
            )
            // Controles da narração (sempre presentes; desabilitados até o índice ficar pronto).
            val speeds = listOf(0.75f, 1f, 1.25f, 1.5f, 2f)
            val active = narrationMine && (narration.status == NarrationStatus.PLAYING || narration.status == NarrationStatus.LOADING)
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onNarrationPrev, enabled = narrationEnabled && narrationMine) { Text("Anterior") }
                TextButton(onClick = onToggleNarration, enabled = narrationEnabled) { Text(if (active) "Pausar" else "Ouvir") }
                TextButton(onClick = onNarrationNext, enabled = narrationEnabled && narrationMine) { Text("Próximo") }
                TextButton(onClick = {
                    val i = speeds.indexOfFirst { it == narration.speed }
                    onSpeed(speeds[(i + 1) % speeds.size])
                }) { Text(narration.speed.toString().replace('.', ',') + "x") }
            }
            Text(
                "${sliderValue.roundToInt() + 1} / $total  (toque para ir a uma página)",
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.align(Alignment.CenterHorizontally).clickable(onClick = onLabelClick).padding(4.dp),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onPrev, enabled = page > 0) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Página anterior")
                }
                Slider(
                    value = sliderValue,
                    onValueChange = { sliderValue = it },
                    onValueChangeFinished = { onSeek(sliderValue.roundToInt()) },
                    valueRange = 0f..max(1, total - 1).toFloat(),
                    enabled = total > 1,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = onNext, enabled = page < total - 1) {
                    Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = "Próxima página")
                }
            }
        }
    }
}

@Composable
private fun JumpToPageDialog(total: Int, onDismiss: () -> Unit, onConfirm: (Int) -> Unit) {
    var text by remember { mutableStateOf("") }
    val parsed = PageNavigator.parseUserPage(text, total)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Ir para a página") },
        text = {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it.filter(Char::isDigit).take(6) },
                label = { Text("Página (1 a $total)") },
                singleLine = true,
                isError = text.isNotEmpty() && parsed == null,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )
        },
        confirmButton = { TextButton(enabled = parsed != null, onClick = { parsed?.let(onConfirm) }) { Text("Ir") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}
