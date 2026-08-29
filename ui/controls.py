import asyncio
import logging
import re
import threading
import time
import tkinter as tk

import data.library as lib
import data.prefs as prefs
from config import FONTS, PDF_RENDER_DPI, C
from core import dictionary as dic
from core.tts import speak
from ui.widgets import flat_button

log = logging.getLogger(__name__)

class ControlsMixin:
    def _build_controls(self, parent):
        bar = tk.Frame(parent, bg=C["panel"], height=130)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_propagate(False)

        tk.Frame(bar, bg=C["red"], height=2).place(x=0, y=0, relwidth=1)

        # Transport centralizado
        t = tk.Frame(bar, bg=C["panel"])
        t.place(relx=0.5, rely=0.5, anchor="center")

        self._timer_lbl = tk.Label(
            t, text="00:00:00",
            font=FONTS["timer"],
            bg=C["panel"], fg=C["red"],
        )
        self._timer_lbl.pack(pady=(0, 8))

        btns = tk.Frame(t, bg=C["panel"])
        btns.pack()

        flat_button(btns, "⏮", self._prev_page,
                    font=FONTS["icon"], bg=C["border"], fg="#888",
                    hover_bg=C["hover"], width=42, height=42).pack(side="left", padx=5)
        flat_button(btns, "◂", self._prev_chunk,
                    font=FONTS["icon_sm"], bg=C["border"], fg="#888",
                    hover_bg=C["hover"], width=36, height=36).pack(side="left", padx=3)

        # Play button
        self._play_frame = flat_button(
            btns, "▶", self._toggle_play,
            font=("Georgia", 22), bg=C["red"], fg="#fff",
            hover_bg=C["red_hot"], width=64, height=64,
        )
        self._play_frame.pack(side="left", padx=10)
        self._play_lbl = self._play_frame.label   # alias — trocado dinamicamente em _toggle_play

        flat_button(btns, "▸", self._next_chunk,
                    font=FONTS["icon_sm"], bg=C["border"], fg="#888",
                    hover_bg=C["hover"], width=36, height=36).pack(side="left", padx=3)
        flat_button(btns, "⏭", self._next_page,
                    font=FONTS["icon"], bg=C["border"], fg="#888",
                    hover_bg=C["hover"], width=42, height=42).pack(side="left", padx=5)

        # Botão de auto-scroll (preferência persistida — ver data/prefs.py)
        autoscroll_on = self._autoscroll_enabled
        self._scroll_btn = tk.Label(
            t, text=f"⇕ auto-scroll  {'ON' if autoscroll_on else 'OFF'}",
            font=FONTS["label"],
            bg=C["border"], fg=C["success"] if autoscroll_on else C["text_dim"],
            cursor="hand2", padx=10, pady=3,
        )
        self._scroll_btn.pack(pady=(8, 0))
        self._scroll_btn.bind("<Button-1>", lambda _: self._toggle_autoscroll())
        self._scroll_btn.bind("<Enter>",    lambda _: self._scroll_btn.configure(bg="#333"))
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

    async def _read_loop(self):
        """
        Para cada página a partir de current_page:
          1. Extrai texto
          2. Gera áudio via TTS
          3. Toca o áudio
          4. Avança para a próxima página
        """
        while not self._stop.is_set():
            page = self.current_page
            if page >= self.total_pages:
                break

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

            # Divide em frases ou linhas
            chunks = [c.strip() for c in re.split(r'(?<=[.!?])\s+|\n', text) if c.strip()]
            if not chunks:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

            start_idx = self.current_chunk_idx
            if start_idx >= len(chunks):
                start_idx = 0

            async def get_audio(text_chunk):
                try:
                    audio, timings = await speak(text_chunk, self._voice, self._speed)
                    return audio, timings
                except Exception as e:
                    log.error(f"TTS erro: {e}")
                    return b"", []

            next_audio_task = asyncio.create_task(get_audio(chunks[start_idx]))

            for i in range(start_idx, len(chunks)):
                if self._stop.is_set():
                    break

                with self._state_lock:
                    self.current_chunk_idx = i
                self._current_text = chunks[i]

                audio, timings = await next_audio_task

                # Pré-gera o próximo chunk enquanto o atual toca
                if i + 1 < len(chunks):
                    next_audio_task = asyncio.create_task(get_audio(chunks[i + 1]))

                if self._stop.is_set():
                    break
                if not audio:
                    self.after(0, lambda: self._show_transient_status(
                        "⚠ Falha ao gerar áudio — verifique sua conexão.", error=True))
                    continue

                # Grifa o chunk completo imediatamente (garante fundo azul sempre)
                self._highlight_ephemeral()

                # Pré-calcula bboxes palavra-por-palavra (melhoria opcional)
                word_bboxes = self._precompute_word_bboxes(
                    chunks, i, timings, self.current_page
                )

                self.player.play(audio)

                # Loop de reprodução — word-by-word se houver bboxes,
                # senão mantém o grifo de chunk já aplicado acima
                word_idx = -1
                while (self.player.is_busy() or self.player.is_paused) \
                      and not self._stop.is_set():
                    await asyncio.sleep(0.03)

                    if self.player.is_paused or not word_bboxes:
                        continue

                    pos = self.player.get_pos()
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
                                {**r, "color": C["info"], "opacity": 0.4}
                                for r in rects
                            ]
                            if self._alive:
                                self.after(0, self._redraw)
                                self.after(0, self._auto_scroll_to_highlight)

                # Delay de segurança (race condition pygame)
                if not self._stop.is_set():
                    await asyncio.sleep(0.15)

            if not self._stop.is_set():
                self.current_page += 1
                self.current_chunk_idx = 0
                if self.current_page >= self.total_pages and self.current_path:
                    lib.mark_finished(self.current_path, True)
                    self._update_finished_btn()
                    self._refresh_lib()

    def _restart_loop(self):
        """Para o loop atual e reinicia da página corrente."""
        self._stop.set()
        self.player.stop()
        if self._alive:
            self.after(250, self._do_restart)

    def _do_restart(self):
        if not self._alive:
            return
        self._stop.clear()
        threading.Thread(
            target=lambda: asyncio.run(self._read_loop()),
            daemon=True,
        ).start()

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
        """Retorna a lista de frases (chunks) da página atual."""
        if not self.renderer:
            return []
        text = self.renderer.text_for_page(self.current_page)
        if not text:
            return []
        return [c.strip() for c in re.split(r'(?<=[.!?])\s+|\n', text) if c.strip()]

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
        prefs.set("autoscroll", self._autoscroll_enabled)
        if self._autoscroll_enabled:
            self._scroll_btn.configure(text="⇕ auto-scroll  ON",  fg=C["success"])
        else:
            self._scroll_btn.configure(text="⇕ auto-scroll  OFF", fg=C["text_dim"])

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
            iw, ih = self._cur_img.size
            base_scale = min(cw / iw, ch / ih)
            scale = base_scale * self._zoom

            # Posição Y do centro do grifo no canvas SEM nenhum pan aplicado
            y_on_canvas_no_pan = (ch - ih * scale) / 2 + y_center_img * scale

            # Pan necessário para trazer esse ponto ao centro vertical do canvas
            desired_pan_y = ch / 2 - y_on_canvas_no_pan

            # Aplica suavização e limita ao range de pan permitido
            max_py = max(0, (int(ih * scale) - ch) // 2 + int(ih * scale) // 4)
            new_pan_y = int(self._pan_y * 0.3 + desired_pan_y * 0.7)
            self._pan_y = max(-max_py, min(max_py, new_pan_y))
            self._redraw()
        except Exception as e:
            log.debug(f"auto_scroll erro (ignorado): {e}")
