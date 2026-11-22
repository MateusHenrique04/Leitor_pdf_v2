package com.lector.app.download

import android.content.Context
import java.io.File

/** Onde ficam os MP3 baixados: `filesDir/tts/{bookId}/{voz}/{índice}.mp3`. */
object AudioFiles {
    fun bookDir(context: Context, bookId: String) = File(File(context.filesDir, "tts"), bookId)

    fun voiceDir(context: Context, bookId: String, voice: String) = File(bookDir(context, bookId), voice)

    fun chunkFile(context: Context, bookId: String, voice: String, chunkIndex: Int) =
        File(voiceDir(context, bookId, voice), "$chunkIndex.mp3")
}
