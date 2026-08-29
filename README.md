# Lector — leitor de PDF com narração e dicionário interativo

Aplicativo desktop (Windows/Linux/Mac, Python + Tkinter/CustomTkinter) para
ler PDFs em voz alta com destaque sincronizado por frase, dicionário
interativo (clique numa palavra para ver a definição em PT/EN/ES), grifos
persistentes, biblioteca de livros com progresso salvo, sumário e busca de
texto.

## Funcionalidades

- **Leitura em voz alta (TTS)** via [edge-tts](https://github.com/rany2/edge-tts),
  com auto-scroll sincronizado por frase/palavra.
- **Dicionário interativo**: clique em qualquer palavra do PDF para ver a
  definição (dicio.com.br / Wiktionary para PT-BR, Free Dictionary API
  para EN/ES), com detecção automática de idioma.
- **Grifos (highlights)** manuais e automáticos, persistidos por livro/página,
  exportáveis para Markdown.
- **Biblioteca**: acompanha progresso de leitura, marca livros como lidos.
- **Sumário (TOC)** e **busca de texto** em todo o documento.
- **Modo Foco**: bloqueia trocar de livro/fechar o app por um tempo definido.
- Preferências (voz, velocidade, volume, zoom, cor de grifo, auto-scroll)
  são salvas entre sessões.

## Instalação

Requer **Python 3.11+**.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

## Executar

```bash
python main.py
```

## Atalhos de teclado

| Atalho | Ação |
|---|---|
| `Espaço` | Play/pause |
| `←` / `→` | Frase anterior/próxima |
| `Ctrl` + `←` / `→` | Página anterior/próxima |
| `Ctrl+F` | Buscar no texto |
| `Ctrl+O` | Abrir PDF |
| `+` / `-` | Zoom in/out |
| `Ctrl+0` | Resetar zoom |
| `Ctrl+Shift+F` | Modo Foco |
| `Esc` | Fecha popup de dicionário, busca ou diálogos abertos |
| `Ctrl` + roda do mouse | Zoom (roda sozinha rola/passa de página) |

## Gerar o executável (.exe)

```bash
pip install pyinstaller
pyinstaller main.spec
```

O executável é gerado em `dist/main.exe`. **Não commite `dist/` nem
`build/`** — são artefatos de build, já cobertos pelo `.gitignore`.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt

# Testes
pytest

# Lint
ruff check .
```

O CI (`.github/workflows/ci.yml`) roda `ruff check` e `pytest` em cada
push/PR.

### Estrutura do projeto

```
main.py              # ponto de entrada — só inicializa App()
config.py            # cores, fontes, vozes, paths — única fonte de verdade
core/                 # lógica de negócio, sem dependência de UI
  pdf_renderer.py     # abrir/renderizar PDF, extrair texto, buscar trechos (PyMuPDF)
  dictionary.py       # busca de definições (scraping + APIs)
  tts.py              # geração de áudio (edge-tts)
  player.py           # reprodução de áudio (pygame)
data/                 # persistência em JSON (biblioteca, histórico, grifos, preferências)
ui/                   # interface (CustomTkinter/Tkinter), via mixins compostos em App
tests/                # testes automatizados (pytest)
```

Para instruções detalhadas de onde editar cada tipo de mudança, veja
[`ADICIONAR_FUNCIONALIDADE.md`](ADICIONAR_FUNCIONALIDADE.md).

## Licença

[MIT](LICENSE).
