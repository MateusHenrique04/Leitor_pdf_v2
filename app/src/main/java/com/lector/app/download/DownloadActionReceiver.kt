package com.lector.app.download

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** Botões Pausar e Cancelar da notificação do download. */
class DownloadActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val bookId = intent.getStringExtra(DownloadNotifications.EXTRA_BOOK) ?: return
        val voice = intent.getStringExtra(DownloadNotifications.EXTRA_VOICE) ?: return
        val action = intent.action
        val pending = goAsync()
        val app = context.applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val manager = DownloadManager(app)
                when (action) {
                    DownloadNotifications.ACTION_PAUSE -> manager.pause(bookId, voice)
                    DownloadNotifications.ACTION_CANCEL -> manager.cancel(bookId, voice)
                }
            } finally {
                pending.finish()
            }
        }
    }
}
