# Lector Android (projeto real)
Fase 1: biblioteca + abrir PDF via SAF + Room.
Fase 2: tela de leitura (PdfRenderer), navegação e zoom.
Fase 3: lógica de texto em Kotlin puro (domain/): normalizeWord, TextSplitter, TextCleaner, ChunkPlanner (v1),
com testes portados de test_text.py. Ainda não está ligada à tela (falta o PdfEngine que extrai o texto).
Abra a pasta `lector` no Android Studio (File > Open). Gradle fixado em 8.9.
Testes unitários (PC): app/src/test. Testes de DAO (celular): app/src/androidTest.
Fase 3b: PdfEngine (PdfBox-Android) em pdf/, com WordAssembler, LineBuilder, ParagraphGrouper e PageGeometry em domain/ (Kotlin puro, com testes).
Botão temporário "Texto" na tela de leitura: mede a extração de 5 páginas e mostra o texto limpo.
Fase 3b.1: TextCleaner une palavras hifenizadas com hífen suave (U+00AD) e o relatório mostra caracteres estranhos no fim das linhas.

Fase 4: EdgeTtsClient (tts/): token Sec-MS-GEC portado (EdgeDrm.java, conferido contra o drm.py do edge-tts 7.2.8), protocolo puro (EdgeProtocol), OkHttp WebSocket.
No diálogo do botão "Texto": "Narrar" sintetiza o 1º trecho da página (internet) e "Ouvir" toca o MP3. Temporário.
OkHttp 4.12.0 em libs.versions.toml: conferir a versão.

Fase 5: WordSyncEngine (domain/WordSyncEngine.kt): porte de core/word_sync.py (WordSync.matchForward/anchorChunk/mergeRectsByLine)
+ WordSyncEngine.sync(startPage, endPage, timings, cursor), que também trata trecho que cruza páginas (SyncCursor = página + índice da palavra).
Testes: WordSyncEngineTest (portados de test_word_sync.py + casos de página cruzada). Ainda não ligado à tela (Fase 7).

Fase 6a: índice de narração do livro inteiro (opção A). BookIndexer (domain/) extrai o texto de todas as páginas, limpa e planeja com o ChunkPlanner;
BookIndexCodec grava em texto simples; BookIndexStore (data/) guarda em filesDir/index/{bookId}.v{VERSION}.idx (escrita atômica; apagado ao remover o livro).
A tela de leitura mostra "Preparando o livro para narração… x/y" na 1ª abertura; depois lê do arquivo. Linha temporária na barra inferior mostra o nº de trechos.
Próximo: 6b (player Media3 + serviço de mídia).

Fase 6b: NarrationEngine (player/): ExoPlayer (Media3), síntese on-line trecho a trecho (3 à frente), um MediaItem por trecho cortado em
"fim da última palavra + 0,10 s", velocidade pelo player (posição comparada direto com os tempos, sem dividir). WordClock (domain/) dá a palavra falada.
Controles temporários na barra inferior da leitura: Anterior / Ouvir-Pausar / Próximo / velocidade. A Fase 4 (Narrar/Ouvir do diálogo de teste) foi removida.
O motor para ao sair do livro; a 6c o move para um MediaSessionService (tela apagada, notificação).

Fase 6c: NarrationService (player/): MediaSessionService que expõe o ExoPlayer do NarrationEngine como MediaSession (notificação com Anterior/Pausar/Próximo,
narração com a tela apagada e ao voltar para a biblioteca). O motor liga ao serviço (bindService) ao começar e solta ao parar; o serviço se encerra quando o estado volta a IDLE.
Permissão de notificações (Android 13+) pedida na 1ª vez em "Ouvir". Manifesto: FOREGROUND_SERVICE(+_MEDIA_PLAYBACK), POST_NOTIFICATIONS, WAKE_LOCK, ACCESS_WIFI_STATE.

Fase 7 (7c: a tela volta à página falada 3 s depois de o usuário folhear; 7b: com zoom a página acompanha cada palavra na horizontal e espera 2,5 s depois de um gesto): grifo + página acompanha + progresso. WordSyncEngine liga o PdfEngine ao áudio no ReaderViewModel (1 sync por trecho, na IO);
HighlightBuilder escolhe palavra + linhas do trecho; PageCanvas desenha (Multiply) com a mesma escala/deslocamento; PageViewState.ensureVisible rola
quando a linha do grifo sai da área visível (RevealPolicy). O NarrationEngine salva (página, indexInPage) a cada trecho, mesmo com a tela fechada;
"Ouvir" retoma do trecho salvo se a página aberta é a da posição salva.

Fase 8.1 (banco do download offline): data/audio/ — AudioDatabase (audio.db, SEPARADO do lector.db: sem migração, biblioteca intocada),
AudioChunkEntity (chave: livro+voz+versão do planner+índice do trecho; MP3 em arquivo, tempos em TimingsCodec), DownloadJobEntity (por livro+voz),
AudioDao (próximo a baixar, retomada, falhas/tentativas, andamento, espaço, apagar por voz/livro). BookIndex.chunkRange(páginas) converte páginas em trechos.
Passo 8.2 do documento original = BookIndex/BookIndexer (6a). Próximo: 8.3 (worker de download).

Fase 8.3 (worker de download): download/ — BookDownloader (lógica pura, testada: 2 em paralelo, escrita atômica .tmp->.mp3, retomada, falha pontual/permanente,
aborta com falhas seguidas, cancelamento), RoomDownloadStore, EdgeSynthesizer (sempre +0%), BookDownloadWorker (WorkManager + notificação Pausar/Cancelar, checa espaço),
DownloadManager (start/pause/resume/cancel/retryFailed/deleteVoice/deleteBook; remover o livro apaga o áudio), DownloadActionReceiver. Vozes: Voices (Antonio/Guy/Alvaro; padrão Antonio).
Botão TEMPORÁRIO "Baixar" na barra da leitura: baixa 10 páginas a partir da atual com a voz Antonio; a linha de baixo mostra x/y. Tela de verdade: 8.5.

Fase 8.4 (tocar do cache): o NarrationEngine, antes de sintetizar um trecho, procura no audio.db (mesma voz + versão do planner) um trecho baixado com arquivo e tempos válidos
(CachePolicy) e toca dele; senão sintetiza on-line como antes (cache parcial funciona; só a parte baixada toca sem internet). Arquivos baixados nunca são apagados pelo motor
(só os temporários de tts-live). A linha de baixo mostra "• offline" quando o trecho vem do cache. NarrationState.fromCache.

Fase 8.5 (tela de áudio): ui/downloads/ — AudioSheet (bottom sheet aberto pelo botão "Áudio" da leitura) + DownloadsViewModel: escolha da voz (Antonio/Guy/Alvaro; vale para a narração
e para os downloads; trocar narrando recomeça o trecho atual), livro inteiro ou páginas X a Y, só Wi-Fi / só carregando, estimativa antes de baixar (trechos, minutos, MB),
progresso com Pausar/Retomar/Cancelar, "Tentar de novo só os que falharam", espaço por voz e "Apagar áudio desta voz". Biblioteca: selo "Disponível offline".
LectorPrefs (DataStore): voz, velocidade (agora persiste), Wi-Fi/carregando. Barra de cima da leitura: [←] título [Áudio] [⋮] (ajuste, zoom e restaurar foram para o menu ⋮;
corrige o botão voltar coberto). Removidos os botões temporários "Texto" e "Baixar" (o diagnóstico de texto agora fica no fim da tela de áudio).
