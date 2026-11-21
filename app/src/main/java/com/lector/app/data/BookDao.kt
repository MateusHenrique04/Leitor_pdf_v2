package com.lector.app.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface BookDao {
    @Query("SELECT * FROM books ORDER BY lastOpenedAt DESC")
    fun observeAll(): Flow<List<BookEntity>>

    @Query("SELECT * FROM books WHERE id = :id")
    suspend fun getById(id: String): BookEntity?

    @Query("SELECT * FROM books WHERE uri = :uri")
    suspend fun getByUri(uri: String): BookEntity?

    /** Devolve -1 se a uri já existia (índice único) e nada foi inserido. */
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(book: BookEntity): Long

    @Query("UPDATE books SET lastPage = :page, lastChunkIndex = :chunk, lastOpenedAt = :now WHERE id = :id")
    suspend fun updatePosition(id: String, page: Int, chunk: Int, now: Long)

    @Query("UPDATE books SET totalPages = :total WHERE id = :id")
    suspend fun updateTotalPages(id: String, total: Int)

    @Query("UPDATE books SET finished = :finished WHERE id = :id")
    suspend fun setFinished(id: String, finished: Boolean)

    @Query("UPDATE books SET lastOpenedAt = :now WHERE id = :id")
    suspend fun touch(id: String, now: Long)

    @Query("DELETE FROM books WHERE id = :id")
    suspend fun deleteById(id: String)
}
