"""LECTOR — leitor de PDF com narração e grifo sincronizado (interface Qt)."""
import os
import sys

# Silencia o banner do pygame no console.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.app import App  # noqa: E402
from ui.theme import app_font, build_qss, dark_palette  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Lector")
    app.setStyle("Fusion")            # base consistente entre máquinas; o QSS faz o resto
    app.setPalette(dark_palette())
    app.setFont(app_font())
    app.setStyleSheet(build_qss())

    window = App()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
