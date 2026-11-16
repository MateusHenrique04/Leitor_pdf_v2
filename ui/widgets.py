"""
ui/widgets.py — componentes reutilizáveis para reduzir a duplicação de
"botão falso" (tk.Frame + tk.Label com hover/clique bindados manualmente)
que se repetia em quase todo arquivo de ui/ (controls.py, dict_popup.py,
focus_dialog.py, sidebar.py, viewer.py...).

Uso:
    from ui.widgets import flat_button
    btn = flat_button(parent, "▶", self._toggle_play, bg=C["red"], hover_bg=C["red_hot"])
    btn.pack(...)
    btn.label.configure(text="⏸")   # trocar o texto depois, se precisar
"""
import tkinter as tk

from config import FONTS, C

# Folga nas pontas da SeekBar para o marcador redondo não ser cortado.
_SEEK_MARGIN = 6


def flat_button(
    parent,
    text: str,
    command,
    *,
    font=("Georgia", 13),
    bg: str | None = None,
    fg: str | None = None,
    hover_bg: str = C["hover"],
    width: int | None = None,
    height: int | None = None,
    padx: int = 10,
    pady: int = 6,
) -> tk.Frame:
    """
    Cria um "botão" leve baseado em Frame+Label com hover, no estilo já
    usado no app. Retorna o Frame (com um atributo extra `.label`, para
    trocar texto/cor depois) — chame .pack()/.grid()/.place() nele.

    Se `width`/`height` forem passados, o botão tem tamanho fixo (ex.:
    ícones circulares/quadrados de transporte); caso contrário, o
    tamanho é definido pelo texto + padx/pady (ex.: botões de texto).
    """
    bg = bg or C["border"]
    fg = fg or C["text_dim"]
    fixed_size = width is not None or height is not None

    frame_kwargs = {}
    if width is not None:
        frame_kwargs["width"] = width
    if height is not None:
        frame_kwargs["height"] = height
    frame = tk.Frame(parent, bg=bg, cursor="hand2", **frame_kwargs)
    if fixed_size:
        frame.pack_propagate(False)

    label = tk.Label(
        frame, text=text, font=font, bg=bg, fg=fg,
        padx=0 if fixed_size else padx,
        pady=0 if fixed_size else pady,
    )
    if fixed_size:
        label.place(relx=0.5, rely=0.5, anchor="center")
    else:
        label.pack()

    def _on_click(_e):
        command()

    def _on_enter(_e):
        frame.configure(bg=hover_bg)
        label.configure(bg=hover_bg)

    def _on_leave(_e):
        frame.configure(bg=bg)
        label.configure(bg=bg)

    for w in (frame, label):
        w.bind("<Button-1>", _on_click)
        w.bind("<Enter>", _on_enter)
        w.bind("<Leave>", _on_leave)

    frame.label = label
    return frame


