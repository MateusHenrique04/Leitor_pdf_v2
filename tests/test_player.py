"""
Testes de core/player.py.

pygame não é instalável neste ambiente de desenvolvimento (sem wheel para
a versão do Python aqui disponível), então estes testes substituem
`pygame` por um dublê mínimo em sys.modules antes de importar
core.player — cobre só a lógica de _offset_seconds/get_pos, que é pura
Python e não depende do mixer de áudio de verdade.
"""
import sys
import types

import pytest


@pytest.fixture
def player_module(monkeypatch, tmp_path):
    """Importa core.player com um pygame falso injetado em sys.modules."""
    music_state = {"pos_ms": 0, "paused": False, "volume": 0.7}

    music = types.SimpleNamespace(
        load=lambda *a, **k: None,
        play=lambda *a, **k: None,
        pause=lambda: music_state.__setitem__("paused", True),
        unpause=lambda: music_state.__setitem__("paused", False),
        stop=lambda: None,
        get_busy=lambda: not music_state["paused"],
        get_pos=lambda: music_state["pos_ms"],
        set_volume=lambda v: music_state.__setitem__("volume", v),
    )
    mixer = types.SimpleNamespace(
        pre_init=lambda *a, **k: None,
        init=lambda *a, **k: None,
        quit=lambda: None,
        get_init=lambda: True,
        music=music,
    )
    pygame_stub = types.ModuleType("pygame")
    pygame_stub.mixer = mixer

    monkeypatch.setitem(sys.modules, "pygame", pygame_stub)
    sys.modules.pop("core.player", None)

    # config.TEMP_DIR precisa existir para Player.__init__ (mkdir).
    monkeypatch.setattr("config.TEMP_DIR", tmp_path, raising=False)

    import core.player as player_mod

    yield player_mod, music_state

    sys.modules.pop("core.player", None)


def test_get_pos_tracks_raw_position_while_playing(player_module):
    player_mod, music_state = player_module
    p = player_mod.Player()
    p._paused = False
    music_state["pos_ms"] = 2000
    assert p.get_pos() == pytest.approx(2.0)


def test_pause_then_get_pos_does_not_double_count(player_module):
    """Bug verificado: pause() somava get_pos() ao offset, e get_pos()
    voltava a somar o offset ao mesmo raw_ms (que o pygame real mantém
    congelado durante a pausa, não reseta) — resultado dobrava a posição
    reportada. Depois da correção, pausar e consultar a posição repetidas
    vezes não deve fazer a posição avançar por conta própria."""
    player_mod, music_state = player_module
    p = player_mod.Player()
    p._paused = False
    music_state["pos_ms"] = 3000   # 3s tocados antes de pausar

    p.pause()
    pos_right_after_pause = p.get_pos()
    pos_again = p.get_pos()   # chamar de novo não pode somar mais nada

    assert pos_right_after_pause == pytest.approx(3.0)
    assert pos_again == pytest.approx(3.0)


def test_unpause_continues_from_paused_position(player_module):
    player_mod, music_state = player_module
    p = player_mod.Player()
    p._paused = False
    music_state["pos_ms"] = 3000
    p.pause()
    p.unpause()
    # Música real continua de onde parou — raw_ms avança 500ms a mais.
    music_state["pos_ms"] = 3500
    assert p.get_pos() == pytest.approx(3.5)


def test_play_resets_offset(player_module):
    player_mod, music_state = player_module
    p = player_mod.Player()
    p._paused = False
    music_state["pos_ms"] = 5000
    p.pause()
    music_state["pos_ms"] = 0
    p.play(b"fake-mp3-bytes")
    assert p.get_pos() == pytest.approx(0.0)
