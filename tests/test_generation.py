"""
Testes de core/generation.py — garante que uma geração antiga nunca
volte a ser considerada "atual" depois que uma nova começa, mesmo que a
execução antiga esteja parada (ex.: bloqueada num await) no momento em
que a troca acontece. Ver ui/controls.py (_read_loop) para o uso real.
"""
from core.generation import GenerationGuard


def test_first_token_is_current():
    g = GenerationGuard()
    token = g.next()
    assert g.is_current(token)


def test_new_generation_invalidates_old_token():
    g = GenerationGuard()
    old = g.next()
    new = g.next()
    assert not g.is_current(old)
    assert g.is_current(new)


def test_invalidate_without_starting_new_generation():
    g = GenerationGuard()
    token = g.next()
    g.invalidate()
    assert not g.is_current(token)


def test_old_token_never_becomes_current_again():
    """Simula a thread antiga sendo liberada (ex.: um await que retorna)
    depois que várias trocas já aconteceram — ela não deve achar que
    ainda é a atual."""
    g = GenerationGuard()
    old = g.next()
    for _ in range(5):
        g.next()
    assert not g.is_current(old)
