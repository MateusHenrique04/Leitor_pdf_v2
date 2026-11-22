package com.lector.app.ui.downloads

import android.app.Application
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lector.app.data.audio.JobState
import com.lector.app.domain.Formatters
import com.lector.app.domain.Voices

/** Gerenciamento do áudio do livro (Fase 8.5): voz, download offline (intervalo, restrições), andamento e apagar. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AudioSheet(bookId: String, onDismiss: () -> Unit, onTextDiagnostic: () -> Unit) {
    val app = LocalContext.current.applicationContext as Application
    val vm: DownloadsViewModel = viewModel(key = "audio-$bookId", factory = DownloadsViewModel.Factory(app, bookId))
    val ui by vm.ui.collectAsStateWithLifecycle()
    var confirmDelete by remember { mutableStateOf(false) }
    val voiceBytes = ui.voiceBytes[ui.voice]

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Áudio do livro", style = MaterialTheme.typography.titleLarge)

            // ---- voz ----
            Text("Voz", style = MaterialTheme.typography.titleSmall)
            Voices.ALL.forEach { v ->
                ChoiceRow(
                    selected = ui.voice == v.id,
                    onClick = { vm.selectVoice(v.id) },
                    label = v.label,
                    detail = ui.voiceBytes[v.id]?.let { "baixado: ${Formatters.bytes(it)}" },
                )
            }
            Text(
                "A voz escolhida vale para a narração e para os downloads.",
                style = MaterialTheme.typography.bodySmall,
            )
            HorizontalDivider()

            // ---- download ----
            Text("Baixar para ouvir sem internet", style = MaterialTheme.typography.titleSmall)
            ChoiceRow(selected = ui.wholeBook, onClick = { vm.setWholeBook(true) }, label = "Livro inteiro (${ui.totalPages} páginas)")
            ChoiceRow(selected = !ui.wholeBook, onClick = { vm.setWholeBook(false) }, label = "Só algumas páginas")
            if (!ui.wholeBook) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = ui.fromText, onValueChange = vm::setFrom, label = { Text("Da página") },
                        singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                    OutlinedTextField(
                        value = ui.toText, onValueChange = vm::setTo, label = { Text("Até a página") },
                        singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                    )
                }
            }
            SwitchRow("Só no Wi-Fi", ui.wifiOnly, vm::setWifiOnly)
            SwitchRow("Só carregando", ui.chargingOnly, vm::setChargingOnly)

            val e = ui.estimate
            Text(
                when {
                    e != null -> "Estimativa: ${e.chunks} trechos, ~${Formatters.duration(e.audioSeconds)} de áudio, ~${Formatters.bytes(e.bytes)}."
                    ui.estimateError != null -> ui.estimateError!!
                    else -> "Calculando…"
                },
                style = MaterialTheme.typography.bodyMedium,
                color = if (e == null && ui.estimateError != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
            )

            JobSection(ui, vm)

            ui.message?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }

            // ---- apagar ----
            if (voiceBytes != null) {
                HorizontalDivider()
                Text("Esta voz ocupa ${Formatters.bytes(voiceBytes)} neste livro.", style = MaterialTheme.typography.bodyMedium)
                OutlinedButton(onClick = { confirmDelete = true }) { Text("Apagar áudio desta voz") }
            }

            HorizontalDivider()
            TextButton(onClick = { onDismiss(); onTextDiagnostic() }) { Text("Diagnóstico de texto") }
        }
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Apagar o áudio baixado?") },
            text = { Text("Só o áudio desta voz neste livro. O PDF e as outras vozes não são afetados. A narração on-line continua funcionando.") },
            confirmButton = { TextButton(onClick = { vm.deleteAudio(); confirmDelete = false }) { Text("Apagar") } },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancelar") } },
        )
    }
}

@Composable
private fun JobSection(ui: DownloadsUiState, vm: DownloadsViewModel) {
    val job = ui.job
    when {
        job == null || job.state == JobState.DONE -> {
            if (job != null) {
                Text("Pronto: ${job.doneChunks} trechos baixados (páginas ${job.fromPage + 1} a ${job.toPage + 1}).", style = MaterialTheme.typography.bodyMedium)
            }
            Button(onClick = vm::start, enabled = ui.estimate != null && !ui.busy) {
                Text(if (job == null) "Baixar áudio" else "Baixar de novo / outro trecho")
            }
        }
        job.state == JobState.RUNNING || job.state == JobState.QUEUED -> {
            val label = if (job.state == JobState.QUEUED) "Na fila (espera a rede ou a restrição escolhida)" else "Baixando"
            Text("$label: ${job.doneChunks} de ${job.totalChunks} trechos", style = MaterialTheme.typography.bodyMedium)
            LinearProgressIndicator(
                progress = { if (job.totalChunks > 0) job.doneChunks / job.totalChunks.toFloat() else 0f },
                modifier = Modifier.fillMaxWidth(),
            )
            job.lastError?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Button(onClick = vm::pause) { Text("Pausar") }
                OutlinedButton(onClick = vm::cancel) { Text("Cancelar") }
            }
        }
        job.state == JobState.PAUSED -> {
            Text("Pausado: ${job.doneChunks} de ${job.totalChunks} trechos", style = MaterialTheme.typography.bodyMedium)
            LinearProgressIndicator(
                progress = { if (job.totalChunks > 0) job.doneChunks / job.totalChunks.toFloat() else 0f },
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = vm::resume) { Text("Retomar") }
                OutlinedButton(onClick = vm::cancel) { Text("Cancelar") }
            }
        }
        else -> { // FAILED
            Text("Falhou: ${job.doneChunks} de ${job.totalChunks} trechos baixados.", style = MaterialTheme.typography.bodyMedium)
            job.lastError?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = vm::retryFailed) { Text("Tentar de novo só os que falharam") }
            }
            OutlinedButton(onClick = vm::cancel) { Text("Cancelar") }
        }
    }
}

@Composable
private fun ChoiceRow(selected: Boolean, onClick: () -> Unit, label: String, detail: String? = null) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick), verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = selected, onClick = null)
        Column(Modifier.padding(start = 12.dp)) {
            Text(label, style = MaterialTheme.typography.bodyLarge)
            if (detail != null) Text(detail, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
