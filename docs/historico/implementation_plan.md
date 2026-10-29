# Separação do `ui/app.py` em Módulos

O `app.py` tem **2.271 linhas** e 94 KB. Embora já siga a regra de "UI orquestra, lógica em `core/`", a classe `App` acumula muitas responsabilidades de UI que podem ser isoladas em arquivos menores, facilitando edição e manutenção.

## Estrutura Proposta

```
ui/
├── app.py              ← ~150 linhas (só __init__, _build, _bind_keys, _quit)
├── sidebar.py          ← Sidebar + biblioteca (lista de livros)
├── viewer.py           ← Canvas da página, topbar, barra de busca, zoom, pan
├── controls.py         ← Barra inferior de transporte (play/pause, timer)
├── right_panel.py      ← Painel direito (voz, velocidade, volume, grifos, status, foco, sumário)
├── toc_window.py       ← Janela popup do sumário
├── dict_popup.py       ← Popup do dicionário (ao clicar em palavra)
├── focus_dialog.py     ← Diálogo do modo foco
└── __init__.py
```

## Estratégia de Separação

Cada arquivo exportará **uma classe mixin** (ex: `SidebarMixin`). A classe `App` em `app.py` herdará de todos os mixins, mantendo o comportamento idêntico — sem alterar imports externos e sem quebrar `main.py`.

```python
# app.py (novo)
class App(SidebarMixin, ViewerMixin, ControlsMixin, RightPanelMixin, ctk.CTk):
    def __init__(self): ...
    def _build(self): ...
    def _bind_keys(self): ...
    def _quit(self): ...
```

> [!IMPORTANT]
> **Nenhum comportamento será alterado** — só reorganização de código. O app continuará funcionando exatamente igual.

## Divisão por Arquivo

| Arquivo | Métodos principais | Linhas (aprox.) |
|---|---|---|
| `app.py` | `__init__`, `_build`, `_bind_keys`, `_quit`, `_save_session`, `_tick_timer` | ~200 |
| `sidebar.py` | `_build_sidebar`, `_refresh_lib`, `_remove_book`, `_open_file`, `_load_book`, `_toggle_finished`, `_update_finished_btn` | ~350 |
| `viewer.py` | `_build_center`, `_show_page`, `_render_and_draw`, `_draw_image`, `_zoom_*`, `_on_mousewheel`, `_on_canvas_*`, `_on_pan_*`, `_on_sel_*`, `_redraw`, `_canvas_to_pdf_coords`, `_on_canvas_resize` | ~450 |
| `controls.py` | `_build_controls`, `_toggle_play`, `_next_page`, `_prev_page`, `_next_chunk`, `_prev_chunk`, `_on_seek`, `_restart_loop`, `_do_restart`, `_read_loop`, `_toggle_autoscroll`, `_auto_scroll_to_highlight` | ~450 |
| `right_panel.py` | `_build_right` | ~250 |
| `highlights_mixin.py` | `_precompute_word_bboxes`, `_highlight_ephemeral`, `_highlight_manual`, `_clear_page_highlights`, `_export_highlights`, `_toggle_hl_mode`, `_on_sel_start/drag/end` | ~300 |
| `dict_popup.py` | `_on_word_click`, `_fetch_and_show`, `_show_dict_popup` | ~130 |
| `toc_window.py` | `_show_toc` | ~90 |
| `focus_dialog.py` | `_open_focus_dialog`, `_focus_start`, `_focus_tick`, `_focus_end_naturally`, `_focus_cancel`, `_focus_blocked_feedback` | ~200 |

## Proposed Changes

### ui/ (pasta de interface)

#### [MODIFY] [app.py](file:///c:/Users/Mateus/Desktop/lector/ui/app.py)
Reduzido a ~200 linhas: `__init__`, `_build`, `_bind_keys`, `_quit`, `_save_session`, `_tick_timer`. A classe `App` herda de todos os mixins.

#### [NEW] ui/sidebar.py
`SidebarMixin` com toda a lógica da sidebar, lista de livros, abertura/carregamento de arquivo.

#### [NEW] ui/viewer.py
`ViewerMixin` com o canvas da página, zoom, pan, resize, topbar e barra de busca.

#### [NEW] ui/controls.py
`ControlsMixin` com barra de transporte, loop de leitura TTS, controles de playback e auto-scroll.

#### [NEW] ui/right_panel.py
`RightPanelMixin` com a construção do painel direito.

#### [NEW] ui/highlights_mixin.py
`HighlightsMixin` com toda lógica de grifos (efêmeros, manuais, seleção, export).

#### [NEW] ui/dict_popup.py
`DictPopupMixin` com clique de palavra e popup do dicionário.

#### [NEW] ui/toc_window.py
`TocMixin` com a janela de sumário.

#### [NEW] ui/focus_dialog.py
`FocusMixin` com o diálogo de modo foco e seu countdown.

## Verificação

- Executar `python main.py` e testar todas as funcionalidades do app.
- Verificar que abrir PDF, TTS, grifos, dicionário, sumário, modo foco e busca continuam funcionando.
