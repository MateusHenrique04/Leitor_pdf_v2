"""
Token de geração para cancelar trabalho obsoleto entre threads.

Problema que resolve: quando uma ação de longa duração (ex.: o loop de
leitura) pode ser reiniciada antes de terminar, um único threading.Event
compartilhado não basta — se a thread antiga estiver bloqueada num await
de rede no momento em que o Event é limpo para a nova execução, ela nunca
vê o `set()` e volta a rodar junto com a nova (vozes sobrepostas, estado
sendo escrito por duas threads). Um token de geração evita isso: cada
execução pega um número único e só continua escrevendo estado ou agindo
(tocar áudio, redesenhar) enquanto esse número continuar sendo o mais
recente.
"""
import threading


class GenerationGuard:
    """Contador de gerações thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._gen = 0

    def next(self) -> int:
        """Inicia uma nova geração (invalidando a anterior) e retorna seu token."""
        with self._lock:
            self._gen += 1
            return self._gen

    def invalidate(self) -> None:
        """Invalida a geração atual sem iniciar uma nova."""
        with self._lock:
            self._gen += 1

    def is_current(self, token: int) -> bool:
        """True enquanto `token` ainda for a geração mais recente."""
        with self._lock:
            return self._gen == token
