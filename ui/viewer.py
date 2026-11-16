import logging
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

import data.highlights as highlights
import data.library as lib
import data.prefs as prefs
from config import DEFAULT_HIGHLIGHT_COLOR, FONTS, PDF_RENDER_DPI, C
from ui.widgets import flat_button

log = logging.getLogger(__name__)

class ViewerMixin:
    def _build_center(self):
        center = tk.Frame(self, bg=C["bg"])
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_rowconfigure(0, weight=1)   # visualizador expande
        center.grid_rowconfigure(1, weight=0)   # controles fixos
        center.grid_columnconfigure(0, weight=1)

        # ── Visualizador de página ──
        viewer = tk.Frame(center, bg=C["bg"])
        viewer.grid(row=0, column=0, sticky="nsew")
        viewer.grid_rowconfigure(0, weight=0)  # topbar
        viewer.grid_rowconfigure(1, weight=1)  # imagem
        viewer.grid_columnconfigure(0, weight=1)

        # Topbar: nome + página + slider
        topbar = tk.Frame(viewer, bg=C["panel"])
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        tk.Frame(topbar, bg=C["red"], height=2).grid(
            row=0, column=0, columnspan=3, sticky="ew")

        self._title_lbl = tk.Label(
            topbar, text="Nenhum livro aberto",
            font=("Georgia", 11, "bold"),
            bg=C["panel"], fg=C["text"],
            anchor="w", padx=18, pady=7,
        )
        self._title_lbl.grid(row=1, column=0, sticky="w")

        # Botões de zoom na topbar
        zoom_row = tk.Frame(topbar, bg=C["panel"])
        zoom_row.grid(row=1, column=1, sticky="e", padx=8)

        def _zoom_btn(parent, text, cmd):
            b = flat_button(parent, text, cmd,
                             font=FONTS["symbol"], bg=C["border"], fg=C["text"],
                             hover_bg=C["border_soft"], padx=8, pady=2)
            b.pack(side="left", padx=2)
            return b

        _zoom_btn(zoom_row, "−", self._zoom_out)
        self._zoom_lbl = tk.Label(zoom_row, text="100%",
                                   font=FONTS["mono_bold"],
                                   bg=C["panel"], fg=C["text_dim"],
                                   width=5, anchor="center")
        self._zoom_lbl.pack(side="left")
        _zoom_btn(zoom_row, "＋", self._zoom_in)

        # Alterna entre ajustar à largura e ajustar à página inteira, e
        # zera o zoom. O rótulo diz o modo ATUAL — um ícone sozinho não
        # conseguiria comunicar qual dos dois está valendo.
        self._fit_btn = flat_button(
            zoom_row, "", self._toggle_fit_mode,
            font=FONTS["mono_bold"], bg=C["border"], fg=C["text"],
            hover_bg=C["border_soft"], padx=8, pady=2)
        self._fit_btn.pack(side="left", padx=2)
        self._update_fit_btn()

        # Modo leitura: esconde biblioteca e painel de ajustes (Tab).
        self._reading_btn = flat_button(
            zoom_row, "⛶", self._toggle_reading_mode,
            font=FONTS["symbol"], bg=C["border"], fg=C["text"],
            hover_bg=C["border_soft"], padx=8, pady=2)
        self._reading_btn.pack(side="left", padx=(8, 2))

        self._page_lbl = tk.Label(
            topbar, text="",
            font=("Courier", 10, "bold"),
            bg=C["panel"], fg=C["red_text"],
            anchor="e", padx=18,
        )
        self._page_lbl.grid(row=1, column=2, sticky="e")

        self._prog_var = tk.DoubleVar(value=0)
        self._prog_slider = tk.Scale(
            topbar, variable=self._prog_var,
            from_=1, to=1, orient="horizontal",
            bg=C["panel"], troughcolor=C["border"],
            activebackground=C["red_hot"],
            highlightthickness=0, bd=0,
            showvalue=0, sliderrelief="flat",
            sliderlength=14, width=5,
            fg=C["red"],
        )
        self._prog_slider.grid(row=2, column=0, columnspan=3, sticky="ew")
        self._prog_slider.bind("<Button-1>",        lambda _: setattr(self, "_dragging", True))
        self._prog_slider.bind("<ButtonRelease-1>", self._on_seek)

        # Barra de busca (oculta por padrão, Ctrl+F para abrir)
        self._search_bar = tk.Frame(viewer, bg=C["panel"])
        self._search_bar.grid(row=1, column=0, sticky="ew")
        self._search_bar.grid_remove()   # oculta
        viewer.grid_rowconfigure(1, weight=0)
        viewer.grid_rowconfigure(2, weight=1)

        tk.Label(self._search_bar, text="🔍", font=FONTS["symbol"],
                 bg=C["panel"], fg=C["text_dim"], padx=8).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_entry = tk.Entry(
            self._search_bar, textvariable=self._search_var,
            font=("Georgia", 11), bg=C["panel_alt"], fg=C["text"],
            insertbackground=C["text"], relief="flat", bd=4,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, pady=6)
        self._search_count_lbl = tk.Label(
            self._search_bar, text="", font=("Courier", 9),
            bg=C["panel"], fg=C["text_dim"], padx=8,
        )
        self._search_count_lbl.pack(side="left")
        for txt, cmd in [("▲", lambda: self._search_navigate(-1)),
                         ("▼", lambda: self._search_navigate(+1))]:
            b = tk.Label(self._search_bar, text=txt, font=FONTS["symbol"],
                         bg=C["border"], fg=C["text"], cursor="hand2", padx=8, pady=4)
            b.pack(side="left", padx=2, pady=4)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, bb=b: bb.configure(bg=C["border_soft"]))
            b.bind("<Leave>", lambda e, bb=b: bb.configure(bg=C["border"]))
        close_s = tk.Label(self._search_bar, text="✕", font=FONTS["symbol"],
                           bg=C["panel"], fg=C["text_dim"], cursor="hand2", padx=10)
        close_s.pack(side="right")
        close_s.bind("<Button-1>", lambda _: self._close_search())
        self._search_var.trace_add("write", lambda *_: self._do_search())
        self._search_entry.bind("<Return>",   lambda _: self._search_navigate(+1))
        self._search_entry.bind("<Shift-Return>", lambda _: self._search_navigate(-1))
        self._search_entry.bind("<Escape>",   lambda _: self._close_search())

        # Resultados de busca
        self._search_results: list[dict] = []   # lista de {page, bbox}
        self._search_result_idx = -1

        # Canvas para exibir a imagem da página
        self._canvas = tk.Canvas(
            viewer, bg=C["canvas_bg"],
            highlightthickness=0, bd=0,
        )
        self._canvas.grid(row=2, column=0, sticky="nsew")
        self._canvas.bind("<Configure>",      self._on_canvas_resize)
        self._canvas.bind("<MouseWheel>",     self._on_mousewheel)      # Windows
        self._canvas.bind("<Button-4>",       self._on_mousewheel)      # Linux scroll up
        self._canvas.bind("<Button-5>",       self._on_mousewheel)      # Linux scroll down
        self._canvas.bind("<ButtonPress-1>",  self._on_canvas_press)
        self._canvas.bind("<B1-Motion>",      self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>",self._on_canvas_release)
        self._canvas.bind("<Button-3>",       self._on_canvas_right_click)
        self._canvas_img_ref = None

        # ── Barra de controles ──
        self._build_controls(center)

    def _toggle_reading_mode(self):
        """Liga/desliga o modo leitura (atalho: Tab)."""
        self._reading_mode = not self._reading_mode
        prefs.set_value("reading_mode", self._reading_mode)
        self._apply_reading_mode()

    def _apply_reading_mode(self):
        """
        Esconde ou mostra os painéis laterais.

        Durante a leitura, biblioteca e ajustes ficam ocupando ~40% da
        janela sem serem tocados. Escondê-los leva a página de ~46% para
        ~80% da tela. Os widgets continuam existindo — só saem do grid —,
        então nada precisa ser reconstruído nem perde estado.
        """
        if self._reading_mode:
            self._sidebar_frame.grid_remove()
            self._right_frame.grid_remove()
        else:
            self._sidebar_frame.grid()
            self._right_frame.grid()
        self._reading_btn.label.configure(
            fg=C["red_text"] if self._reading_mode else C["text"])
        # O canvas mudou de tamanho: redesenha já, sem esperar o
        # <Configure> (que pode demorar um frame e piscar).
        self.after_idle(self._redraw)

    def _max_pan(self) -> tuple[int, int]:
        """
        Até onde o pan pode ir em cada eixo.

        O limite é exatamente o que mantém a página cobrindo o canvas: se
        ela é maior que a tela, dá para percorrê-la inteira; se é menor,
        fica centralizada e não há o que arrastar.

        O limite anterior permitia ir um quarto da página ALÉM disso. Com
        o ajuste por largura isso virou defeito visível: o auto-scroll
        centraliza o grifo, e quando o trecho lido estava perto do topo da
        página ele empurrava a página para baixo e abria uma faixa preta
        acima dela.
        """
        if self._cur_img is None:
            return 0, 0
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw, ih = self._cur_img.size
        escala = self._page_scale()
        return (max(0, (int(iw * escala) - cw) // 2),
                max(0, (int(ih * escala) - ch) // 2))

    def _page_scale(self) -> float:
        """
        Fator que leva a imagem renderizada da página ao tamanho de tela.

        É `ajuste × zoom`, onde o ajuste depende do modo:

          "largura" — a página ocupa toda a largura do canvas e transborda
                      para baixo; o auto-scroll acompanha a voz. É o padrão
                      porque é o que entrega o texto no maior tamanho.
          "pagina"  — a página inteira cabe na tela.

        Antes só existia o modo "pagina", e com ele uma folha retrato num
        canvas deitado fica limitada pela ALTURA: sobravam tarjas vazias
        enormes dos dois lados. Medido, a página ficava com 15% a 22% da
        janela, e o vazio em volta dela chegava a 36% — mais do que a
        própria página. O livro é o produto; ele precisa do espaço.

        Quatro lugares precisavam desta conta (desenho, conversão de
        clique para coordenada do PDF, auto-scroll e salto para resultado
        de busca) e cada um tinha a sua cópia — por isso virou método.
        """
        if self._cur_img is None:
            return 1.0
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw, ih = self._cur_img.size
        if cw < 10 or ch < 10 or not iw or not ih:
            return 1.0
        ajuste = cw / iw if self._fit_mode == "largura" else min(cw / iw, ch / ih)
        return ajuste * self._zoom

    def _show_page(self, n: int):
        """
        Renderiza e exibe a página n no canvas.

        Só exibe: quem decide em que página a leitura está é o loop de
        leitura (ui/controls.py) e os botões de navegação. Este método
        chegou a atribuir `self.current_page = n`, e isso abria uma
        corrida — o loop de leitura o agenda com `after(0, ...)`, e numa
        sequência de páginas quase vazias (folhas de rosto, aberturas de
        capítulo) o loop avança várias páginas antes de o callback rodar;
        ao rodar, ele puxava a leitura de volta para uma página já
        passada. Um callback atrasado agora simplesmente não faz nada.
        """
        if not self.renderer or not (0 <= n < self.total_pages):
            return
        if n != self.current_page:
            return

        self._pan_x = self._pan_y = 0   # reseta pan ao mudar de página
        # Com zoom > 100% (padrão), centralizar verticalmente corta o topo
        # da página — onde o texto normalmente começa — deixando a tela
        # com aparência de "página em branco" até o auto-scroll da leitura
        # alcançar o texto. Pede pro próximo _draw_image ancorar no topo
        # em vez de centralizar (só na primeira renderização da página).
        self._pan_pending_top = True
        self._ephemeral_highlights = []  # limpa grifo da frase anterior
        self._eph_y_cursor = 0.0         # reseta cursor de posição sequencial
        lib.save_position(self.current_path, n, self.current_chunk_idx)

        # Atualiza label e slider sem disparar seek
        self._prog_var.set(n + 1)
        self._page_lbl.configure(text=f"PÁG. {n + 1} / {self.total_pages}")

        # Renderiza em thread separada para não travar a UI
        threading.Thread(
            target=self._render_and_draw, args=(n, self.renderer), daemon=True,
        ).start()

    def _render_and_draw(self, n: int, renderer):
        """Roda em background — renderiza a imagem e agenda o draw na UI.

        `renderer` é o renderer vigente no momento em que a renderização
        foi pedida (não `self.renderer`, que pode já ter sido trocado se o
        usuário virou de página ou de livro rápido — ver _draw_image_if_current).
        """
        try:
            img = renderer.render_page(n)
            if self._alive:
                self.after(0, lambda i=img: self._draw_image_if_current(n, renderer, i))
            # Pré-renderiza páginas adjacentes em background
            renderer.prefetch(n)
        except Exception as e:
            log.error("Erro ao renderizar página %d: %s", n, e)

    def _draw_image_if_current(self, n: int, renderer, img: Image.Image):
        """Só desenha se, no momento em que o callback roda na UI thread, a
        imagem ainda corresponder à página/livro atuais — evita que uma
        renderização lenta de uma página antiga seja desenhada depois da
        imagem da página atual (virar páginas rápido)."""
        if self._alive and n == self.current_page and renderer is self.renderer:
            self._draw_image(img)

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _draw_image(self, img: Image.Image):
        """
        Exibe a imagem PIL no canvas com os grifos, respeitando zoom e pan.

        Ordem importa para a performance: a página é redimensionada para o
        tamanho de tela PRIMEIRO (e o resultado fica em cache), e os grifos
        são pintados depois, já na escala do canvas.

        A versão anterior compunha os grifos sobre a imagem em tamanho
        cheio — converter 827x1170 para RGBA, criar um overlay do mesmo
        tamanho, compor e reduzir com LANCZOS a cada chamada: ~52 ms. Isso
        não incomodava enquanto o grifo mudava uma vez por trecho, mas
        agora ele acompanha a voz palavra a palavra (várias vezes por
        segundo) e esse custo tomaria a thread da interface inteira.
        """
        if not self._alive:
            return
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.after(100, lambda: self._draw_image(img))
            return

        self._cur_img = img   # guarda para redesenhar no zoom/pan
        iw, ih = img.size

        # Escala base (zoom=1 → cabe na tela)
        scale      = self._page_scale()
        nw         = max(1, int(iw * scale))
        nh         = max(1, int(ih * scale))

        # Primeira renderização de uma página recém-aberta: ancora no topo
        # em vez de centralizar verticalmente (ver _show_page). Sem isso,
        # com o zoom padrão > 100%, o topo da página — onde o texto
        # normalmente começa — fica cortado e a tela parece "em branco".
        if self._pan_pending_top:
            self._pan_y = max(0, (nh - ch) // 2)
            self._pan_pending_top = False

        max_px, max_py = self._max_pan()
        self._pan_x = max(-max_px, min(max_px, self._pan_x))
        self._pan_y = max(-max_py, min(max_py, self._pan_y))

        # Página redimensionada em cache: só refaz o LANCZOS quando muda a
        # página, o zoom ou o tamanho do canvas — nunca quando só o grifo
        # andou. A comparação é por identidade do objeto (o renderer
        # mantém as imagens vivas no seu próprio cache LRU).
        if self._scaled_src is not img or self._scaled_size != (nw, nh):
            self._scaled_img  = img.resize((nw, nh), Image.LANCZOS)
            self._scaled_src  = img
            self._scaled_size = (nw, nh)

        # Posição do canto superior esquerdo da página no canvas
        x = (cw - nw) // 2 + self._pan_x
        y = (ch - nh) // 2 + self._pan_y

        # Recorta somente a área visível para não criar imagem gigante
        src_x  = max(0, -x)
        src_y  = max(0, -y)
        src_x2 = min(nw, src_x + cw)
        src_y2 = min(nh, src_y + ch)

        frame = Image.new("RGB", (cw, ch), self._hex_to_rgb(C["canvas_bg"]))
        if src_x2 > src_x and src_y2 > src_y:
            frame.paste(
                self._scaled_img.crop((src_x, src_y, src_x2, src_y2)),
                (max(0, x), max(0, y)),
            )

        # Grifos: de pontos PDF direto para pixels do canvas
        self._paint_highlights(frame, (PDF_RENDER_DPI / 72.0) * scale, x, y)

        tk_img = ImageTk.PhotoImage(frame)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=tk_img)
        self._canvas_img_ref = tk_img

        # Atualiza label de zoom
        self._zoom_lbl.configure(text=f"{int(self._zoom * 100)}%")

        # Cursor muda para indicar que pode arrastar quando com zoom
        self._canvas.configure(cursor="fleur" if self._page_overflows() else "")

    def _paint_highlights(self, frame: Image.Image, k: float, ox: int, oy: int):
        """
        Pinta grifos efêmeros (leitura) e manuais sobre `frame`, que já
        está no tamanho do canvas.

        `k` converte pontos PDF em pixels de tela e (ox, oy) é onde o
        canto da página caiu no canvas. Retângulos fora da área visível
        são descartados antes de desenhar.
        """
        pintar = [(h, h.get("color", C["info"])) for h in self._ephemeral_highlights]
        if self.current_path:
            pintar += [(h, h.get("color", DEFAULT_HIGHLIGHT_COLOR))
                       for h in highlights.get(self.current_path, self.current_page + 1)]
        if not pintar:
            return

        cw, ch = frame.size
        visiveis = []
        for h, color in pintar:
            x0 = h["x0"] * k + ox
            y0 = h["y0"] * k + oy
            x1 = h["x1"] * k + ox
            y1 = h["y1"] * k + oy
            if x1 < 0 or y1 < 0 or x0 > cw or y0 > ch:
                continue
            visiveis.append((x0, y0, x1, y1, color, h.get("opacity", 0.35)))
        if not visiveis:
            return

        # O overlay cobre só a área dos grifos, não o canvas inteiro:
        # durante a leitura o grifo da palavra ocupa uns poucos milhares
        # de pixels, e alocar meio megapixel a cada palavra era o maior
        # custo restante do redesenho.
        bx0 = max(0, int(min(v[0] for v in visiveis)))
        by0 = max(0, int(min(v[1] for v in visiveis)))
        bx1 = min(cw, int(max(v[2] for v in visiveis)) + 1)
        by1 = min(ch, int(max(v[3] for v in visiveis)) + 1)
        if bx1 <= bx0 or by1 <= by0:
            return

        overlay = Image.new("RGBA", (bx1 - bx0, by1 - by0), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for x0, y0, x1, y1, color, opacity in visiveis:
            r, g, b = self._hex_to_rgb(color)
            draw.rectangle([x0 - bx0, y0 - by0, x1 - bx0, y1 - by0],
                           fill=(r, g, b, int(opacity * 255)))

        # RGBA como própria máscara = composição alpha sobre o RGB
        frame.paste(overlay, (bx0, by0), overlay)

    def _zoom_in(self):
        self._zoom = min(self._zoom_max, round(self._zoom + 0.25, 2))
        prefs.set_value("zoom", self._zoom)
        self._redraw()

    def _zoom_out(self):
        self._zoom = max(self._zoom_min, round(self._zoom - 0.25, 2))
        self._pan_x = 0
        prefs.set_value("zoom", self._zoom)
        self._redraw()

    def _zoom_reset(self):
        """Volta ao ajuste puro, sem zoom extra (atalho Ctrl+0)."""
        self._zoom  = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._pan_pending_top = True
        prefs.set_value("zoom", self._zoom)
        self._redraw()

    def _toggle_fit_mode(self):
        """Alterna largura ⇄ página inteira e volta o zoom a 1.0."""
        self._fit_mode = "pagina" if self._fit_mode == "largura" else "largura"
        prefs.set_value("fit_mode", self._fit_mode)
        self._update_fit_btn()
        self._zoom_reset()

    def _update_fit_btn(self):
        self._fit_btn.label.configure(
            text="LARGURA" if self._fit_mode == "largura" else "PÁGINA")

    def _page_overflows(self) -> bool:
        """True quando a página não cabe inteira na altura do canvas —
        ou seja, quando há o que rolar. É o que decide se a roda do mouse
        rola a página ou passa para a próxima."""
        if self._cur_img is None:
            return False
        _iw, ih = self._cur_img.size
        return ih * self._page_scale() > self._canvas.winfo_height() + 2

    # Máscara do bit "Control" no state de eventos do Tkinter (Windows/X11)
    _CONTROL_MASK = 0x0004

    def _on_mousewheel(self, event):
        """
        Antes, a roda do mouse SEMPRE dava zoom — fora da convenção usual
        de leitores de PDF (a maioria reserva Ctrl+roda para zoom e usa a
        roda normal para rolar/passar de página).

        Agora: Ctrl+roda = zoom (como antes). Roda normal: se a página
        está com zoom ativo, faz pan vertical; se está no tamanho de
        ajuste (100%), passa para a página anterior/seguinte.
        """
        ctrl_held = bool(event.state & self._CONTROL_MASK)

        # Windows manda event.delta em múltiplos de 120 ("um clique" da
        # roda), mas touchpads de precisão mandam valores bem menores e
        # muito mais vezes. Tratar cada evento como um clique fazia o
        # touchpad virar várias páginas — e cada virada reinicia a
        # leitura — com um movimento mínimo do dedo. Acumular o delta e
        # só agir a cada 120 resolve; no Linux (Button-4/5) não há delta,
        # então cada evento vale um clique inteiro.
        if event.num in (4, 5):
            cliques = 1 if event.num == 4 else -1
        else:
            self._wheel_accum += getattr(event, "delta", 0)
            cliques = int(self._wheel_accum / 120)
            if not cliques:
                return
            self._wheel_accum -= cliques * 120

        scroll_up = cliques > 0

        if ctrl_held:
            if scroll_up:
                self._zoom_in()
            else:
                self._zoom_out()
            return

        # Antes a condição era `zoom > 1.01`. Com o ajuste por largura a
        # página transborda para baixo mesmo com zoom 1.0, e a roda
        # virava página em vez de rolar o texto — exatamente no modo em
        # que rolar é o gesto esperado.
        if self._page_overflows():
            self._pan_y += 60 * cliques
            self._redraw()
        elif scroll_up:
            self._prev_page()
        else:
            self._next_page()

    def _on_canvas_press(self, event):
        if self._hl_mode:
            self._on_sel_start(event)
        else:
            self._on_pan_start(event)

    def _on_canvas_drag(self, event):
        if self._hl_mode:
            self._on_sel_drag(event)
        else:
            self._on_pan_move(event)

    def _on_canvas_release(self, event):
        if self._hl_mode:
            self._on_sel_end(event)
        else:
            self._on_pan_end(event)

    def _on_pan_start(self, event):
        self._press_x = event.x
        self._press_y = event.y
        if self._page_overflows():
            self._pan_start = (event.x - self._pan_x, event.y - self._pan_y)

    def _on_pan_move(self, event):
        if self._pan_start and self._page_overflows():
            self._pan_x = event.x - self._pan_start[0]
            self._pan_y = event.y - self._pan_start[1]
            self._redraw()

    def _on_pan_end(self, event):
        dx = abs(event.x - self._press_x)
        dy = abs(event.y - self._press_y)
        self._pan_start = None
        # Se o mouse não se moveu mais de 5px é um clique simples → busca palavra
        if dx <= 5 and dy <= 5:
            self._on_word_click(event.x, event.y)

    def _redraw(self):
        """Redesenha a imagem atual com zoom/pan atualizados."""
        if self._cur_img is not None:
            self._draw_image(self._cur_img)

    def _canvas_to_pdf_coords(self, cx: int, cy: int) -> tuple[float, float] | None:
        """
        Converte coordenadas do canvas (pixels de tela) para coordenadas do PDF (pontos).
        Retorna (pdf_x, pdf_y) ou None se o clique foi fora da área da imagem.
        """
        if not self._cur_img:
            return None
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        iw, ih = self._cur_img.size
        scale      = self._page_scale()
        nw = int(iw * scale)
        nh = int(ih * scale)
        # Posição do canto superior esquerdo da imagem no canvas
        img_x0 = (cw - nw) // 2 + self._pan_x
        img_y0 = (ch - nh) // 2 + self._pan_y
        # Coordenada dentro da imagem renderizada
        ix = cx - img_x0
        iy = cy - img_y0
        if not (0 <= ix < nw and 0 <= iy < nh):
            return None
        # ix/scale → pixel na imagem PIL original (renderizada a PDF_RENDER_DPI)
        # ÷ (PDF_RENDER_DPI/72) → converte pixel para ponto PDF (72 DPI)
        dpi_scale = PDF_RENDER_DPI / 72.0
        pdf_x = (ix / scale) / dpi_scale
        pdf_y = (iy / scale) / dpi_scale
        return pdf_x, pdf_y

    def _on_canvas_resize(self, _event):
        """Redesenha a página atual quando o canvas muda de tamanho."""
        if self.renderer and 0 <= self.current_page < self.total_pages:
            threading.Thread(
                target=self._render_and_draw,
                args=(self.current_page, self.renderer),
                daemon=True,
            ).start()

    def _open_search(self):
        self._search_bar.grid()
        self._search_entry.focus_set()
        self._search_entry.select_range(0, "end")

    def _close_search(self):
        self._search_bar.grid_remove()
        self._search_results = []
        self._search_result_idx = -1
        self._ephemeral_highlights = [h for h in self._ephemeral_highlights
                                       if h.get("_search")]
        self._ephemeral_highlights = []
        self._redraw()

    def _do_search(self):
        """Busca o termo em todas as páginas do PDF e armazena resultados."""
        term = self._search_var.get().strip()
        self._search_results = []
        self._search_result_idx = -1
        self._search_count_lbl.configure(text="")
        if not term or not self.renderer:
            self._redraw()
            return
        # Busca somente na página atual para resposta imediata
        hits = self.renderer.search_text(self.current_page, term)
        for bbox in hits:
            bbox["_search"] = True
            bbox["color"]   = C["search"]
            self._search_results.append({"page": self.current_page, "bbox": bbox})
        # Busca no restante das páginas em background
        threading.Thread(target=self._search_all_pages,
                         args=(term, self.current_page), daemon=True).start()

    def _search_all_pages(self, term: str, skip_page: int):
        """Varre todas as páginas exceto skip_page (já feita em _do_search)."""
        if not self.renderer:
            return
        results = []
        for p in range(self.total_pages):
            if p == skip_page:
                continue
            try:
                hits = self.renderer.search_text(p, term)
            except Exception:
                hits = []
            for bbox in hits:
                bbox["_search"] = True
                bbox["color"]   = C["search"]
                results.append({"page": p, "bbox": bbox})
        # Ordena por página e mescla com os resultados da página atual
        if self._alive and self._search_var.get().strip() == term:
            def _merge():
                self._search_results += results
                self._search_results.sort(key=lambda r: r["page"])
                total = len(self._search_results)
                if total == 0:
                    self._search_count_lbl.configure(text="sem resultados")
                else:
                    self._search_count_lbl.configure(text=f"1 / {total}")
                    self._search_result_idx = 0
                    self._jump_to_search_result(0)
            self.after(0, _merge)

    def _search_navigate(self, delta: int):
        if not self._search_results:
            return
        n = len(self._search_results)
        self._search_result_idx = (self._search_result_idx + delta) % n
        self._search_count_lbl.configure(
            text=f"{self._search_result_idx + 1} / {n}")
        self._jump_to_search_result(self._search_result_idx)

    def _jump_to_search_result(self, idx: int):
        if not self._search_results or idx < 0:
            return
        result = self._search_results[idx]
        page   = result["page"]
        bbox   = result["bbox"]
        # Vai para a página do resultado se necessário
        if page != self.current_page:
            self.current_page = page
            self._prog_var.set(page + 1)
            self._page_lbl.configure(text=f"PÁG. {page + 1} / {self.total_pages}")
            threading.Thread(
                target=self._render_and_draw, args=(page, self.renderer), daemon=True,
            ).start()
        # Destaca todos os resultados da página atual; o resultado corrente
        # (identificado por identidade do objeto, não por índice — a versão
        # anterior sempre pintava o primeiro da lista, nunca o realmente
        # selecionado) fica em laranja, os demais em amarelo.
        self._ephemeral_highlights = [
            {**r["bbox"], "_search": True,
             "color": C["warn"] if r is result else C["search"]}
            for r in self._search_results if r["page"] == page
        ]
        # Centraliza no resultado via pan
        zoom_pdf = PDF_RENDER_DPI / 72.0
        y_center_pdf = (bbox["y0"] + bbox["y1"]) / 2.0
        if self._cur_img:
            ch = self._canvas.winfo_height()
            _iw, ih = self._cur_img.size
            scale = self._page_scale()
            y_on_canvas = (ch - ih * scale) / 2 + y_center_pdf * zoom_pdf * scale
            self._pan_y = int(ch / 2 - y_on_canvas)
        self._redraw()
