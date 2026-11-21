package com.lector.app.ui.library

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.lector.app.data.AddBookResult
import com.lector.app.data.BookEntity
import com.lector.app.data.BookRepository
import com.lector.app.data.LectorDatabase
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class LibraryViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = BookRepository(app, LectorDatabase.get(app).bookDao())

    val books: StateFlow<List<BookEntity>> =
        repo.observeAll().stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val _isAdding = MutableStateFlow(false)
    val isAdding: StateFlow<Boolean> = _isAdding.asStateFlow()

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 4)
    val messages: SharedFlow<String> = _messages.asSharedFlow()

    fun onPdfPicked(uri: Uri?) {
        if (uri == null) return
        viewModelScope.launch {
            _isAdding.value = true
            val msg = when (val r = repo.addFromUri(uri)) {
                is AddBookResult.Added -> "Adicionado: ${r.book.title}"
                is AddBookResult.AlreadyExists -> "\"${r.book.title}\" já está na biblioteca."
                is AddBookResult.Failed -> r.reason
            }
            _isAdding.value = false
            _messages.tryEmit(msg)
        }
    }

    fun remove(book: BookEntity) {
        viewModelScope.launch { repo.remove(book) }
    }
}
