package com.lector.app.tts

/**
 * Constantes do endpoint (copiadas de edge_tts/constants.py, versão 7.2.8 do edge-tts).
 * O endpoint NÃO é oficial: se a conexão passar a ser recusada, compare com a versão mais nova do edge-tts
 * (CHROMIUM_FULL_VERSION, headers e o algoritmo do token mudam de tempos em tempos).
 */
object EdgeConstants {
    const val BASE_URL = "speech.platform.bing.com/consumer/speech/synthesize/readaloud"
    const val TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
    const val WSS_URL = "wss://$BASE_URL/edge/v1?TrustedClientToken=$TRUSTED_CLIENT_TOKEN"

    const val DEFAULT_VOICE = "en-US-EmmaMultilingualNeural"

    const val CHROMIUM_FULL_VERSION = "143.0.3650.75"
    const val CHROMIUM_MAJOR_VERSION = "143" // = CHROMIUM_FULL_VERSION.split(".")[0]
    // Token v2 (obrigatório desde ~10/out/2026) exige o prefixo "2-". Com "1-" o servidor responde 403.
    const val SEC_MS_GEC_VERSION = "2-$CHROMIUM_FULL_VERSION"

    /**
     * Headers do WebSocket. "Sec-WebSocket-Version" não entra: o OkHttp já envia (13).
     * O cookie "muid" é gerado a cada conexão (ver EdgeProtocol.muid).
     */
    val WSS_HEADERS: Map<String, String> = mapOf(
        "Pragma" to "no-cache",
        "Cache-Control" to "no-cache",
        "Origin" to "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold",
        "User-Agent" to "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" +
            " (KHTML, like Gecko) Chrome/$CHROMIUM_MAJOR_VERSION.0.0.0 Safari/537.36" +
            " Edg/$CHROMIUM_MAJOR_VERSION.0.0.0",
        "Accept-Encoding" to "gzip, deflate, br, zstd",
        "Accept-Language" to "en-US,en;q=0.9",
    )

    const val OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

    /** Compensação entre trechos: 1 s = 10.000.000 ticks (100 ns); MP3 CBR de 48 kbps. */
    const val TICKS_PER_SECOND = 10_000_000L
    const val MP3_BITRATE_BPS = 48_000L

    /** O serviço recusa SSML grande: o texto é dividido em partes de até 4096 bytes. */
    const val MAX_TEXT_BYTES = 4096

    const val CONNECT_TIMEOUT_MS = 10_000L
    const val RECEIVE_TIMEOUT_MS = 60_000L
}
