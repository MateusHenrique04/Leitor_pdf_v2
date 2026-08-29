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

from config import C


def flat_button(
    parent,
    text: str,
    command,
    *,
    font=("Georgia", 13),
    bg: str | None = None,
    fg: str = "#888",
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
