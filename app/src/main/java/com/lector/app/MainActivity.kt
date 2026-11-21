package com.lector.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import com.lector.app.ui.library.LibraryScreen
import com.lector.app.ui.reader.ReaderScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                // Navegação simples por estado (sem biblioteca de navegação por enquanto).
                var openBookId by rememberSaveable { mutableStateOf<String?>(null) }
                val id = openBookId
                if (id == null) {
                    LibraryScreen(onOpenBook = { openBookId = it.id })
                } else {
                    BackHandler { openBookId = null }
                    ReaderScreen(bookId = id, onBack = { openBookId = null })
                }
            }
        }
    }
}
