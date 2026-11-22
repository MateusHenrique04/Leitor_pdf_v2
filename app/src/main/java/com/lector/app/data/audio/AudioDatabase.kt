package com.lector.app.data.audio

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

/**
 * Banco separado do cache de narração offline (audio.db). Fica fora do lector.db de propósito: o banco dos
 * livros não muda (sem migração, sem risco para a biblioteca); os dois se ligam só pelo bookId.
 */
@Database(entities = [AudioChunkEntity::class, DownloadJobEntity::class], version = 1, exportSchema = false)
abstract class AudioDatabase : RoomDatabase() {
    abstract fun audioDao(): AudioDao

    companion object {
        @Volatile private var instance: AudioDatabase? = null

        fun get(context: Context): AudioDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AudioDatabase::class.java,
                    "audio.db",
                ).build().also { instance = it }
            }
    }
}
