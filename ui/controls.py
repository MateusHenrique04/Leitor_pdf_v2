import asyncio
import logging
import threading
import time
import tkinter as tk

import data.library as lib
import data.prefs as prefs
from config import FONTS, PDF_RENDER_DPI, WORD_HIGHLIGHT_OPACITY, C
from core import dictionary as dic
from core.duration import format_hms
from core.text import build_chunks
from core.tts import speak, speech_end
from ui.widgets import SeekBar, flat_button

log = logging.getLogger(__name__)

# De quanto em quanto tempo o loop de leitura olha a posição do áudio
# para mover o grifo. 30 ms é bem abaixo do limiar em que o olho percebe
# atraso e custa praticamente nada.
PLAYBACK_POLL_S = 0.03

# Pausa deliberada entre dois trechos. Somada à margem mantida depois da
# última palavra (core.tts.SPEECH_TAIL_MARGIN) e ao silêncio inicial que
# o MP3 seguinte traz de fábrica (~0,25 s), dá a pausa que se ouve entre
# as frases.
INTER_CHUNK_PAUSE_S = 0.05

class ControlsMixin:
    def _build_controls(self, parent):
        # A barra tinha altura fixa de 130px e o bloco do transporte era
        # posicionado com place(), que não conta para o tamanho pedido
        # pelo pai. O bloco mede 157px: centralizado dentro de 130px,
        # ficava 13px cortado em cima (metade do cronômetro) e ~14px
        # cortados embaixo — justamente onde fica o aviso de falha de
        # TTS, que portanto NUNCA aparecia, em nenhum tamanho de janela.
        #
        # Sem altura fixa e com pack(), a barra passa a medir o que o
        # conteúdo precisa.
        bar = tk.Frame(parent, bg=C["panel"])
        bar.grid(row=1, column=0, sticky="ew")

        tk.Frame(bar, bg=C["red"], height=2).pack(fill="x")

        # Transport centralizado
        t = tk.Frame(bar, bg=C["panel"])
        t.pack(pady=(10, 12))

        # Linha do audiolivro: posição · barra clicável · duração total.
        #
        # É o elemento principal da barra. Antes o maior item aqui era o
        # cronômetro da sessão, em 16pt vermelho — a informação MENOS
        # acionável da tela ocupando o maior peso visual, enquanto onde
        # você está no livro ficava em cinza miúdo. Os dois trocaram de
        # lugar: o cronômetro desceu para junto do auto-scroll.
        timeline = tk.Frame(t, bg=C["panel"])
        timeline.pack(pady=(0, 12))

        # width=9 porque o texto mais longo que cabe aqui é "~25:54:37"
        # (um livro de 13h lido a 0,5×) — com 8 o "~12:57:18" saía
        # cortado no "~12:57:1".
        self._pos_lbl = tk.Label(
            timeline, text="--:--", font=FONTS["timeline"],
            bg=C["panel"], fg=C["text"], width=9, anchor="e",
        )
        self._pos_lbl.pack(side="left")

        self._seek_bar = SeekBar(timeline, self._on_time_seek, width=300)
        self._seek_bar.pack(side="left", padx=10)

        self._total_lbl = tk.Label(
            timeline, text="--:--", font=FONTS["timeline"],
            bg=C["panel"], fg=C["text_dim"], width=9, anchor="w",
        )
        self._total_lbl.pack(side="left")

        btns = tk.Frame(t, bg=C["panel"])
        btns.pack()

        flat_button(btns, "⏮", self._prev_page,
                    font=FONTS["icon"], bg=C["border"], fg=C["text_dim"],
                    hover_bg=C["hover"], width=42, height=42).pack(side="left", padx=5)
        flat_button(btns, "◂", self._prev_chunk,
                    font=FONTS["icon_sm"], bg=C["border"], fg=C["text_dim"],
                    hover_bg=C["hover"], width=36, height=36).pack(side="left", padx=3)

        # Play button
        self._play_frame = flat_button(
            btns, "▶", self._toggle_play,
            font=FONTS["icon_lg"], bg=C["red"], fg=C["on_accent"],
            hover_bg=C["red_hot"], width=64, height=64,
        )
        self._play_frame.pack(side="left", padx=10)
        self._play_lbl = self._play_frame.label   # alias — trocado dinamicamente em _toggle_play

        flat_button(btns, "▸", self._next_chunk,
                    font=FONTS["icon_sm"], bg=C["border"], fg=C["text_dim"],
                    hover_bg=C["hover"], width=36, height=36).pack(side="left", padx=3)
        flat_button(btns, "⏭", self._next_page,
                    font=FONTS["icon"], bg=C["border"], fg=C["text_dim"],
                    hover_bg=C["hover"], width=42, height=42).pack(side="left", padx=5)

        # Botão de auto-scroll (preferência persistida — ver data/prefs.py).
        # Sem símbolo antes do texto: a seta que havia aqui não cabe em
        # 8pt — virava um tracinho ilegível — e o estado já é dito pelo
        # próprio "ON"/"OFF" e pela cor do rótulo.
        autoscroll_on = self._autoscroll_enabled
        rodape = tk.Frame(t, bg=C["panel"])
        rodape.pack(pady=(10, 0))

        self._scroll_btn = tk.Label(
            rodape, text=f"auto-scroll  {'ON' if autoscroll_on else 'OFF'}",
            font=FONTS["label"],
            bg=C["border"], fg=C["success"] if autoscroll_on else C["text_dim"],
            cursor="hand2", padx=10, pady=3,
        )
        self._scroll_btn.pack(side="left")

        # Cronômetro da sessão: informação de acompanhamento, não de
        # operação — fica discreto, ao lado.
        self._timer_lbl = tk.Label(
            rodape, text="sessão  00:00:00",
            font=FONTS["label"],
            bg=C["panel"], fg=C["text_dim"], padx=12,
        )
        self._timer_lbl.pack(side="left")
        self._scroll_btn.bind("<Button-1>", lambda _: self._toggle_autoscroll())
        self._scroll_btn.bind("<Enter>",    lambda _: self._scroll_btn.configure(bg=C["border_soft"]))
        self._scroll_btn.bind("<Leave>",    lambda _: self._scroll_btn.configure(bg=C["border"]))

        # Status transitório (falhas de TTS/rede durante a leitura —
        # antes o áudio só parava em silêncio, sem explicar por quê)
        self._status_lbl = tk.Label(
            t, text="",
            font=FONTS["label"],
            bg=C["panel"], fg=C["red_hot"],
        )
        self._status_lbl.pack(pady=(4, 0))

    def _show_transient_status(self, text: str, error: bool = False, ms: int = 4000):
        """Mostra uma mensagem curta perto do transporte (ex.: falha de TTS)
        que some sozinha após `ms` milissegundos."""
        if not self._alive:
            return
        color = C["red_hot"] if error else C["text_dim"]
        self._status_lbl.configure(text=text, fg=color)
        self._status_generation = getattr(self, "_status_generation", 0) + 1
        gen = self._status_generation

        def _clear():
            if self._alive and getattr(self, "_status_generation", 0) == gen:
                self._status_lbl.configure(text="")
        self.after(ms, _clear)

    # ──────────────────────────────────────────────────────────────
    # Barra de tempo do audiolivro
    # ──────────────────────────────────────────────────────────────

    def _book_position_seconds(self) -> float:
        """
        Em que segundo do audiolivro a leitura está.

        A conta é: o ponto em que esta sessão de leitura começou (estimado
        a partir do texto, em `_anchor_seconds`) MAIS o tempo de áudio
        realmente tocado desde então. O tempo tocado não é estimado — vem
        da duração que o próprio TTS reporta para cada trecho.

        A versão anterior calculava a posição inteira como
        `caracteres_lidos ÷ ritmo`. Parecia equivalente, mas tinha um
        defeito observado rodando o app: quando a calibração ajusta o
        ritmo (ver core/duration.py), TODA a linha do tempo reescala, e a
        posição caía ~3% de uma vez — 38 segundos aos 20 minutos de
        livro. Havia uma trava impedindo o rótulo de andar para trás, mas
        ela só trocava o salto por um congelamento de ~40 s até a conta
        alcançar o valor travado.

        Ancorando no tempo tocado, a recalibração passa a afetar só a
        duração TOTAL estimada — a posição anda sempre para a frente, no
        ritmo do relógio, porque é isso que ela de fato mede.
        """
        if self._timeline is None:
            return 0.0
        pos = self._reading_pos
        if pos is None:
            return self._anchor_seconds

        tocado_antes, duracao_trecho = pos
        progresso = 0.0
        if duracao_trecho > 0:
            progresso = max(0.0, min(1.0, self.player.get_pos() / duracao_trecho))
        return self._anchor_seconds + tocado_antes + duracao_trecho * progresso

    def _publish_position(self):
        """
        Fixa a âncora da posição no ponto atual (página + trecho).

        Chamado sempre que a leitura salta: abrir um livro, ±página,
        ±trecho, sumário, clique na barra de tempo. Daqui para a frente a
        posição anda pelo tempo de áudio tocado, não pela estimativa — ver
        _book_position_seconds.
        """
        self._reading_pos = None
        if self._timeline is None:
            self._anchor_seconds = 0.0
            return
        chunks = self._get_current_chunks()
        fracao = 0.0
        if chunks:
            idx = max(0, min(self.current_chunk_idx, len(chunks) - 1))
            pagina_chars = sum(len(c) for c in chunks)
            if pagina_chars:
                fracao = sum(len(c) for c in chunks[:idx]) / pagina_chars
        self._anchor_seconds = self._timeline.seconds_at(self.current_page, fracao)

    def _refresh_timeline(self):
        """Atualiza rótulos e barra. Chamado de segundo em segundo pelo
        cronômetro (_tick_timer)."""
        if self._timeline is None or not self._timeline.total_chars:
            return
        total = self._timeline.total_seconds
        atual = min(self._book_position_seconds(), total)
        self._pos_lbl.configure(text=format_hms(atual))
        # O "~" é honesto: a duração é estimada a partir do texto, porque
        # o áudio só existe depois de sintetizado (ver core/duration.py).
        self._total_lbl.configure(text="~" + format_hms(total))
        self._seek_bar.set_fraction(atual / total if total else 0.0)

    def _on_time_seek(self, fraction: float):
        """Usuário clicou/arrastou a barra: pula para aquele instante."""
        if not self.renderer or self._timeline is None:
            return
        segundos = fraction * self._timeline.total_seconds
        page, fracao_na_pagina = self._timeline.locate(segundos)

        self.current_page = max(0, min(page, self.total_pages - 1))
        chunks = self._get_current_chunks()
        indice = int(fracao_na_pagina * len(chunks)) if chunks else 0
        self.current_chunk_idx = max(0, min(indice, len(chunks) - 1)) if chunks else 0
        self._restart_loop()
        self._refresh_timeline()

    def _is_current_gen(self, gen: int) -> bool:
        """True enquanto `gen` ainda for a geração mais recente do loop de
        leitura — usado por _read_loop para saber se foi invalidado."""
        return self._read_gen.is_current(gen)

    def _start_read_loop(self):
        """Invalida qualquer _read_loop em execução (nova geração) e inicia
        um novo a partir da página/frase correntes. Uma thread antiga nunca
        mais escreve em current_page/current_chunk_idx nem chama
        player.play depois de ver sua geração ficar velha."""
        gen = self._read_gen.next()
        threading.Thread(
            target=lambda: asyncio.run(self._read_loop(gen)),
            daemon=True,
        ).start()

    def _stop_read_loop(self):
        """Invalida a geração atual sem iniciar uma nova (fechar livro/app)."""
        self._read_gen.invalidate()

    async def _read_loop(self, gen: int):
        """
        Para cada página a partir de current_page:
          1. Extrai o texto e monta os trechos (core/text.build_chunks)
          2. Gera o áudio do trecho via TTS (já pré-gerando o seguinte)
          3. Toca, acompanhando a fala com o grifo
          4. Avança para a próxima página

        `gen` é o token de geração desta execução — ver _start_read_loop.

        O que acontece ENTRE dois trechos define se a leitura soa fluida.
        A versão anterior gastava aí ~0,15 s de sleep fixo + ~60 ms de
        busca do grifo do trecho + ~125 ms calculando os retângulos das
        palavras, e ainda esperava o MP3 terminar — e todo MP3 do
        edge-tts tem ~0,9 s de silêncio depois da última palavra. Dava
        mais de um segundo de silêncio a cada frase. Agora o grifo sai
        dos retângulos já calculados (~0 ms), a reprodução para assim que
        a fala acaba (core.tts.speech_end) e só resta uma pausa curta e
        deliberada entre os trechos.
        """
        # Tempo de áudio já tocado nesta execução do loop, somado a partir
        # da duração que o TTS reporta para cada trecho. É o que faz a
        # posição na barra de tempo andar — ver _book_position_seconds.
        # Zera junto com o loop, e o loop reinicia a cada navegação.
        tocado = 0.0

        while self._is_current_gen(gen):
            page = self.current_page
            if page >= self.total_pages:
                break

            # self._ephemeral_highlights é reatribuída (não mutada em
            # lugar) aqui e lida pela thread principal em _draw_image —
            # revisado no item 10 da auditoria: é só uma troca de
            # referência de lista, atômica em CPython, então o pior caso é
            # desenhar um grifo um frame atrasado, nunca uma exceção.
            self._ephemeral_highlights = []
            # Atualiza visual da página
            self.after(0, lambda p=page: self._show_page(p))

            text = self.renderer.text_for_page(page)
            if not text:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

            # Detecta idioma da página para o dicionário
            self._detected_lang = dic.detect_lang(text[:500])

            # Agrupa as frases da página nos trechos enviados ao TTS
            chunks = build_chunks(text)
            if not chunks:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

            start_idx = self.current_chunk_idx
            if start_idx >= len(chunks):
                start_idx = 0


            # speak() nunca lança — já trata suas próprias falhas e retorna
            # (b"", []) para o loop pular o trecho (ver core/tts.py).
            next_audio_task = asyncio.create_task(speak(chunks[start_idx], self._voice, self._speed))

            for i in range(start_idx, len(chunks)):
                if not self._is_current_gen(gen):
                    break

                with self._state_lock:
                    if not self._read_gen.is_current(gen):
                        break
                    self.current_chunk_idx = i
                self._current_text = chunks[i]

                audio, timings = await next_audio_task

                # Pré-gera o próximo chunk enquanto o atual toca
                if i + 1 < len(chunks):
                    next_audio_task = asyncio.create_task(
                        speak(chunks[i + 1], self._voice, self._speed)
                    )

                if not self._is_current_gen(gen):
                    break
                if not audio:
                    self.after(0, lambda: self._show_transient_status(
                        "⚠ Falha ao gerar áudio — verifique sua conexão.", error=True))
                    continue

                # Retângulo de cada palavra que será falada (barato: uma
                # leitura da página, com cache — ver _precompute_word_bboxes)
                word_bboxes = self._precompute_word_bboxes(timings, page)

                # Grifa o trecho inteiro antes de tocar, para nunca haver
                # um instante sem indicação visual do que está sendo lido.
                if not self._highlight_chunk_from_words(word_bboxes):
                    self._highlight_ephemeral()

                if not self._is_current_gen(gen):
                    break
                self.player.play(audio)

                # Instante em que só sobra silêncio no MP3; None quando o
                # TTS não devolveu timings e só resta esperar o fim.
                stop_at = speech_end(timings)

                # Publica onde a leitura está, para a barra de tempo
                # (lida pela thread da UI em _refresh_timeline). É uma
                # troca de referência de tupla — atômica em CPython —,
                # então a UI nunca vê metade de uma atualização.
                #
                # `stop_at + INTER_CHUNK_PAUSE_S` é o tempo de relógio
                # que este trecho consome, e serve também para calibrar a
                # estimativa de duração do livro. Vem dos timings do
                # próprio TTS, e não do relógio: assim uma pausa do
                # usuário no meio do trecho não estraga a medição.
                if stop_at:
                    duracao = stop_at + INTER_CHUNK_PAUSE_S
                    self._reading_pos = (tocado, duracao)
                    tocado += duracao
                    if self._timeline is not None:
                        self._timeline.observe(len(chunks[i]), duracao)

                word_idx = -1
                while (self.player.is_busy() or self.player.is_paused) \
                        and self._is_current_gen(gen):
                    await asyncio.sleep(PLAYBACK_POLL_S)

                    if self.player.is_paused:
                        continue

                    pos = self.player.get_pos()
                    if stop_at is not None and pos >= stop_at:
                        break
                    if not word_bboxes:
                        continue

                    new_idx = word_idx
                    for wi, (wb_start, wb_end, _wb_rects) in enumerate(word_bboxes):
                        if wb_start <= pos < wb_end:
                            new_idx = wi
                            break
                        elif pos >= wb_end and wi == len(word_bboxes) - 1:
                            new_idx = wi

                    if new_idx != word_idx and new_idx >= 0:
                        word_idx = new_idx
                        rects = word_bboxes[word_idx][2]
                        if rects:
                            self._ephemeral_highlights = [
                                {**r, "color": C["info"], "opacity": WORD_HIGHLIGHT_OPACITY}
                                for r in rects
                            ]
                            if self._alive:
                                self.after(0, self._follow_highlight)

                # Pausa curta e deliberada entre trechos: junto com a
                # margem de core.tts.SPEECH_TAIL_MARGIN e o silêncio que o
                # próprio MP3 seguinte traz no início, dá ~0,4 s — a
                # duração de uma pausa natural entre frases.
                if self._is_current_gen(gen):
                    await asyncio.sleep(INTER_CHUNK_PAUSE_S)

            if self._is_current_gen(gen):
                self.current_page += 1
                self.current_chunk_idx = 0
                if self.current_page >= self.total_pages and self.current_path:
                    lib.mark_finished(self.current_path, True)
                    self._update_finished_btn()
                    self._refresh_lib()

    def _restart_loop(self):
        """Para o loop atual e reinicia imediatamente da página/frase
        correntes — cada chamada gera um novo token, então a thread antiga
        (mesmo que ainda esteja bloqueada num await de rede) nunca mais
        escreve estado nem toca áudio depois disso."""
        if not self._alive:
            return
        self.player.stop()
        # Toda navegação (±página, ±trecho, sumário, barra de páginas,
        # barra de tempo) passa por aqui, então é o lugar certo para
        # reancorar a barra de tempo no ponto novo.
        self._publish_position()
        self._start_read_loop()

    def _toggle_play(self):
        if not self.renderer:
            return
        if self.player.is_paused:
            self.player.unpause()
            self._play_lbl.configure(text="⏸")
            self._timer_running = True
            self._last_tick = time.time()
        else:
            self.player.pause()
            self._play_lbl.configure(text="▶")
            self._timer_running = False
            self._save_session()

    def _next_page(self):
        if not self.renderer:
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.current_chunk_idx = 0
            self._restart_loop()

    def _prev_page(self):
        if not self.renderer:
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.current_chunk_idx = 0
            self._restart_loop()

    def _get_current_chunks(self) -> list[str]:
        """Retorna os trechos (chunks) da página atual, exatamente como o
        loop de leitura os monta — os botões ◂/▸ precisam contar os mesmos
        trechos que estão sendo lidos."""
        if not self.renderer:
            return []
        text = self.renderer.text_for_page(self.current_page)
        if not text:
            return []
        return build_chunks(text)

    def _next_chunk(self):
        """Pula para a próxima frase. Se for a última, avança para a próxima página."""
        if not self.renderer:
            return
        chunks = self._get_current_chunks()
        if chunks and self.current_chunk_idx < len(chunks) - 1:
            self.current_chunk_idx += 1
            self._restart_loop()
        else:
            # Última frase da página — avança a página
            self._next_page()

    def _prev_chunk(self):
        """Volta para a frase anterior. Se for a primeira, volta à página anterior na última frase."""
        if not self.renderer:
            return
        if self.current_chunk_idx > 0:
            self.current_chunk_idx -= 1
            self._restart_loop()
        elif self.current_page > 0:
            # Primeira frase da página — volta à página anterior, na última frase
            self.current_page -= 1
            chunks = self._get_current_chunks()
            self.current_chunk_idx = max(0, len(chunks) - 1)
            self._restart_loop()

    def _on_seek(self, _event):
        self._dragging = False
        if not self.renderer:
            return
        target = int(self._prog_var.get()) - 1   # converte para 0-indexed
        target = max(0, min(target, self.total_pages - 1))
        self.current_page = target
        self.current_chunk_idx = 0
        self._restart_loop()

    def _toggle_autoscroll(self):
        """Liga/desliga o scroll automático (preferência persistida)."""
        self._autoscroll_enabled = not self._autoscroll_enabled
        prefs.set_value("autoscroll", self._autoscroll_enabled)
        if self._autoscroll_enabled:
            self._scroll_btn.configure(text="auto-scroll  ON",  fg=C["success"])
        else:
            self._scroll_btn.configure(text="auto-scroll  OFF", fg=C["text_dim"])

    def _auto_scroll_to_highlight(self):
        """
        Ajusta _pan_y para centralizar verticalmente o grifo efêmero atual.
        Funciona com o sistema existente de pan/zoom — não usa yview.
        """
        if not self._alive or not self._autoscroll_enabled \
                or not self._ephemeral_highlights or not self._cur_img:
            return
        try:
            # Centraliza no topo do grifo atual — evita pular para o meio
            # de múltiplos bboxes espalhados (causava autoscroll errático)
            first = min(self._ephemeral_highlights, key=lambda h: h["y0"])
            y_center_pdf = (first["y0"] + first["y1"]) / 2.0

            # Converte coordenadas PDF (pontos) → pixels na imagem renderizada
            zoom_pdf = PDF_RENDER_DPI / 72.0
            y_center_img = y_center_pdf * zoom_pdf

            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            if cw < 10 or ch < 10:
                return
            _iw, ih = self._cur_img.size
            scale = self._page_scale()

            # Posição Y do centro do grifo no canvas SEM nenhum pan aplicado
            y_on_canvas_no_pan = (ch - ih * scale) / 2 + y_center_img * scale

            # Pan necessário para trazer esse ponto ao centro vertical do canvas
            desired_pan_y = ch / 2 - y_on_canvas_no_pan

            # Aplica suavização e limita ao mesmo range do desenho
            _max_px, max_py = self._max_pan()
            new_pan_y = int(self._pan_y * 0.3 + desired_pan_y * 0.7)
            self._pan_y = max(-max_py, min(max_py, new_pan_y))
        except Exception as e:
            log.debug("auto_scroll erro (ignorado): %s", e)

    def _follow_highlight(self):
        """Acompanha o grifo atual: ajusta o pan (se o auto-scroll estiver
        ligado) e redesenha UMA vez.

        Antes cada mudança de grifo agendava _redraw e, logo depois,
        _auto_scroll_to_highlight — que redesenhava de novo. Eram dois
        desenhos completos da página por palavra falada."""
        self._auto_scroll_to_highlight()
        self._redraw()
