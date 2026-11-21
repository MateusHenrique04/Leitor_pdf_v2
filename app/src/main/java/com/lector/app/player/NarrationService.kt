package com.lector.app.player

import android.content.Intent
import androidx.media3.common.ForwardingPlayer
import androidx.media3.common.Player
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import com.lector.app.domain.NarrationStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

/**
 * Serviço de mídia (Fase 6c). Não toca nada sozinho: expõe o ExoPlayer do [NarrationEngine] como uma
 * MediaSession. O Media3 cuida da notificação (com Anterior/Pausar/Próximo) e de manter o serviço em
 * primeiro plano enquanto toca, o que mantém a narração viva com a tela apagada.
 */
class NarrationService : MediaSessionService() {
    private var session: MediaSession? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    override fun onCreate() {
        super.onCreate()
        val engine = NarrationEngine.get(this)
        val s = MediaSession.Builder(this, ChunkPlayer(engine.sessionPlayer, engine)).build()
        session = s
        addSession(s) // garante a notificação mesmo sem um MediaController conectado
        // Quando a narração é parada (stop), o serviço acaba junto.
        scope.launch {
            engine.state.map { it.status == NarrationStatus.IDLE }.distinctUntilChanged().collect { idle ->
                if (idle) stopSelf()
            }
        }
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    /** App removido dos recentes: se não está tocando, o serviço não tem por que ficar. */
    override fun onTaskRemoved(rootIntent: Intent?) {
        val p = session?.player
        if (p == null || !p.playWhenReady || p.mediaItemCount == 0) stopSelf()
    }

    override fun onDestroy() {
        scope.cancel()
        session?.release() // não libera o player: ele é do NarrationEngine
        session = null
        super.onDestroy()
    }
}

/**
 * O que a notificação e a tela de bloqueio enxergam. Anterior/Próximo viram "trecho anterior/próximo" do motor
 * (a playlist do ExoPlayer só tem os trechos já sintetizados), e some a barra de busca e os botões de ±5 s.
 */
private class ChunkPlayer(player: Player, private val engine: NarrationEngine) : ForwardingPlayer(player) {
    override fun getAvailableCommands(): Player.Commands =
        super.getAvailableCommands().buildUpon()
            .add(Player.COMMAND_SEEK_TO_NEXT)
            .add(Player.COMMAND_SEEK_TO_PREVIOUS)
            .add(Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM)
            .add(Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM)
            .remove(Player.COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM)
            .remove(Player.COMMAND_SEEK_BACK)
            .remove(Player.COMMAND_SEEK_FORWARD)
            .build()

    override fun isCommandAvailable(command: Int): Boolean = availableCommands.contains(command)

    override fun hasNextMediaItem(): Boolean = true
    override fun hasPreviousMediaItem(): Boolean = true

    override fun seekToNext() = engine.next()
    override fun seekToNextMediaItem() = engine.next()
    override fun seekToPrevious() = engine.previous()
    override fun seekToPreviousMediaItem() = engine.previous()
}
