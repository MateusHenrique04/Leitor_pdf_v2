package com.lector.app.tts

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Quadro recebido do servidor. */
sealed interface EdgeFrame {
    data class Text(val data: String) : EdgeFrame
    class Binary(val data: ByteArray) : EdgeFrame
    data class Failure(val error: Throwable) : EdgeFrame
}

/** Conexão aberta. [frames] fecha quando o servidor encerra. Existe para o cliente poder ser testado com um falso. */
interface EdgeSocket {
    val frames: ReceiveChannel<EdgeFrame>
    fun send(text: String)
    fun close()
}

interface EdgeTransport {
    /** Abre o WebSocket. Falha com [EdgeHttpException] se o servidor recusar a conexão com um código HTTP. */
    suspend fun connect(url: String, headers: Map<String, String>): EdgeSocket
}

/** Implementação real, com OkHttp. */
class OkHttpEdgeTransport(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(EdgeConstants.CONNECT_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        .build(),
) : EdgeTransport {

    override suspend fun connect(url: String, headers: Map<String, String>): EdgeSocket =
        suspendCancellableCoroutine { cont ->
            val channel = Channel<EdgeFrame>(Channel.UNLIMITED)
            val builder = Request.Builder().url(url)
            for ((k, v) in headers) builder.header(k, v)

            val listener = object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    if (cont.isActive) cont.resume(OkSocket(webSocket, channel))
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    channel.trySend(EdgeFrame.Text(text))
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    channel.trySend(EdgeFrame.Binary(bytes.toByteArray()))
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    channel.close()
                    webSocket.close(1000, null)
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    channel.close()
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (cont.isActive) {
                        if (response != null) {
                            cont.resumeWithException(
                                EdgeHttpException(response.code, response.header("Date"), response.message, describe(response)),
                            )
                        } else {
                            cont.resumeWithException(WebSocketError(t.message ?: "Falha ao conectar", t))
                        }
                    } else {
                        channel.trySend(EdgeFrame.Failure(t))
                    }
                    channel.close()
                }
            }
            val ws = client.newWebSocket(builder.build(), listener)
            cont.invokeOnCancellation {
                ws.cancel()
                channel.close()
            }
        }

    /** Cabeçalhos e começo do corpo da resposta de erro (sem dados pessoais: o servidor não recebe nenhum). */
    private fun describe(response: Response): String {
        val sb = StringBuilder()
        for (i in 0 until minOf(response.headers.size, 20)) {
            sb.append("  ").append(response.headers.name(i)).append(": ").append(response.headers.value(i)).append('\n')
        }
        val body = try {
            response.peekBody(300).string().trim()
        } catch (e: Exception) {
            ""
        }
        if (body.isNotEmpty()) sb.append("  corpo: ").append(body.replace('\n', ' ')).append('\n')
        return sb.toString()
    }

    private class OkSocket(private val ws: WebSocket, private val channel: Channel<EdgeFrame>) : EdgeSocket {
        override val frames: ReceiveChannel<EdgeFrame> get() = channel

        override fun send(text: String) {
            if (!ws.send(text)) throw WebSocketError("A conexão já estava fechada ao enviar.")
        }

        override fun close() {
            ws.close(1000, null)
            channel.close()
        }
    }
}
