package com.lector.app.data

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * Livro da biblioteca. No desktop a chave era o caminho do arquivo; aqui é um [id] (UUID)
 * estável (o cache de áudio da Fase 8 usa esse id) e o arquivo é a [uri] do SAF, única.
 *
 * SUPOSIÇÃO: campos derivados do library.json do desktop (last_page, last_chunk_idx,
 * total_pages, finished) + addedAt/lastOpenedAt para ordenar a biblioteca.
 */
@Entity(tableName = "books", indices = [Index(value = ["uri"], unique = true)])
data class BookEntity(
    @PrimaryKey val id: String,
    val uri: String,
    val title: String,
    val totalPages: Int,
    val lastPage: Int = 0,
    val lastChunkIndex: Int = 0,
    val finished: Boolean = false,
    val addedAt: Long,
    val lastOpenedAt: Long,
)
