"""
ui/reading.py — o loop de leitura (TTS + grifo sincronizado), a navegação e a
barra de tempo do audiolivro.

A lógica é a mesma da versão Tk; o que mudou é só a ponte com a interface:
a thread de leitura não chama mais `self.after(0, ...)`, ela emite sinais Qt
(sig_*), que o Qt entrega na thread da UI.
"""
import asyncio
import logging
import threading
import time

import data.library as lib
import data.prefs as prefs
from config import WORD_HIGHLIGHT_OPACITY, C
from core import dictionary as dic
from core.duration import format_hms
from core.text import build_chunks
from core.tts import speak, speech_end

log = logging.getLogger(__name__)

# De quanto em quanto tempo o loop de leitura olha a posição do áudio para
# mover o grifo. 30 ms está bem abaixo do limiar em que o olho percebe atraso.
PLAYBACK_POLL_S = 0.03

# Pausa deliberada entre dois trechos. Somada à margem mantida depois da
# última palavra (core.tts.SPEECH_TAIL_MARGIN) e ao silêncio inicial do MP3
# seguinte (~0,25 s), dá a pausa que se ouve entre as frases.
INTER_CHUNK_PAUSE_S = 0.05


class ReadingMixin:
    # ──────────────────────────────────────────────────────────────
    # Barra de tempo do audiolivro
    # ──────────────────────────────────────────────────────────────

    def _book_position_seconds(self) -> float:
        """
        Em que segundo do audiolivro a leitura está: o ponto em que esta
        sessão de leitura começou (estimado do texto, `_anchor_seconds`) MAIS
        o tempo de áudio realmente tocado desde então (reportado pelo próprio
        TTS). Assim a recalibração da estimativa só afeta a duração TOTAL; a
        posição anda sempre para a frente, no ritmo do relógio.
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
        """Fixa a âncora da posição no ponto atual (página + trecho). Chamado
        sempre que a leitura salta: abrir livro, ±página, ±trecho, sumário,
        clique na barra de tempo."""
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
        """Atualiza rótulos e barra (chamado pelo relógio da janela)."""
        if self._timeline is None or not self._timeline.total_chars:
            return
        total = self._timeline.total_seconds
        atual = min(self._book_position_seconds(), total)
        # O "~" é honesto: a duração é estimada do texto, porque o áudio só
        # existe depois de sintetizado (ver core/duration.py).
        self.transport.set_timeline(
            format_hms(atual), "~" + format_hms(total), atual / total if total else 0.0)

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
        self._follow_suppressed = False
        self._restart_loop()
        self._refresh_timeline()

    # ──────────────────────────────────────────────────────────────
    # Loop de leitura
    # ──────────────────────────────────────────────────────────────

    def _is_current_gen(self, gen: int) -> bool:
        return self._read_gen.is_current(gen)

    def _start_read_loop(self):
        """Invalida qualquer _read_loop em execução (nova geração) e inicia um
        novo a partir da página/frase correntes. Uma thread antiga nunca mais
        escreve estado nem toca áudio depois de ver sua geração ficar velha."""
        gen = self._read_gen.next()
        threading.Thread(
            target=lambda: asyncio.run(self._read_loop(gen)),
            daemon=True,
        ).start()

    def _stop_read_loop(self):
        """Invalida a geração atual sem iniciar outra (fechar livro/app)."""
        self._read_gen.invalidate()

    async def _read_loop(self, gen: int):
        """
        Para cada página a partir de current_page:
          1. Extrai o texto e monta os trechos (core/text.build_chunks)
          2. Gera o áudio do trecho via TTS (já pré-gerando o seguinte)
          3. Toca, acompanhando a fala com o grifo
          4. Avança para a próxima página

        O que acontece ENTRE dois trechos define se a leitura soa fluida: o
        grifo sai de retângulos já calculados, a reprodução para assim que a
        fala acaba (core.tts.speech_end) e só resta uma pausa curta e
        deliberada entre os trechos.
        """
        # Tempo de áudio já tocado nesta execução do loop, somado da duração
        # que o TTS reporta para cada trecho — é o que faz a posição andar.
        tocado = 0.0

        while self._is_current_gen(gen):
            page = self.current_page
            if page >= self.total_pages:
                break

            self._ephemeral_highlights = []
            self._word_highlights = []
            self.sig_show_page.emit(page)

            text = self.renderer.text_for_page(page)
            if not text:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

            # Detecta o idioma da página para o dicionário
            self._detected_lang = dic.detect_lang(text[:500])

            chunks = build_chunks(text)
            if not chunks:
                self.current_page += 1
                self.current_chunk_idx = 0
                continue

            start_idx = self.current_chunk_idx
            if start_idx >= len(chunks):
                start_idx = 0

            # speak() nunca lança — trata as próprias falhas e devolve
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

                # Pré-gera o próximo trecho enquanto o atual toca
                if i + 1 < len(chunks):
                    next_audio_task = asyncio.create_task(
                        speak(chunks[i + 1], self._voice, self._speed)
                    )

                if not self._is_current_gen(gen):
                    break
                if not audio:
                    self.sig_status.emit("⚠ Falha ao gerar áudio — verifique sua conexão.", True)
                    continue

                # Retângulo de cada palavra que será falada (barato: uma
                # leitura da página, com cache)
                word_bboxes = self._precompute_word_bboxes(timings, page)

                # Grifa o trecho inteiro antes de tocar, para nunca haver um
                # instante sem indicação visual do que está sendo lido.
                if not self._highlight_chunk_from_words(word_bboxes):
                    self._highlight_ephemeral()

                if not self._is_current_gen(gen):
                    break
                self.player.play(audio)

                # Instante em que só sobra silêncio no MP3; None quando o TTS
                # não devolveu timings e só resta esperar o fim.
                stop_at = speech_end(timings)

                # Publica onde a leitura está, para a barra de tempo. É uma
                # troca de referência de tupla (atômica em CPython). O tempo
                # que este trecho consome também calibra a estimativa de
                # duração do livro — vem dos timings do TTS, não do relógio,
                # então uma pausa do usuário não estraga a medição.
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
                            # O fundo do trecho continua; só a palavra muda.
                            self._word_highlights = [
                                {**r, "color": C["info"], "opacity": WORD_HIGHLIGHT_OPACITY}
                                for r in rects
                            ]
                            if self._alive:
                                self.sig_follow.emit()

                if self._is_current_gen(gen):
                    await asyncio.sleep(INTER_CHUNK_PAUSE_S)

            if self._is_current_gen(gen):
                self.current_page += 1
                self.current_chunk_idx = 0
                if self.current_page >= self.total_pages and self.current_path:
                    lib.mark_finished(self.current_path, True)
                    self.sig_lib_changed.emit()

    def _restart_loop(self):
        """Para o loop atual e reinicia da página/frase correntes — cada
        chamada gera um novo token, então a thread antiga nunca mais escreve
        estado nem toca áudio depois disso."""
        if not self._alive:
            return
        self.player.stop()
        # Toda navegação passa por aqui: é o lugar de reancorar a barra de tempo.
        self._publish_position()
        self._start_read_loop()

    # ──────────────────────────────────────────────────────────────
    # Acompanhar a voz na tela (thread da UI)
    # ──────────────────────────────────────────────────────────────

    def _follow_highlight(self):
        """Pinta o trecho e a palavra atuais e, com o auto-scroll ligado,
        mantém o texto lido à vista (rolagem suave, sem balançar)."""
        chunk = list(self._ephemeral_highlights)
        words = list(self._word_highlights)
        self.view.set_chunk_highlights(chunk)
        self.view.set_word_highlights(words)
        if self._autoscroll_enabled and not self._follow_suppressed:
            target = words or chunk
            if target:
                self.view.follow(min(target, key=lambda h: h["y0"]))

    # ──────────────────────────────────────────────────────────────
    # Comandos
    # ──────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if not self.renderer:
            return
        if self.player.is_paused:
            self.player.unpause()
            self.transport.set_playing(True)
            self._timer_running = True
            self._last_tick = time.time()
            self._follow_suppressed = False
        else:
            self.player.pause()
            self.transport.set_playing(False)
            self._timer_running = False
            self._save_session()

    def _next_page(self):
        if not self.renderer:
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.current_chunk_idx = 0
            self._follow_suppressed = False
            self._restart_loop()

    def _prev_page(self):
        if not self.renderer:
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.current_chunk_idx = 0
            self._follow_suppressed = False
            self._restart_loop()

    def _get_current_chunks(self) -> list[str]:
        """Trechos da página atual, exatamente como o loop os monta — os
        botões de frase precisam contar os mesmos trechos que são lidos."""
        if not self.renderer:
            return []
        text = self.renderer.text_for_page(self.current_page)
        if not text:
            return []
        return build_chunks(text)

    def _next_chunk(self):
        """Próxima frase; na última, avança a página."""
        if not self.renderer:
            return
        chunks = self._get_current_chunks()
        if chunks and self.current_chunk_idx < len(chunks) - 1:
            self.current_chunk_idx += 1
            self._follow_suppressed = False
            self._restart_loop()
        else:
            self._next_page()

    def _prev_chunk(self):
        """Frase anterior; na primeira, volta à última frase da página anterior."""
        if not self.renderer:
            return
        if self.current_chunk_idx > 0:
            self.current_chunk_idx -= 1
            self._follow_suppressed = False
            self._restart_loop()
        elif self.current_page > 0:
            self.current_page -= 1
            chunks = self._get_current_chunks()
            self.current_chunk_idx = max(0, len(chunks) - 1)
            self._follow_suppressed = False
            self._restart_loop()

    def _on_page_seek(self, page_1based: int):
        """O usuário soltou o slider de páginas."""
        if not self.renderer:
            return
        self.current_page = max(0, min(page_1based - 1, self.total_pages - 1))
        self.current_chunk_idx = 0
        self._follow_suppressed = False
        self._restart_loop()

    def _on_page_step(self, step: int):
        """Roda do mouse numa página que não rola: vira de página."""
        if step > 0:
            self._next_page()
        else:
            self._prev_page()

    def _on_autoscroll_toggled(self, on: bool):
        self._autoscroll_enabled = on
        prefs.set_value("autoscroll", on)