class SeekBar(tk.Canvas):
    """
    Barra de progresso clicável e arrastável.

    Por que não um `tk.Scale`: no Scale, clicar no meio da trilha avança
    um "passo" na direção do clique em vez de saltar para o ponto
    clicado — ou seja, não dá para pular para um minuto específico com um
    clique só, que é justamente o uso aqui.

    `on_seek(fracao)` é chamado ao SOLTAR o botão, com um valor de 0 a 1.
    Enquanto o usuário arrasta, a barra se move sozinha e `set_fraction`
    é ignorado, para a posição da leitura não brigar com o dedo dele.
    """

    def __init__(self, parent, on_seek, *, width=260, height=16,
                 track=None, fill=None, knob=None):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, bd=0,
                         cursor="hand2")
        self._on_seek = on_seek
        self._fraction = 0.0
        self._dragging = False
        self._track_color = track or C["border"]
        self._fill_color = fill or C["red"]
        self._knob_color = knob or C["red_hot"]
        self._enabled = False

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ── estado ────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        """Desligada enquanto não há livro aberto — nem desenha o
        preenchimento nem responde a cliques."""
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "")
        self._redraw()

    def set_fraction(self, fraction: float):
        if self._dragging:
            return
        fraction = max(0.0, min(1.0, fraction))
        if abs(fraction - self._fraction) < 1e-4:
            return
        self._fraction = fraction
        self._redraw()

    # ── interação ─────────────────────────────────────────────────

    def _fraction_at(self, x: int) -> float:
        largura = max(1, self.winfo_width() - 2 * _SEEK_MARGIN)
        return max(0.0, min(1.0, (x - _SEEK_MARGIN) / largura))

    def _on_press(self, event):
        if not self._enabled:
            return
        self._dragging = True
        self._fraction = self._fraction_at(event.x)
        self._redraw()

    def _on_drag(self, event):
        if not self._dragging:
            return
        self._fraction = self._fraction_at(event.x)
        self._redraw()

    def _on_release(self, event):
        if not self._dragging:
            return
        self._dragging = False
        self._fraction = self._fraction_at(event.x)
        self._redraw()
        self._on_seek(self._fraction)

    # ── desenho ───────────────────────────────────────────────────

    def _redraw(self):
        self.delete("all")
        largura = self.winfo_width()
        altura = self.winfo_height()
        if largura <= 1 or altura <= 1:
            return
        y = altura // 2
        x0, x1 = _SEEK_MARGIN, largura - _SEEK_MARGIN
        self.create_rectangle(x0, y - 2, x1, y + 2,
                              fill=self._track_color, outline="")
        if not self._enabled:
            return
        xf = x0 + (x1 - x0) * self._fraction
        if xf > x0:
            self.create_rectangle(x0, y - 2, xf, y + 2,
                                  fill=self._fill_color, outline="")
        raio = 5 if self._dragging else 4
        self.create_oval(xf - raio, y - raio, xf + raio, y + raio,
                         fill=self._knob_color, outline="")


class CollapsibleSection(tk.Frame):
    """
    Seção com cabeçalho clicável que mostra ou esconde o seu conteúdo.

    Existe porque o painel direito era uma lista plana de sete seções com
    o mesmo peso visual, misturando o que se ajusta toda hora (voz,
    velocidade, volume) com o que se usa uma vez por sessão (sumário,
    modo foco). Tudo junto não cabia em janelas baixas.

    O conteúdo vai em `.body`:

        sec = CollapsibleSection(painel, "Grifos", aberta=True)
        sec.pack(fill="x")
        tk.Label(sec.body, ...).pack()
    """

    def __init__(self, parent, title: str, *, aberta: bool = False, on_toggle=None):
        super().__init__(parent, bg=C["panel"])
        self._aberta = aberta
        self._on_toggle = on_toggle
        self.title = title

        header = tk.Frame(self, bg=C["panel"], cursor="hand2")
        header.pack(fill="x")
        self._arrow = tk.Label(
            header, text="", font=FONTS["symbol"],
            bg=C["panel"], fg=C["text_dim"], width=2,
        )
        self._arrow.pack(side="left", padx=(14, 0))
        self._label = tk.Label(
            header, text=title.upper(), font=FONTS["label"],
            bg=C["panel"], fg=C["text_dim"], anchor="w", pady=8,
        )
        self._label.pack(side="left", fill="x", expand=True)

        for w in (header, self._arrow, self._label):
            w.bind("<Button-1>", lambda _e: self.toggle())
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))

        self.body = tk.Frame(self, bg=C["panel"])
        self._sync()

    def _hover(self, dentro: bool):
        cor = C["text"] if dentro else C["text_dim"]
        self._arrow.configure(fg=cor)
        self._label.configure(fg=cor)

    def _sync(self):
        self._arrow.configure(text="▾" if self._aberta else "▸")
        if self._aberta:
            self.body.pack(fill="x", pady=(0, 8))
        else:
            self.body.pack_forget()

    @property
    def aberta(self) -> bool:
        return self._aberta

    def toggle(self):
        self._aberta = not self._aberta
        self._sync()
        if self._on_toggle:
            self._on_toggle(self.title, self._aberta)
