package com.lector.app.download

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat

/** Notificação do download em primeiro plano, com os botões Pausar e Cancelar. */
object DownloadNotifications {
    const val CHANNEL_ID = "lector_downloads"
    const val ACTION_PAUSE = "com.lector.app.download.PAUSE"
    const val ACTION_CANCEL = "com.lector.app.download.CANCEL"
    const val EXTRA_BOOK = "bookId"
    const val EXTRA_VOICE = "voice"

    fun notificationId(bookId: String, voice: String) = ("dl:$bookId:$voice").hashCode()

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val nm = context.getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Download de áudio", NotificationManager.IMPORTANCE_LOW),
            )
        }
    }

    /** [total] = 0 mostra a barra indeterminada (ainda preparando). */
    fun build(context: Context, bookId: String, voice: String, title: String, done: Int, total: Int) =
        run {
            ensureChannel(context)
            NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle("Baixando áudio: $title")
                .setContentText(if (total > 0) "$done de $total trechos" else "Preparando…")
                .setProgress(total, done, total == 0)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .addAction(0, "Pausar", action(context, ACTION_PAUSE, bookId, voice))
                .addAction(0, "Cancelar", action(context, ACTION_CANCEL, bookId, voice))
                .build()
        }

    private fun action(context: Context, action: String, bookId: String, voice: String): PendingIntent {
        val intent = Intent(context, DownloadActionReceiver::class.java)
            .setAction(action)
            .putExtra(EXTRA_BOOK, bookId)
            .putExtra(EXTRA_VOICE, voice)
        val requestCode = (action + notificationId(bookId, voice)).hashCode()
        return PendingIntent.getBroadcast(context, requestCode, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
