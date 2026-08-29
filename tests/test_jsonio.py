"""
Testes de data/_jsonio.py — escrita atômica e backup de arquivo
corrompido em vez de descartar dados do usuário silenciosamente.
"""
from data._jsonio import load_json, save_json


def test_load_json_missing_file_returns_default(tmp_path):
    path = tmp_path / "nao_existe.json"
    assert load_json(path, {"x": 1}) == {"x": 1}


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "data.json"
    data = {"livro.pdf": {"last_page": 5}}
    assert save_json(path, data) is True
    assert load_json(path, {}) == data


def test_save_json_is_atomic_no_leftover_tmp_file(tmp_path):
    path = tmp_path / "data.json"
    save_json(path, {"a": 1})
    tmp_file = path.with_suffix(path.suffix + ".tmp")
    assert not tmp_file.exists()


def test_load_corrupted_file_backs_up_and_returns_default(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("isto nao e json valido {{{", encoding="utf-8")

    result = load_json(path, {"fallback": True})

    assert result == {"fallback": True}
    backup = path.with_suffix(path.suffix + ".corrupted")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "isto nao e json valido {{{"
