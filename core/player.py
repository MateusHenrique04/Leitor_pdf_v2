"""
core/player.py — controla reprodução de áudio via pygame.
"""
import os
import pygame
from config import TEMP_DIR


class Player:
    def __init__(self):
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        self._volume  = 0.7
        self._paused  = True
        self._toggle  = False
        self._offset_seconds: float = 0.0   # acumula tempo antes de pausas
        pygame.mixer.music.set_volume(self._volume)

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, v: float):
        self._volume = max(0.0, min(1.0, v))
        pygame.mixer.music.set_volume(self._volume)

    def play(self, data: bytes):
        """Carrega e toca bytes MP3 da memória."""
        import io
        self._offset_seconds = 0.0
        pygame.mixer.music.load(io.BytesIO(data), "mp3")
        pygame.mixer.music.play()
        if self._paused:
            pygame.mixer.music.pause()

    def pause(self):
        raw_ms = pygame.mixer.music.get_pos()
        if raw_ms >= 0:
            self._offset_seconds += raw_ms / 1000.0
        pygame.mixer.music.pause()
        self._paused = True

    def unpause(self):
        pygame.mixer.music.unpause()
        self._paused = False

    def get_pos(self) -> float:
        """Retorna a posição atual de reprodução em segundos."""
        if not pygame.mixer.get_init():
            return 0.0
        raw_ms = pygame.mixer.music.get_pos()
        if raw_ms < 0:
            return self._offset_seconds
        return self._offset_seconds + raw_ms / 1000.0

    def stop(self):
        pygame.mixer.music.stop()

    def is_busy(self) -> bool:
        return pygame.mixer.music.get_busy()

    def quit(self):
        pygame.mixer.quit()
