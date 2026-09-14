# Documentação Técnica — Lector

> Este documento complementa o [`README.md`](README.md) (visão geral e uso) e o
> [`ADICIONAR_FUNCIONALIDADE.md`](ADICIONAR_FUNCIONALIDADE.md) (guia rápido de
> "onde editar"). Aqui o foco é **arquitetura, fluxos internos, formatos de
> dados e decisões de design** — o material que normalmente se perde na
> cabeça de quem escreveu o código.

## Índice

1. [Visão geral](#1-visão-geral)
2. [Stack e dependências](#2-stack-e-dependências)
3. [Arquitetura em camadas](#3-arquitetura-em-camadas)
4. [Estrutura de diretórios](#4-estrutura-de-diretórios)
5. [Ciclo de vida da aplicação](#5-ciclo-de-vida-da-aplicação)
6. [Camada `core/` — lógica de negócio](#6-camada-core--lógica-de-negócio)
7. [Camada `data/` — persistência](#7-camada-data--persistência)
8. [Camada `ui/` — interface (mixins)](#8-camada-ui--interface-mixins)
9. [Fluxos-chave em detalhe](#9-fluxos-chave-em-detalhe)
10. [Concorrência](#10-concorrência)
11. [Configuração (`config.py`)](#11-configuração-configpy)
12. [Tratamento de erros e resiliência](#12-tratamento-de-erros-e-resiliência)
13. [Testes](#13-testes)
14. [CI/CD](#14-cicd)
15. [Build e distribuição (PyInstaller)](#15-build-e-distribuição-pyinstaller)
16. [Atalhos de teclado](#16-atalhos-de-teclado)
17. [Limitações conhecidas e melhorias futuras](#17-limitações-conhecidas-e-melhorias-futuras)
18. [Glossário](#18-glossário)

---

## 1. Visão geral

**Lector** é um leitor de PDF desktop (Windows/Linux/Mac) que lê o texto em
voz alta com destaque sincronizado, tem dicionário interativo por clique de
palavra, sistema de grifos persistentes, biblioteca com progresso de leitura
e modo foco. É uma aplicação **Python + Tkinter/CustomTkinter monolítica de
processo único** — sem backend, sem banco de dados, sem instalação além do
Python: todo o estado é gravado em arquivos JSON ao lado do executável.

Tamanho do código-fonte (sem testes): **≈ 4.000 linhas** distribuídas em
`core/` (lógica pura, ~760 linhas), `data/` (persistência, ~310 linhas) e
`ui/` (interface, ~2.960 linhas, via mixins).

## 2. Stack e dependências

| Camada | Biblioteca | Uso |
|---|---|---|
| UI | `customtkinter` + `tkinter` | Janela, widgets, canvas |
| Renderização PDF | `pymupdf` (fitz) | Abrir PDF, rasterizar página, extrair texto/palavras/TOC, busca de texto |
| Imagem | `pillow` (PIL) | Composição de grifos sobre a página, redimensionamento, cache |
| TTS | `edge-tts` | Síntese de voz via serviço da Microsoft (streaming + word-boundaries) |
| Áudio | `pygame` (`pygame.mixer.music`) | Reprodução do MP3 gerado |
| Dicionário | `requests` + `beautifulsoup4` | Scraping de dicio.com.br, chamadas REST a Wiktionary/Free Dictionary |
| Detecção de idioma | `langdetect` | pt/en/es para escolher o backend de dicionário |
| Empacotamento | `pyinstaller` | Gera `dist/main.exe` |
| Dev | `pytest`, `ruff` | Testes e lint |

Todas fixadas com piso mínimo de versão em `requirements.txt` — comentário no
próprio arquivo explica por que (customtkinter/pymupdf/edge-tts quebram API
entre minor versions).

## 3. Arquitetura em camadas

Regra de dependência estrita, reforçada por convenção (não há enforcement
automatizado como import-linter):

```
ui/    → pode importar core/ e data/
core/  → não importa ui/ nem data/ (lógica pura, testável sem Tk)
data/  → não importa ui/ nem core/ (só config.py)
config.py → não importa nada do projeto (raiz da árvore de dependências)
```

```
┌─────────────────────────────────────────────────────────┐
│  ui/  (CustomTkinter — orquestra, nunca guarda regra)     │
│  app.py + 8 mixins (Sidebar, Viewer, Controls,             │
│  RightPanel, Highlights, DictPopup, Toc, Focus)            │
└───────────────┬─────────────────────────┬─────────────────┘
                 │                         │
                 ▼                         ▼
┌─────────────────────────┐   ┌─────────────────────────────┐
│  core/  (sem estado de   │   │  data/  (persistência JSON)  │
│  UI, testável isolado)   │   │                               │
│  - pdf_renderer.py       │   │  - _jsonio.py (I/O atômico)  │
│  - dictionary.py         │   │  - library.py                │
│  - tts.py                │   │  - history.py                │
│  - player.py             │   │  - highlights.py              │
└─────────────────────────┘   │  - prefs.py                   │
                               └───────────┬───────────────────┘
                                           ▼
                               ┌─────────────────────────────┐
                               │  config.py (única fonte de    │
                               │  verdade: cores, fontes,      │
                               │  vozes, paths, DPI)            │
                               └─────────────────────────────┘
```

**Por que essa separação importa na prática**: `core/pdf_renderer.py` e
`core/dictionary.py` são os únicos módulos com testes automatizados
(`tests/`) justamente porque não dependem de Tk — dá para instanciar
`PDFRenderer` e chamar `dic.lookup()` num teste puro. Qualquer lógica que
acabar vazando para dentro de um mixin de `ui/` fica, na prática,
impossível de testar sem montar uma janela Tkinter real.

## 4. Estrutura de diretórios

```
Leitor_pdf_v2/
├── main.py                    # ponto de entrada — só App().mainloop()
├── config.py                  # cores (C), fontes (FONTS), vozes (VOICES),
│                               # velocidades (SPEEDS), paths, DPI — única
│                               # fonte de verdade para toda a UI
├── core/                      # lógica de negócio, sem dependência de UI
│   ├── pdf_renderer.py        # PDFRenderer: abrir/renderizar/extrair/buscar
│   ├── dictionary.py          # lookup() — cascata de backends + cache
│   ├── tts.py                 # speak() — edge-tts assíncrono
│   └── player.py              # Player — wrapper de pygame.mixer.music
├── data/                      # persistência em JSON, cache em memória
│   ├── _jsonio.py             # load_json/save_json — I/O atômico + backup
│   ├── library.py             # biblioteca de livros (progresso, "lido")
│   ├── history.py             # histórico de sessões de leitura
│   ├── highlights.py          # grifos manuais/automáticos por livro/página
│   └── prefs.py                # voz/velocidade/volume/zoom/autoscroll/cor
├── ui/                         # interface — App = composição de mixins
│   ├── app.py                  # App(*Mixins, ctk.CTk): init, build, atalhos,
│   │                            # cronômetro, salvamento de sessão, _quit
│   ├── sidebar.py               # SidebarMixin: biblioteca, abrir/carregar PDF
│   ├── viewer.py                 # ViewerMixin: canvas, zoom/pan, busca de texto
│   ├── controls.py               # ControlsMixin: transporte, loop de leitura TTS
│   ├── right_panel.py             # RightPanelMixin: voz/velocidade/volume/grifos
│   ├── highlights_mixin.py        # HighlightsMixin: seleção manual, auto-highlight
│   ├── dict_popup.py               # DictPopupMixin: clique em palavra → popup
│   ├── toc_window.py                # TocMixin: janela de sumário
│   ├── focus_dialog.py               # FocusMixin: diálogo e countdown do modo foco
│   └── widgets.py                     # flat_button() — botão Frame+Label reutilizável
├── tests/                       # pytest — cobre core/pdf_renderer, core/dictionary,
│                                 # data/_jsonio (ui/ não tem testes automatizados)
├── .github/workflows/ci.yml     # ruff check + pytest em cada push/PR
├── main.spec                     # receita do PyInstaller (dist/main.exe)
├── library.json, history.json,   # ESTADO DO USUÁRIO — nunca versionado
│ highlights.json, prefs.json,    # (.gitignore), gerado em runtime ao lado
│ .window_geometry                # do executável/script
├── README.md                      # instalação, uso, atalhos
├── ADICIONAR_FUNCIONALIDADE.md    # guia rápido "quero mudar X → edito Y"
└── DOCUMENTACAO_TECNICA.md        # este arquivo
```

## 5. Ciclo de vida da aplicação

1. `main.py` instancia `ui.app.App()` e chama `.mainloop()` — é o único
   código fora de `ui/`/`core/`/`data/`/`config.py`.
2. `App.__init__`:
   - Restaura geometria da janela salva em `.window_geometry`.
   - Carrega preferências (`data/prefs.py`) — voz, velocidade, volume, zoom,
     auto-scroll, cor de grifo — com fallback para os padrões de `config.py`
     quando ausentes ou inválidas.
   - Inicializa estado em memória (página atual, chunk atual, locks,
     flags de modo foco/seleção de grifo).
   - Cria o `Player` (inicializa `pygame.mixer`).
   - Chama `_build()` (monta sidebar + área central + painel direito, cada
     um delegado a um mixin), `_bind_keys()` (atalhos globais) e registra
     `_quit` no `WM_DELETE_WINDOW`.
   - Chama `_refresh_lib()` (popula a lista de livros) e `_tick_timer()`
     (inicia o cronômetro de sessão, que se re-agenda via `self.after(1000, ...)`).
3. Usuário abre um PDF (botão "Abrir PDF", `Ctrl+O`, ou clique num livro da
   biblioteca) → `SidebarMixin._load_book` → thread de background abre o
   `PDFRenderer` → volta para a UI thread via `self.after(0, ...)` →
   `_on_book_opened` dispara `_show_page()` e inicia o `_read_loop` (asyncio
   rodando em outra thread).
4. Ao fechar a janela, `App._quit()`:
   - Se o modo foco está ativo, pede confirmação antes de sair.
   - Marca `self._alive = False` (evita que callbacks `self.after(...)`
     agendados por threads em background toquem em widgets já destruídos).
   - Sinaliza `self._stop` (para o loop de leitura), salva posição/sessão,
     força flush dos grifos, encerra `pygame`, fecha o `PDFRenderer`, limpa
     `.tmp_audio/`, salva a geometria da janela e sai (`sys.exit()`).

## 6. Camada `core/` — lógica de negócio

### 6.1 `core/pdf_renderer.py` — `PDFRenderer`

Encapsula o PyMuPDF. **Nunca deve ser instanciado na thread principal** em
livros grandes — o `__init__` varre **todas** as páginas do documento para
detectar cabeçalhos/rodapés repetidos (por isso `ui/sidebar.py` sempre cria
o renderer numa `threading.Thread`).

| Membro | Descrição |
|---|---|
| `PDFOpenError` | Exceção com mensagem já segura para exibir ao usuário (arquivo corrompido, protegido por senha, sem páginas, caminho inexistente). |
| `__init__(filepath)` | Abre o documento; levanta `PDFOpenError` para qualquer falha; detecta cabeçalho/rodapé repetido (linha que aparece em ≥30% das páginas, mínimo 3) para remover do texto lido pelo TTS. |
| `render_page(n) -> PIL.Image` | Rasteriza a página `n` (0-indexed) em `PDF_RENDER_DPI` (config, padrão 100). Cache **LRU real** de até 10 páginas (`OrderedDict` + `move_to_end`/`popitem(last=False)`). |
| `text_for_page(n) -> str` | Texto normalizado (NFKC) para o TTS: remove linhas iguais ao cabeçalho/rodapé detectado, corrige hifenização de fim de linha (`pala-\nvra` → `palavra`), remove números de página isolados, colapsa espaços/quebras. |
| `search_text(n, text) -> list[dict]` | Ver [§9.3](#93-busca-de-texto-e-grifo-automático-search_text) — heurística de 4 etapas para localizar um trecho na página e retornar bboxes em pontos PDF. |
| `word_at(n, pdf_x, pdf_y) -> str \| None` | Palavra sob um ponto (usado no clique do dicionário). |
| `prefetch(n)` | Dispara threads daemon para pré-renderizar `n-1`/`n+1` (esconde a latência de troca de página). |
| `get_toc() -> list[(level, title, page)]` | Sumário do PDF (bookmarks nativos); `[]` se ausente. |
| `close()` | Fecha o documento e limpa o cache. |

### 6.2 `core/dictionary.py` — `lookup()`

Busca definição de uma palavra através de uma **cascata de backends**, com
cache em memória (não persiste em disco — reinicia a cada execução do app).

```
detected_lang == "en"  → Free Dictionary API (en)
detected_lang == "es"  → Free Dictionary API (es)
default (pt-BR/None)   → dicio.com.br (scraping)
                        → Wiktionary PT (REST)
                        → Free Dictionary API (en)
                        → Free Dictionary API (es)
```

Cada backend é uma função `_lookup_*` isolada e testável (`tests/test_dictionary.py`
faz monkeypatch nelas diretamente). Retorno padronizado:

```python
{
    "word": str, "phonetic": str | None, "lang": str,
    "source": "dicio.com.br" | "wiktionary" | "freedictionary",
    "meanings": [{"part_of_speech": str, "definitions": [str, ...]}],
}
```

**Cache com TTL assimétrico** — decisão de design relevante:
- Resultado **positivo** (palavra encontrada) → cacheado **para sempre**
  (`expires_at = None`), pois a definição de uma palavra não muda em runtime.
- Resultado **negativo** (nenhum backend encontrou) → cacheado por
  `_NEG_CACHE_TTL = 600s`, para não travar permanentemente uma palavra que
  na verdade existe mas falhou por instabilidade momentânea de um backend.
- Erro de **rede** em todos os backends tentados → retorna
  `{"_network_error": True}` e **não cacheia** — permite nova tentativa assim
  que a conexão voltar. A UI (`ui/dict_popup.py`) usa essa chave para mostrar
  "Sem conexão com a internet" em vez de "Definição não encontrada".

`detect_lang(text)` usa `langdetect`; falha silenciosa (`None`) se a
biblioteca não conseguir decidir.

### 6.3 `core/tts.py` — `speak()`

```python
async def speak(text: str, voice: str, speed_pct: int) -> tuple[bytes, list[dict]]
```

Streama de `edge_tts.Communicate`, acumulando bytes de áudio (MP3) e eventos
`WordBoundary` (convertidos de *ticks* de 100ns para segundos) em
`[{"word", "start", "end"}, ...]` — é essa lista de timings que permite o
destaque **palavra por palavra** sincronizado com o áudio. Qualquer falha
(sem internet, voz indisponível, timeout) é logada e retorna `(b"", [])` sem
lançar exceção — quem chama (`ControlsMixin._read_loop`) trata áudio vazio
como "pular este trecho" e mostra aviso transitório na UI.

### 6.4 `core/player.py` — `Player`

Wrapper fino sobre `pygame.mixer.music` (áudio único, carregado a partir de
bytes via `io.BytesIO`, sem tocar disco). Ponto sutil: `pygame.mixer.music`
não tem uma API nativa de "posição acumulada através de pausas", então
`Player` mantém `_offset_seconds` manualmente — cada `pause()` soma o tempo
decorrido antes de pausar, e `get_pos()` soma o offset acumulado ao tempo
decorrido do trecho atual. Isso é o que permite ao loop de leitura
sincronizar o destaque de palavra com `timings` mesmo através de
pausas/retomadas.

## 7. Camada `data/` — persistência

Todos os quatro módulos (`library`, `history`, `highlights`, `prefs`) seguem
o mesmo padrão: **cache em memória (`_cache` module-level) + `_jsonio.py`**
para I/O em disco. Isso evita reler o JSON do zero a cada chamada, mantendo
uma única fonte de verdade em memória durante a execução do processo.

### 7.1 `data/_jsonio.py` — fundação compartilhada

```python
load_json(path, default) -> Any
save_json(path, data) -> bool
```

- **Escrita atômica**: grava em `<path>.tmp` e faz `tmp.replace(path)` — um
  crash no meio da escrita nunca deixa o JSON principal truncado/corrompido.
- **Backup em vez de descarte silencioso**: se o JSON existente falhar ao
  parsear, o arquivo é renomeado para `<path>.corrupted` (preservando os
  dados do usuário para inspeção manual) e a função retorna `default` em vez
  de lançar exceção.
- Toda falha é logada (`log.error`/`log.warning`) em vez de engolida por um
  `except: pass` — decisão explicitamente documentada no cabeçalho do
  arquivo como correção de uma auditoria de código anterior.

### 7.2 `library.json` — biblioteca de livros

Chave = caminho absoluto do PDF.

```json
{
  "/caminho/livro.pdf": {
    "last_page": 12,
    "last_chunk_idx": 3,
    "total_pages": 240,
    "finished": false
  }
}
```

API: `add`, `remove`, `get`, `save_position(path, page, chunk_idx)`,
`save_total`, `mark_finished`, `is_finished`, `all_books()`.

### 7.3 `history.json` — histórico de sessões

Lista append-only, uma sessão por entrada:

```json
[{"start": "13/09/2026 14:02", "duration": "00h 12m 30s",
  "seconds": 750.0, "book": "livro.pdf"}]
```

`add_session(...)` é chamado a cada `_toggle_play` para pausa e no `_quit`.

### 7.4 `highlights.json` — grifos por livro/página

```json
{
  "/caminho/livro.pdf": {
    "3": [
      {"x0": 72.5, "y0": 100.2, "x1": 400.1, "y1": 115.8,
       "color": "#FFDD00", "opacity": 0.35}
    ]
  }
}
```

Coordenadas em **pontos PDF** (não pixels de tela — independentes de
zoom/DPI). `add()` deduplica retângulos quase idênticos (margem de 1pt).
Toda operação que modifica grifos (`add`, `delete`, `clear_page`,
`clear_book`) persiste **imediatamente** (`save_to_disk()` interno) — grifos
não dependem mais de fechamento normal do app para não se perderem num
crash.

### 7.5 `prefs.json` — preferências persistidas entre sessões

```json
{
  "voice": "Antonio (PT-BR)", "speed": "1×", "volume": 0.7,
  "zoom": 2.5, "autoscroll": true,
  "highlight_color_label": "🟡 Amarelo"
}
```

`_DEFAULTS` define o schema; `get_all()` faz merge com o que está salvo, de
modo que adicionar uma nova preferência no futuro não quebra arquivos
antigos (chaves ausentes caem no default).

## 8. Camada `ui/` — interface (mixins)

`App` não implementa a UI diretamente: ela **herda de 8 mixins**, cada um
responsável por uma área da tela ou uma funcionalidade transversal:

```python
class App(SidebarMixin, ViewerMixin, ControlsMixin, RightPanelMixin,
          HighlightsMixin, DictPopupMixin, TocMixin, FocusMixin, ctk.CTk):
```

Essa reorganização (documentada em [`implementation_plan.md`](implementation_plan.md))
separou o antigo `app.py` monolítico de 2.271 linhas sem alterar
comportamento — cada mixin assume que `self` tem os atributos que `App.__init__`
inicializa (ex.: `self.renderer`, `self._zoom`, `self.player`), então os
mixins **não são reutilizáveis fora de `App`** — são partições de uma única
classe, não componentes independentes.

| Mixin | Arquivo | Responsabilidade |
|---|---|---|
| `SidebarMixin` | `sidebar.py` | Lista de livros (abas "Lendo"/"Lidos"), abrir arquivo, carregar PDF em background, marcar como lido |
| `ViewerMixin` | `viewer.py` | Canvas da página, topbar, zoom/pan, conversão de coordenadas canvas↔PDF, busca de texto no documento inteiro |
| `ControlsMixin` | `controls.py` | Barra de transporte (play/pause/prev/next), **loop assíncrono de leitura TTS**, auto-scroll |
| `RightPanelMixin` | `right_panel.py` | Construção do painel direito: voz, velocidade, volume, cor de grifo, marcar lido, modo foco, sumário |
| `HighlightsMixin` | `highlights_mixin.py` | Seleção manual de grifo (drag no canvas), remoção (clique direito), cálculo de bboxes palavra-por-palavra, exportação para Markdown |
| `DictPopupMixin` | `dict_popup.py` | Clique em palavra → popup de definição (rolável, auto-posicionado) |
| `TocMixin` | `toc_window.py` | Janela popup do sumário, navegação por clique |
| `FocusMixin` | `focus_dialog.py` | Diálogo de configuração e countdown do modo foco |

`ui/widgets.py` fornece `flat_button()` — um "botão" `tk.Frame`+`tk.Label`
com hover, usado em praticamente todos os mixins para evitar duplicar a
mesma lógica de bind de `<Button-1>`/`<Enter>`/`<Leave>`.

## 9. Fluxos-chave em detalhe

### 9.1 Abertura de um PDF (sem travar a UI)

```
usuário clica em "Abrir PDF" / livro da biblioteca
  → SidebarMixin._load_book(path)
      · cancela leitura em andamento (_stop.set(), player.stop())
      · fecha renderer anterior; limpa canvas; mostra "Abrindo…"
      · dispara threading.Thread(_open_book_bg, args=(path,))
  → [thread background] _open_book_bg
      · PDFRenderer(path)  ← pode ser lento (varredura de cabeçalho/rodapé)
      · self.after(0, lambda: self._on_book_opened(...))   # volta p/ UI thread
  → [UI thread] _on_book_opened
      · restaura last_page/last_chunk_idx de library.json
      · _show_page(current_page)
      · threading.Thread(asyncio.run(self._read_loop()))    # nova thread p/ o loop de leitura
```

Ponto crítico documentado no próprio código: a exceção `e` de um
`except PDFOpenError as e` é apagada pelo Python ao sair do bloco `except`,
então a mensagem precisa ser copiada para uma variável local (`msg = str(e)`)
**antes** de ser capturada pela lambda que roda depois, via `self.after`,
fora do escopo do `except` — senão vira `NameError` em runtime.

### 9.2 Loop de leitura (`ControlsMixin._read_loop`, assíncrono)

Roda em `asyncio.run(...)` dentro de uma thread dedicada (thread ≠ UI thread;
comunicação com Tk sempre via `self.after(0, ...)`). Pseudocódigo do fluxo
por página:

1. Extrai texto da página (`renderer.text_for_page`), divide em frases via
   regex `(?<=[.!?])\s+|\n`.
2. Detecta idioma da página (primeiros 500 chars) para alimentar o
   dicionário.
3. Para cada frase (chunk), a partir de `current_chunk_idx`:
   - **Pipeline de pré-geração**: enquanto o chunk `i` está tocando, já
     dispara `asyncio.create_task(get_audio(chunks[i+1]))` para o próximo —
     esconde a latência de rede do TTS entre frases.
   - Assim que o áudio chega, grifa o chunk inteiro imediatamente
     (`_highlight_ephemeral`, garante destaque mesmo antes do primeiro
     word-timing) e pré-calcula os bboxes por palavra
     (`_precompute_word_bboxes`) usando os `timings` do edge-tts.
   - `player.play(audio)` e então um loop de polling (`await asyncio.sleep(0.03)`)
     que consulta `player.get_pos()` e atualiza o grifo efêmero para a
     palavra correspondente ao tempo de reprodução atual — é isso que produz
     o destaque **palavra por palavra** sincronizado.
   - Áudio vazio (falha de TTS) não trava o loop: mostra aviso transitório
     (`_show_transient_status`) e segue para a próxima frase.
4. Ao esgotar as frases da página, avança para `current_page + 1`; se for a
   última página, marca o livro como lido (`lib.mark_finished`).
5. O loop inteiro observa `self._stop` (um `threading.Event`) — qualquer
   ação do usuário (próxima/página anterior, seek, TOC) chama
   `_restart_loop()`, que seta `_stop`, para o player, e — depois de um
   pequeno delay de segurança contra *race condition* do pygame — dispara um
   novo loop a partir da posição atualizada.

### 9.3 Busca de texto e grifo automático (`search_text`)

`PDFRenderer.search_text(n, text)` é o algoritmo mais elaborado do projeto —
localizar um trecho arbitrário de texto (uma frase gerada pelo próprio TTS,
ou o termo digitado na busca) dentro da página e devolver suas coordenadas,
mesmo quando o PDF tem hifenização, colunas ou pequenas diferenças de
normalização entre o texto extraído e o texto renderizado. Estratégia em 4
etapas, cada uma mais tolerante que a anterior:

1. **`page.search_for(text, quads=True)`** — casamento exato via PyMuPDF;
   cobre a maioria dos casos, inclusive frases que atravessam linhas.
2. **Âncora pelo início** — tenta as primeiras 5/4/3/2 palavras do trecho em
   sequência contra as palavras da página; ao achar, acumula linhas seguintes
   até cobrir o número de palavras do chunk.
3. **Âncora pelo final** — últimas 3 palavras; útil quando o início do
   trecho é genérico mas o final é único, estima quantas linhas voltar.
4. **Fallback por palavras únicas** — só ativa para chunks com ≥6 palavras
   "significativas" (>4 caracteres); usa palavras que aparecem exatamente
   uma vez na página para localizar linhas inteiras.

Essa mesma função é reutilizada em três lugares diferentes: busca de texto
do usuário (`Ctrl+F`), grifo automático de frase (`_highlight_ephemeral`) e
grifo automático de palavra (`_precompute_word_bboxes`, com uma janela de
contexto de até 2 palavras antes/depois para desambiguar palavras repetidas
na página) — nos dois últimos casos, um "cursor Y" (`_eph_y_cursor`) garante
que o destaque nunca "regride" verticalmente na página, mesmo quando a
mesma palavra aparece mais de uma vez.

### 9.4 Zoom, pan e mapeamento de coordenadas

A página é renderizada uma vez por `PDF_RENDER_DPI` (100 DPI) e cacheada como
`PIL.Image`; zoom/pan são aplicados **apenas na composição final**
(`_draw_image`), nunca re-rasterizando o PDF — troca de zoom é instantânea.

- `base_scale = min(canvas_w/img_w, canvas_h/img_h)` — escala que encaixa a
  página inteira no canvas (zoom 100% "lógico").
- `scale = base_scale * self._zoom` — zoom do usuário (1.0 a 5.0) multiplica
  essa base.
- Grifos (armazenados em pontos PDF) são desenhados na imagem original
  **antes** do resize/crop, via `zoom_pdf = PDF_RENDER_DPI / 72.0` — depois
  seguem o mesmo `scale` de tudo o mais.
- **Ancoragem no topo ao trocar de página** (`_pan_pending_top`): com zoom
  padrão >100%, centralizar verticalmente cortaria o topo da página (onde o
  texto normalmente começa) até o autoscroll alcançar o texto — por isso a
  primeira renderização de uma página nova força `pan_y` para o topo.
- `_canvas_to_pdf_coords(cx, cy)` faz o caminho inverso — usado tanto para
  clique de dicionário quanto para seleção manual de grifo — aplicando a
  mesma fórmula de escala/pan em ordem reversa e dividindo por
  `PDF_RENDER_DPI/72` para converter pixels renderizados em pontos PDF.
- Roda do mouse: `Ctrl`+roda sempre dá zoom; roda sozinha faz pan vertical
  quando há zoom ativo, ou passa de página quando a imagem está no tamanho
  de ajuste (100%) — distinção feita via máscara de bit do estado do evento
  Tkinter (`_CONTROL_MASK = 0x0004`).

### 9.5 Grifos manuais vs. automáticos

- **Automático (efêmero)**: gerado durante a leitura TTS (frase/palavra
  atual), vive só em memória (`self._ephemeral_highlights`), nunca é
  persistido, cor `C["info"]` (ciano).
- **Manual (permanente)**: usuário ativa "✏ Selecionar", arrasta um
  retângulo no canvas (`HighlightsMixin._on_sel_*`), que é convertido para
  coordenadas PDF e salvo via `data/highlights.py`. Clique direito sobre um
  grifo existente remove-o (busca do mais recente para o mais antigo, com
  margem de 2pt). Cor escolhida em `RightPanelMixin` dentre
  `config.HIGHLIGHT_COLORS`.
- **Exportação** (`_export_highlights`): para cada grifo salvo, reabre a
  página via `page.get_text("text", clip=rect)` para recuperar o texto
  exato sob o retângulo e gera um `.md` com blockquotes agrupados por
  página.

### 9.6 Dicionário interativo

`_on_canvas_press` → `_on_pan_end` distingue clique de arrasto por distância
(`dx <= 5 and dy <= 5`) → `DictPopupMixin._on_word_click` converte
coordenadas e chama `PDFRenderer.word_at` → busca em thread separada
(`_fetch_and_show` → `core.dictionary.lookup(word, self._detected_lang)`) →
popup `Toplevel` sem borda de janela (`overrideredirect(True)`), com
conteúdo rolável quando excede 70% da altura da tela, auto-posicionado perto
do clique (ajustando se sairia da tela) e fechado por clique fora
(`<FocusOut>`), `Esc`, ou pelo botão "Fechar".

### 9.7 Modo Foco

Bloqueia trocar de livro (`_load_book`) e fechar o app (`_quit`) enquanto
`self._focus_active` é `True`. `FocusMixin._focus_start(minutes)` grava
`_focus_end_ts = time.time() + minutes*60` e inicia um `self.after(1000, ...)`
recursivo (`_focus_tick`) que atualiza o label de contagem regressiva até
zerar (`_focus_end_naturally`) ou ser cancelado manualmente
(`_focus_cancel`, com confirmação).

## 10. Concorrência

O projeto usa três mecanismos concorrentes coexistindo sobre uma única UI
thread do Tkinter:

| Mecanismo | Onde | Por quê |
|---|---|---|
| `threading.Thread(daemon=True)` | Abertura de PDF, renderização de página, prefetch, busca de dicionário, busca de texto em todas as páginas | Operações de I/O bloqueante (disco, rede) que não podem travar a UI |
| `asyncio` dentro de uma thread dedicada | `_read_loop` (`asyncio.run(...)` numa thread própria) | `edge-tts` é uma API assíncrona nativa; permite pré-gerar o próximo áudio (`asyncio.create_task`) enquanto o atual toca |
| `self.after(0, callback)` | Toda vez que uma thread de background precisa tocar em um widget Tkinter | Tkinter não é thread-safe — `after(0, ...)` reagenda o callback para rodar na UI thread |

Dois guardas explícitos contra corrida:
- `self._state_lock` (`threading.Lock`) protege `current_chunk_idx`, lido
  tanto pela UI (para salvar posição) quanto escrito pelo `_read_loop`.
- `self._alive` (bool) é setado para `False` em `_quit()` **antes** de
  qualquer outra coisa — todo callback agendado via `self.after` que roda em
  background checa `self._alive` antes de tocar em widgets, evitando
  `TclError` de "widget já destruído" quando o app fecha com threads ainda
  em voo.

## 11. Configuração (`config.py`)

Única fonte de verdade para tudo que normalmente seria hardcoded espalhado
pela UI:

- `C` — paleta de cores (dark theme fixo).
- `FONTS` — tipografia (Georgia para leitura, Courier para labels/mono).
- `VOICES` — nome de exibição → voz `edge-tts` (`pt-BR-AntonioNeural`, etc.).
- `SPEEDS` — label → percentual relativo (`-50` a `+100`).
- `HIGHLIGHT_COLORS` — cores disponíveis para grifo manual.
- `PDF_RENDER_DPI` — resolução de rasterização (100; subir aumenta
  qualidade e custo de memória/CPU).
- Paths (`LIBRARY_FILE`, `HISTORY_FILE`, `HIGHLIGHTS_FILE`, `PREFS_FILE`,
  `GEOMETRY_FILE`, `TEMP_DIR`) — resolvidos por `_pick_base_dir()`.

**`_pick_base_dir()`** merece destaque: por padrão os JSONs de estado ficam
ao lado do executável/script (`_FROZEN_BASE`). Se essa pasta não for
gravável — típico de um `.exe` instalado em `C:\Program Files\` sem
permissão de usuário comum — a função testa a escrita (`touch`/`unlink`) e,
se falhar, cai para `%APPDATA%\Lector` (Windows) ou
`~/.local/share/Lector` (Linux/Mac), para nunca perder biblioteca/histórico/
grifos silenciosamente.

Todo token novo de cor/fonte/voz deve ser adicionado **aqui**, nunca
hardcoded num arquivo de `ui/` — é a regra de ouro repetida tanto no
`README.md` quanto no `ADICIONAR_FUNCIONALIDADE.md`.

## 12. Tratamento de erros e resiliência

Padrão consistente em todo o projeto — falhas de I/O externo (disco, rede,
parsing) nunca derrubam o processo nem falham silenciosamente:

| Camada | Falha possível | Tratamento |
|---|---|---|
| `PDFRenderer.__init__` | Arquivo corrompido, senha, sem páginas, caminho inválido | `PDFOpenError` com mensagem amigável → `messagebox.showerror` na UI |
| `core.dictionary.lookup` | Timeout/erro de conexão em qualquer backend | `DictionaryNetworkError` interna → agregada em `{"_network_error": True}` se **todos** os backends tentados falharam por rede |
| `core.tts.speak` | Sem internet, voz indisponível, timeout | Loga e retorna `(b"", [])` — chamador trata como "pular trecho" |
| `data/_jsonio.load_json` | JSON corrompido/inválido | Faz backup (`.corrupted`) e retorna o valor default — nunca lança |
| `data/_jsonio.save_json` | Falha de escrita em disco | Escrita atômica (tmp + rename); em falha, loga erro e remove o tmp órfão |
| `ui/sidebar._open_book_bg` | Qualquer exceção ao abrir PDF | Sempre volta para a UI thread com uma mensagem de erro; nunca deixa `current_path` apontando para um livro que falhou |

## 13. Testes

```
tests/
├── conftest.py           # fixtures: PDF de 3 páginas gerado em memória
│                          # via pymupdf (sample_pdf_path), PDF corrompido
│                          # (corrupted_pdf_path) — não depende de binário
│                          # versionado no repo
├── test_pdf_renderer.py  # abertura válida/corrompida/inexistente,
│                          # extração de texto, search_text (frase completa,
│                          # sem match, página fora do range), word_at,
│                          # cache LRU, TOC
├── test_dictionary.py    # _clean_word, _normalize_slug, cache positivo
│                          # (sem TTL) vs. negativo (com TTL), distinção
│                          # erro-de-rede vs. não-encontrado, parsing do
│                          # Free Dictionary API
└── test_jsonio.py        # roundtrip save/load, atomicidade (sem .tmp
                           # órfão), backup de arquivo corrompido
```

Cobertura é deliberadamente focada em `core/` e `data/_jsonio.py` — os
módulos sem dependência de Tk e com a lógica mais arriscada
(`search_text` tem 4 estratégias heurísticas; o cache de dicionário tem
semântica de TTL assimétrica). `ui/` não tem testes automatizados —
verificação é manual, seguindo o checklist do
[`implementation_plan.md`](implementation_plan.md#verificação).

```bash
pytest              # roda tudo
pytest -q            # saída enxuta (usada no CI)
ruff check .          # lint (E, F, I, B, UP — ver pyproject.toml)
```

## 14. CI/CD

`.github/workflows/ci.yml` roda em `windows-latest` (a plataforma alvo
principal) a cada push/PR em `main`: instala `requirements.txt` +
`requirements-dev.txt`, roda `ruff check .` e `pytest -q`. Não há deploy
automatizado — o `.exe` é gerado manualmente via PyInstaller quando
necessário.

## 15. Build e distribuição (PyInstaller)

```bash
pip install pyinstaller
pyinstaller main.spec
```

Gera `dist/main.exe` (single-file, sem console — `console=False`). Duas
armadilhas resolvidas no `main.spec`:

- `langdetect` carrega seus perfis de idioma como *data files* via
  `pkgutil`, que a análise estática do PyInstaller não detecta sozinha —
  sem `collect_data_files("langdetect")` a detecção de idioma falha
  **silenciosamente** só no `.exe` (funciona normalmente com
  `python main.py`).
- `collect_submodules("bs4")` garante que os parsers do BeautifulSoup sejam
  empacotados.

`dist/` e `build/` são artefatos gerados — cobertos pelo `.gitignore`,
nunca devem ser commitados.

## 16. Atalhos de teclado

| Atalho | Ação | Implementado em |
|---|---|---|
| `Espaço` | Play/pause | `ControlsMixin._toggle_play` |
| `←` / `→` | Frase anterior/próxima | `ControlsMixin._prev_chunk` / `_next_chunk` |
| `Ctrl` + `←` / `→` | Página anterior/próxima | `ControlsMixin._prev_page` / `_next_page` |
| `Ctrl+F` | Buscar no texto | `ViewerMixin._open_search` |
| `Ctrl+O` | Abrir PDF | `SidebarMixin._open_file` |
| `+` / `-` | Zoom in/out | `ViewerMixin._zoom_in` / `_zoom_out` |
| `Ctrl+0` | Resetar zoom | `ViewerMixin._zoom_reset` |
| `Ctrl+Shift+F` | Modo Foco | `FocusMixin._open_focus_dialog` |
| `Esc` | Fecha popup/busca/diálogo aberto | `App._on_escape` + binds locais de cada `Toplevel` |
| `Ctrl` + roda | Zoom (roda sozinha: pan/página) | `ViewerMixin._on_mousewheel` |

## 17. Limitações conhecidas e melhorias futuras

- **Sem testes automatizados para `ui/`** — qualquer regressão de
  comportamento visual/interação só é pega manualmente.
- **Cache de dicionário não persiste entre execuções** — reinicia a cada
  abertura do app (é só em memória, `_dict_cache` a nível de módulo).
- **`search_text` é heurístico** — em PDFs com layout muito irregular
  (colunas complexas, tabelas, texto rotacionado), o grifo automático pode
  falhar em localizar a frase exata (o loop de leitura continua tocando o
  áudio normalmente; só o destaque visual pode ficar impreciso).
- **Um único processo, um único documento aberto por vez** — não há suporte
  a múltiplas janelas/abas.
- **`.venv/`, `build/`, `dist/`, `__pycache__/` presentes no diretório de
  trabalho local** — devem permanecer fora do controle de versão (já
  cobertos pelo `.gitignore`).
- **Scraping de dicio.com.br** é o backend PT-BR primário — sujeito a
  quebrar se a estrutura HTML do site mudar (não há teste de integração
  contra o site real, só parsing de HTML fixado como fixture).

## 18. Glossário

| Termo | Significado no contexto do projeto |
|---|---|
| **Chunk** | Uma frase (ou linha) do texto da página, unidade de leitura do TTS — página é dividida em chunks via regex de pontuação/quebra de linha. |
| **Grifo efêmero** | Destaque visual temporário (frase/palavra sendo lida), nunca persistido. |
| **Grifo manual** | Destaque persistente, criado pelo usuário via seleção no canvas, salvo em `highlights.json`. |
| **Word-timing / word-boundary** | Evento do `edge-tts` que informa o instante (em segundos) em que cada palavra começa/termina a ser falada — base do destaque palavra-por-palavra. |
| **Base dir** | Pasta onde os JSONs de estado do usuário são gravados — ao lado do executável por padrão, com fallback para `%APPDATA%/Lector`. |
| **Pontos PDF** | Unidade de coordenadas nativa do PDF (72 pontos = 1 polegada), independente da resolução (DPI) de rasterização usada para exibir a página. |
