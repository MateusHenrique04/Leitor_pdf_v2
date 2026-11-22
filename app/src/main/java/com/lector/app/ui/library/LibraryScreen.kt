package com.lector.app.ui.library

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.lector.app.data.BookEntity
import com.lector.app.domain.ReadingProgress

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(onOpenBook: (BookEntity) -> Unit, viewModel: LibraryViewModel = viewModel()) {
    val books by viewModel.books.collectAsStateWithLifecycle()
    val offlineBooks by viewModel.offlineBooks.collectAsStateWithLifecycle()
    val isAdding by viewModel.isAdding.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    var bookToDelete by remember { mutableStateOf<BookEntity?>(null) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        viewModel.onPdfPicked(uri)
    }

    LaunchedEffect(Unit) {
        viewModel.messages.collect { snackbarHostState.showSnackbar(it) }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Lector") }) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { if (!isAdding) picker.launch(arrayOf("application/pdf")) },
                icon = { Icon(Icons.Default.Add, contentDescription = null) },
                text = { Text("Adicionar PDF") },
            )
        },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            if (books.isEmpty()) {
                Text(
                    "Sua biblioteca está vazia.\nToque em \"Adicionar PDF\" para começar.",
                    modifier = Modifier.align(Alignment.Center).padding(32.dp),
                    style = MaterialTheme.typography.bodyLarge,
                )
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(books, key = { it.id }) { book ->
                        BookCard(
                            book = book,
                            offline = book.id in offlineBooks,
                            onClick = { onOpenBook(book) },
                            onDelete = { bookToDelete = book },
                        )
                    }
                }
            }
            if (isAdding) {
                LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
            }
        }
    }

    bookToDelete?.let { book ->
        AlertDialog(
            onDismissRequest = { bookToDelete = null },
            title = { Text("Remover da biblioteca?") },
            text = { Text("\"${book.title}\" sai da biblioteca. O arquivo PDF não é apagado do aparelho.") },
            confirmButton = {
                TextButton(onClick = { viewModel.remove(book); bookToDelete = null }) { Text("Remover") }
            },
            dismissButton = { TextButton(onClick = { bookToDelete = null }) { Text("Cancelar") } },
        )
    }
}

@Composable
private fun BookCard(book: BookEntity, offline: Boolean, onClick: () -> Unit, onDelete: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(start = 16.dp, top = 8.dp, bottom = 8.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    book.title,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    ReadingProgress.label(book.lastPage, book.totalPages, book.finished),
                    style = MaterialTheme.typography.bodyMedium,
                )
                if (offline) {
                    Text(
                        "Disponível offline",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Remover da biblioteca")
            }
        }
    }
}
