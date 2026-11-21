package com.lector.app.tts

import java.io.IOException

/** Base dos erros do cliente de TTS (todos são IOException, para o worker tratar como falha de rede/serviço). */
open class EdgeTtsException(message: String, cause: Throwable? = null) : IOException(message, cause)

/** O serviço não mandou nenhum áudio (parâmetros inválidos ou texto vazio). */
class NoAudioReceived(message: String) : EdgeTtsException(message)

/** Mensagem fora do formato esperado (cabeçalhos, tipo de conteúdo, metadados). */
class UnexpectedResponse(message: String) : EdgeTtsException(message)

/** Caminho (Path) de mensagem que o protocolo não conhece. */
class UnknownResponse(message: String) : EdgeTtsException(message)

/** Erro do WebSocket: queda, tempo esgotado ou encerramento antes do fim da síntese. */
class WebSocketError(message: String, cause: Throwable? = null) : EdgeTtsException(message, cause)

/** Não foi possível corrigir o relógio a partir do cabeçalho Date do servidor. */
class SkewAdjustmentError(message: String) : EdgeTtsException(message)

/**
 * A conexão foi recusada com um código HTTP (403 = token/relógio errado, ou bloqueio de rede).
 * [details] traz os cabeçalhos e o início do corpo da resposta, para diagnóstico.
 */
class EdgeHttpException(
    val statusCode: Int,
    val serverDate: String?,
    message: String,
    val details: String = "",
) : EdgeTtsException("HTTP $statusCode: $message")
