"""
data/_jsonio.py — leitura/escrita de JSON compartilhada por library.py,
history.py, highlights.py e prefs.py.

Objetivos (ver auditoria de código):
  - Escrita atômica (arquivo temporário + rename) para não corromper o
    arquivo se o app crashar no meio da escrita.
  - Logar falhas em vez de engolir silenciosamente (`except: pass`).
  - Se um arquivo existente estiver corrompido, faz backup em vez de
    simplesmente descartar os dados do usuário sem aviso.
"""
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def load_json(path: Path, default: Any) -> Any:
    """Lê `path` como JSON. Se não existir, retorna `default`.
    Se existir mas estiver corrompido, faz backup do arquivo e retorna
    `default` (nunca lança exceção para o chamador)."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Falha ao ler %s (%s) — tratando como corrompido.", path, e)
        _backup_corrupted(path)
        return default


def save_json(path: Path, data: Any) -> bool:
    """Escreve `data` como JSON em `path` de forma atômica.
    Retorna True em sucesso, False em falha (loga o erro)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception as e:
        log.error("Falha ao salvar %s: %s", path, e)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _backup_corrupted(path: Path) -> None:
    try:
        backup = path.with_suffix(path.suffix + ".corrupted")
        path.replace(backup)
        log.warning("Arquivo corrompido movido para %s — dados anteriores preservados ali.", backup)
    except Exception as e:
        log.error("Não foi possível salvar backup do arquivo corrompido %s: %s", path, e)
