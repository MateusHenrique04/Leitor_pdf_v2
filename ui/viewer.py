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
                             font=FONTS["mono_bold"], bg=C["border"], fg=C["text"],
                             hover_bg="#333", padx=8, pady=2)
            b.pack(side="left", padx=2)
            return b

        _zoom_btn(zoom_row, "−", self._zoom_out)
        self._zoom_lbl = tk.Label(zoom_row, text="100%",
                                   font=FONTS["mono_bold"],
                                   bg=C["panel"], fg=C["text_dim"],
                                   width=5, anchor="center")
        self._zoom_lbl.pack(side="left")
        _zoom_btn(zoom_row, "＋", self._zoom_in)
        _zoom_btn(zoom_row, "⊡", self._zoom_reset)

        self._page_lbl = tk.Label(
            topbar, text="",
            font=("Courier", 10, "bold"),
            bg=C["panel"], fg=C["red"],
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

        tk.Label(self._search_bar, text="🔍", font=("Courier", 10),
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
            b = tk.Label(self._search_bar, text=txt, font=("Courier", 11, "bold"),
                         bg=C["border"], fg=C["text"], cursor="hand2", padx=8, pady=4)
            b.pack(side="left", padx=2, pady=4)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, bb=b: bb.configure(bg="#333"))
            b.bind("<Leave>", lambda e, bb=b: bb.configure(bg=C["border"]))
        close_s = tk.Label(self._search_bar, text="✕", font=("Courier", 11, "bold"),
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

    def _show_page(self, n: int):
        """Renderiza e exibe a página n no canvas."""
        if not self.renderer or not (0 <= n < self.total_pages):
            return

        self.current_page = n
        self._pan_x = self._pan_y = 0   # reseta pan ao mudar de página
        self._ephemeral_highlights = []  # limpa grifo da frase anterior
        self._eph_y_cursor = 0.0         # reseta cursor de posição sequencial
        lib.save_position(self.current_path, n, self.current_chunk_idx)

        # Atualiza label e slider sem disparar seek
        self._prog_var.set(n + 1)
        self._page_lbl.configure(text=f"PÁG. {n + 1} / {self.total_pages}")

        # Renderiza em thread separada para não travar a UI
        threading.Thread(target=self._render_and_draw, args=(n,), daemon=True).start()

    def _render_and_draw(self, n: int):
        """Roda em background — renderiza a imagem e agenda o draw na UI."""
        try:
            img = self.renderer.render_page(n)
            if self._alive:
                self.after(0, lambda i=img: self._draw_image(i))
            # Pré-renderiza páginas adjacentes em background
            self.renderer.prefetch(n)
        except Exception as e:
            log.error(f"Erro ao renderizar página {n}: {e}")

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _draw_image(self, img: Image.Image):
        """Exibe a imagem PIL no canvas com os grifos, respeitando zoom e pan."""
        if not self._alive:
            return
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.after(100, lambda: self._draw_image(img))
            return

        self._cur_img = img   # guarda para redesenhar no zoom/pan
        iw, ih = img.size

        # Aplica Grifos Permanentes e Efêmeros em uma cópia da imagem original
        img_drawn = img.convert("RGBA")
        overlay = Image.new("RGBA", img_drawn.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        zoom_pdf = PDF_RENDER_DPI / 72.0

        # Desenha efêmeros (TTS) — respeita opacity individual
        if self._ephemeral_highlights:
            for h in self._ephemeral_highlights:
                r, g, b = self._hex_to_rgb(h.get("color", C["info"]))
                a = int(h.get("opacity", 0.35) * 255)
                draw.rectangle(
                    [h["x0"]*zoom_pdf, h["y0"]*zoom_pdf,
                     h["x1"]*zoom_pdf, h["y1"]*zoom_pdf],
                    fill=(r, g, b, a),
                )

        # Desenha manuais
        if self.current_path:
            saved_h = highlights.get(self.current_path, self.current_page + 1)
            for h in saved_h:
                r, g, b = self._hex_to_rgb(h.get("color", DEFAULT_HIGHLIGHT_COLOR))
                a = int(h.get("opacity", 0.35) * 255)
                draw.rectangle([h["x0"]*zoom_pdf, h["y0"]*zoom_pdf, h["x1"]*zoom_pdf, h["y1"]*zoom_pdf], fill=(r, g, b, a))

        img_drawn.alpha_composite(overlay)
        base_img = img_drawn.convert("RGB")

        # Escala base (zoom=1 → cabe na tela)
        base_scale = min(cw / iw, ch / ih)
        scale      = base_scale * self._zoom
        nw         = int(iw * scale)
        nh         = int(ih * scale)

        # Limita pan: não deixa imagem sair completamente da tela
        max_px = max(0, (nw - cw) // 2 + nw // 4)
        max_py = max(0, (nh - ch) // 2 + nh // 4)
        self._pan_x = max(-max_px, min(max_px, self._pan_x))
        self._pan_y = max(-max_py, min(max_py, self._pan_y))

        resized = base_img.resize((nw, nh), Image.LANCZOS)

        # Posição central + offset de pan
        x = (cw - nw) // 2 + self._pan_x
        y = (ch - nh) // 2 + self._pan_y

        # Recorta somente a área visível para não criar imagem gigante
        src_x  = max(0, -x)
        src_y  = max(0, -y)
        src_x2 = min(nw, src_x + cw)
        src_y2 = min(nh, src_y + ch)
        cropped = resized.crop((src_x, src_y, src_x2, src_y2))

        dest_x = max(0, x)
        dest_y = max(0, y)

        bg = Image.new("RGB", (cw, ch), (26, 26, 26))
        bg.paste(cropped, (dest_x, dest_y))

        tk_img = ImageTk.PhotoImage(bg)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=tk_img)
        self._canvas_img_ref = tk_img

        # Atualiza label de zoom
        self._zoom_lbl.configure(text=f"{int(self._zoom * 100)}%")

        # Cursor muda para indicar que pode arrastar quando com zoom
        self._canvas.configure(cursor="fleur" if self._zoom > 1.01 else "")

    def _zoom_in(self):
        self._zoom = min(self._zoom_max, round(self._zoom + 0.25, 2))
        prefs.set("zoom", self._zoom)
        self._redraw()

    def _zoom_out(self):
        self._zoom = max(self._zoom_min, round(self._zoom - 0.25, 2))
        if self._zoom <= 1.0:
            self._pan_x = self._pan_y = 0
        prefs.set("zoom", self._zoom)
        self._redraw()

    def _zoom_reset(self):
        self._zoom  = 1.0
        self._pan_x = self._pan_y = 0
        prefs.set("zoom", self._zoom)
        self._redraw()

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
        # Windows: event.delta (+120 / -120), Linux: Button-4/5
        scroll_up = event.num == 4 or (hasattr(event, "delta") and event.delta > 0)
        ctrl_held = bool(event.state & self._CONTROL_MASK)

        if ctrl_held:
            if scroll_up:
                self._zoom_in()
            else:
                self._zoom_out()
            return

        if self._zoom > 1.01:
            self._pan_y += 60 if scroll_up else -60
            self._redraw()
        else:
            if scroll_up:
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
        if self._zoom > 1.01:
            self._pan_start = (event.x - self._pan_x, event.y - self._pan_y)

    def _on_pan_move(self, event):
        if self._pan_start and self._zoom > 1.01:
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
        base_scale = min(cw / iw, ch / ih)
        scale      = base_scale * self._zoom
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
                args=(self.current_page,),
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
            threading.Thread(target=self._render_and_draw, args=(page,), daemon=True).start()
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
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            iw, ih = self._cur_img.size
            base_scale = min(cw / iw, ch / ih)
            scale = base_scale * self._zoom
            y_on_canvas = (ch - ih * scale) / 2 + y_center_pdf * zoom_pdf * scale
            self._pan_y = int(ch / 2 - y_on_canvas)
        self._redraw()
