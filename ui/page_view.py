"""
ui/page_view.py — o visualizador de página (QGraphicsView).

Por que isto é rápido onde o Canvas do Tk não era:

  • A cena usa PONTOS PDF como unidade. Zoom, ajuste à largura e HiDPI viram
    uma única escala na transformação da view; nada é reconvertido a cada
    desenho, e a página inteira nunca é recomposta.
  • A página é uma imagem só (QGraphicsPixmapItem). Rolar e dar pan é o Qt
    mexendo nas barras de rolagem — sem Python no caminho.
  • Os grifos são retângulos em camadas por cima. A voz andando uma palavra
    muda um ou dois retângulos; o Qt repinta só aquela região.
  • A imagem é renderizada na resolução de que a tela precisa (zoom × DPI)
    em uma thread, e trocada quando fica pronta. Enquanto isso a anterior
    continua na tela, só um pouco mais suave — nunca um quadro em branco.
"""
from __future__ import annotations

import logging
import math
import threading

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from config import MAX_RENDER_PIXELS, PAGE_MARGIN_PT, C

log = logging.getLogger(__name__)

ZOOM_MIN = 1.0
ZOOM_MAX = 5.0
ZOOM_STEP = 0.25

# Z dos itens da cena (de baixo para cima).
_Z_PAPER, _Z_PAGE, _Z_SAVED, _Z_SEARCH, _Z_CHUNK, _Z_WORD, _Z_SELECTION = range(7)


class _HighlightItem(QGraphicsRectItem):
    """Retângulo de grifo pintado em modo Multiply: sobre papel branco fica
    a cor do marca-texto e o texto preto continua preto e nítido, como um
    marcador de verdade — em vez de um véu translúcido que desbota a letra."""

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        super().paint(painter, option, widget)
        painter.restore()


class PageView(QGraphicsView):
    clicked = Signal(float, float, QPoint)        # x, y em pontos PDF + posição global
    right_clicked = Signal(float, float)
    selected = Signal(float, float, float, float)  # retângulo selecionado (pontos PDF)
    page_step = Signal(int)                       # roda do mouse sem o que rolar: ±1
    zoom_changed = Signal(float)
    _rendered = Signal(int, int, float, QImage)   # token, página, escala, imagem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor(C["canvas_bg"])))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Barra vertical sempre presente: se ela aparecesse e sumisse, a
        # largura útil mudaria e o ajuste por largura entraria em ciclo.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.verticalScrollBar().setSingleStep(40)
        self.horizontalScrollBar().setSingleStep(40)

        # Itens fixos da cena
        self._paper = self._scene.addRect(
            QRectF(), QPen(Qt.PenStyle.NoPen), QBrush(QColor("#FFFFFF")))
        self._paper.setZValue(_Z_PAPER)
        self._pix = QGraphicsPixmapItem()
        self._pix.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._pix.setZValue(_Z_PAGE)
        self._pix.setVisible(False)
        self._scene.addItem(self._pix)

        self._layers: dict[int, list[_HighlightItem]] = {
            _Z_SAVED: [], _Z_SEARCH: [], _Z_CHUNK: [], _Z_WORD: [],
        }
        self._sel_item: QGraphicsRectItem | None = None
        self._sel_color = C["info"]

        # Estado
        self._renderer = None
        self._page = -1
        self._pw = 612.0
        self._ph = 792.0
        self._zoom = 1.0
        self._fit_mode = "largura"
        self._scale = 1.0          # px lógicos por ponto PDF (ajuste × zoom)
        self._pix_scale = 0.0      # px por ponto da imagem atualmente exibida
        self._token = 0
        self._hl_mode = False
        self._press: QPoint | None = None
        self._pan_last: QPoint | None = None
        self._moved = False
        self._sel_origin = QPointF()
        self._zoom_accum = 0

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._ensure_quality)
        self._rendered.connect(self._on_rendered)

        self._vanim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._hanim = QPropertyAnimation(self.horizontalScrollBar(), b"value", self)
        for anim in (self._vanim, self._hanim):
            anim.setDuration(240)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ──────────────────────────────────────────────────────────────
    # Página
    # ──────────────────────────────────────────────────────────────

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def fit_mode(self) -> str:
        return self._fit_mode

    def clear(self):
        """Esvazia a tela (nenhum livro aberto)."""
        self._renderer = None
        self._page = -1
        self._token += 1
        self._paper.setRect(QRectF())
        self._pix.setVisible(False)
        self._scene.setSceneRect(QRectF())
        for z in self._layers:
            self._set_layer(z, [])

    def show_page(self, renderer, n: int, focus_y: float | None = None):
        """Mostra a página n. A imagem nítida chega em seguida (thread);
        o papel branco já aparece no mesmo instante, sem piscar."""
        self._renderer = renderer
        self._page = n
        self._pw, self._ph = renderer.page_size(n)
        m = PAGE_MARGIN_PT
        self._scene.setSceneRect(QRectF(-m, -m, self._pw + 2 * m, self._ph + 2 * m))
        self._paper.setRect(QRectF(0, 0, self._pw, self._ph))
        self._pix.setVisible(False)
        self._pix_scale = 0.0
        self._apply_scale()
        if focus_y is not None:
            self.centerOn(QPointF(self._pw / 2, focus_y))
        else:
            self.scroll_to_top()
        self._render_timer.start(25)

    def scroll_to_top(self):
        self._vanim.stop()
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        hbar = self.horizontalScrollBar()
        hbar.setValue((hbar.minimum() + hbar.maximum()) // 2)

    # ──────────────────────────────────────────────────────────────
    # Escala / zoom
    # ──────────────────────────────────────────────────────────────

    def _apply_scale(self):
        if self._page < 0:
            return
        vw = self.viewport().width()
        vh = self.viewport().height()
        if vw < 20 or vh < 20:
            return
        m = PAGE_MARGIN_PT
        sw, sh = self._pw + 2 * m, self._ph + 2 * m
        fit = vw / sw if self._fit_mode == "largura" else min(vw / sw, vh / sh)
        self._scale = max(0.05, fit * self._zoom)
        self.setTransform(QTransform.fromScale(self._scale, self._scale))
        self._update_cursor()

    def restore(self, zoom: float, fit_mode: str):
        """Aplica zoom/modo salvos nas preferências, sem sinais nem redesenho
        (usado uma vez, antes de qualquer página existir)."""
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        self._fit_mode = fit_mode if fit_mode in ("largura", "pagina") else "largura"

    def set_zoom(self, zoom: float):
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, round(zoom, 2)))
        if zoom == self._zoom:
            return
        self._zoom = zoom
        self._apply_scale()
        self._render_timer.start(120)
        self.zoom_changed.emit(zoom)

    def zoom_in(self):
        self.set_zoom(self._zoom + ZOOM_STEP)

    def zoom_out(self):
        self.set_zoom(self._zoom - ZOOM_STEP)

    def set_fit_mode(self, mode: str):
        self._fit_mode = mode if mode in ("largura", "pagina") else "largura"
        self.reset_view()

    def reset_view(self):
        """Zoom 100% do ajuste atual, no topo da página."""
        changed = self._zoom != 1.0
        self._zoom = 1.0
        self._apply_scale()
        self.scroll_to_top()
        self._render_timer.start(120)
        if changed:
            self.zoom_changed.emit(1.0)

    def _ensure_quality(self):
        """Pede uma imagem na resolução que a tela precisa agora, se a que
        está exibida ficou borrada (zoom subiu) ou desperdiçada (desceu)."""
        renderer = self._renderer
        if renderer is None or self._page < 0 or self._scale <= 0:
            return
        cap = math.sqrt(MAX_RENDER_PIXELS / max(1.0, self._pw * self._ph))
        needed = min(math.ceil(self._scale * self.devicePixelRatioF() * 20) / 20, cap)
        if self._pix.isVisible() and needed * 0.95 <= self._pix_scale <= needed * 1.6:
            return
        self._token += 1
        threading.Thread(
            target=self._render_worker,
            args=(self._token, renderer, self._page, needed),
            daemon=True,
        ).start()

    def _render_worker(self, token: int, renderer, n: int, scale: float):
        """Roda fora da thread da UI: renderiza a página e, de bônus, já
        deixa a próxima no cache — a virada de página fica instantânea."""
        try:
            w, h, data = renderer.render_raw(n, scale)
            img = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        except Exception as e:  # documento fechado no meio, p. ex.
            log.debug("Render da página %d falhou (ignorado): %s", n, e)
            return
        self._rendered.emit(token, n, scale, img)
        try:
            if n + 1 < renderer.total:
                renderer.render_raw(n + 1, scale)
        except Exception as e:
            log.debug("Prefetch da página %d falhou (ignorado): %s", n + 1, e)

    def _on_rendered(self, token: int, n: int, _scale: float, img: QImage):
        if token != self._token or n != self._page or img.isNull():
            return
        self._pix.setPixmap(QPixmap.fromImage(img))
        self._pix.setScale(self._pw / img.width())
        self._pix_scale = img.width() / self._pw
        self._pix.setVisible(True)

    # ──────────────────────────────────────────────────────────────
    # Grifos (camadas)
    # ──────────────────────────────────────────────────────────────

    def _set_layer(self, z: int, rects: list[dict]):
        """Atualiza uma camada reaproveitando os itens que já existem — a
        troca de palavra durante a leitura não aloca nem destrói nada."""
        items = self._layers[z]
        while len(items) > len(rects):
            self._scene.removeItem(items.pop())
        while len(items) < len(rects):
            it = _HighlightItem()
            it.setPen(QPen(Qt.PenStyle.NoPen))
            it.setZValue(z)
            self._scene.addItem(it)
            items.append(it)
        for it, h in zip(items, rects, strict=True):
            it.setRect(QRectF(h["x0"], h["y0"], h["x1"] - h["x0"], h["y1"] - h["y0"]))
            color = QColor(h.get("color", C["info"]))
            color.setAlphaF(float(h.get("opacity", 0.35)))
            it.setBrush(QBrush(color))

    def set_saved_highlights(self, rects: list[dict]):
        self._set_layer(_Z_SAVED, rects)

    def set_search_highlights(self, rects: list[dict]):
        self._set_layer(_Z_SEARCH, rects)

    def set_chunk_highlights(self, rects: list[dict]):
        self._set_layer(_Z_CHUNK, rects)

    def set_word_highlights(self, rects: list[dict]):
        self._set_layer(_Z_WORD, rects)

    # ──────────────────────────────────────────────────────────────
    # Acompanhar a leitura
    # ──────────────────────────────────────────────────────────────

    def _animate(self, anim: QPropertyAnimation, bar, target: float):
        target = max(bar.minimum(), min(bar.maximum(), int(target)))
        if target == bar.value():
            return
        anim.stop()
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.start()

    def follow(self, h: dict):
        """Mantém o trecho lido à vista, rolando de forma suave.

        Só rola quando o grifo sai da faixa confortável da tela — e então o
        leva a ~40% da altura. A versão antiga recentralizava a cada
        palavra, e o texto ficava balançando sem parar."""
        p = self.mapFromScene(QPointF((h["x0"] + h["x1"]) / 2, (h["y0"] + h["y1"]) / 2))
        vh = self.viewport().height()
        vw = self.viewport().width()
        vbar = self.verticalScrollBar()
        if vbar.maximum() > 0 and not (vh * 0.18 <= p.y() <= vh * 0.68):
            self._animate(self._vanim, vbar, vbar.value() + p.y() - int(vh * 0.38))
        hbar = self.horizontalScrollBar()
        if hbar.maximum() > 0 and not (vw * 0.1 <= p.x() <= vw * 0.9):
            self._animate(self._hanim, hbar, hbar.value() + p.x() - vw // 2)

    def focus_rect(self, h: dict):
        """Centraliza um retângulo (resultado de busca) sem animação."""
        self._vanim.stop()
        self.centerOn(QPointF((h["x0"] + h["x1"]) / 2, (h["y0"] + h["y1"]) / 2))

    # ──────────────────────────────────────────────────────────────
    # Seleção de grifo manual
    # ──────────────────────────────────────────────────────────────

    def set_hl_mode(self, on: bool):
        self._hl_mode = on
        self._cancel_selection()
        self._update_cursor()

    def set_selection_color(self, color: str):
        self._sel_color = color

    def _cancel_selection(self):
        if self._sel_item is not None:
            self._scene.removeItem(self._sel_item)
            self._sel_item = None

    def _update_cursor(self):
        if self._hl_mode:
            cur = Qt.CursorShape.CrossCursor
        elif self.verticalScrollBar().maximum() > 0 or self.horizontalScrollBar().maximum() > 0:
            cur = Qt.CursorShape.OpenHandCursor
        else:
            cur = Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(cur)

    def overflows(self) -> bool:
        """True quando há o que rolar na vertical."""
        return self.verticalScrollBar().maximum() > 0

    # ──────────────────────────────────────────────────────────────
    # Eventos
    # ──────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scale()
        self._render_timer.start(150)

    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            self._zoom_accum += dy
            steps = int(self._zoom_accum / 120)
            if steps:
                self._zoom_accum -= steps * 120
                self.set_zoom(self._zoom + ZOOM_STEP * steps)
            event.accept()
            return
        if mods & Qt.KeyboardModifier.ShiftModifier:
            hbar = self.horizontalScrollBar()
            hbar.setValue(hbar.value() - dy)
            event.accept()
            return
        if self.overflows():
            super().wheelEvent(event)   # rolagem nativa (inclui touchpad de precisão)
            return
        # Nada para rolar: a roda vira de página. O delta é acumulado porque
        # touchpads mandam muitos eventos pequenos, e cada virada reinicia a
        # leitura — um movimento de dedo não pode virar dez páginas.
        self._zoom_accum += dy
        steps = int(self._zoom_accum / 120)
        if steps:
            self._zoom_accum -= steps * 120
            self.page_step.emit(-1 if steps > 0 else 1)
        event.accept()

    def _pdf_point(self, pos: QPoint) -> QPointF:
        return self.mapToScene(pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
            self._pan_last = self._press
            self._moved = False
            if self._hl_mode and self._page >= 0:
                self._sel_origin = self._pdf_point(self._press)
                self._cancel_selection()
                pen = QPen(QColor(self._sel_color), 2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self._sel_item = QGraphicsRectItem(QRectF(self._sel_origin, self._sel_origin))
                self._sel_item.setPen(pen)
                self._sel_item.setZValue(_Z_SELECTION)
                self._scene.addItem(self._sel_item)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton and self._page >= 0:
            p = self._pdf_point(event.position().toPoint())
            self.right_clicked.emit(p.x(), p.y())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is None:
            super().mouseMoveEvent(event)
            return
        pos = event.position().toPoint()
        if (pos - self._press).manhattanLength() > 5:
            self._moved = True
        if self._hl_mode:
            if self._sel_item is not None:
                cur = self._pdf_point(pos)
                self._sel_item.setRect(QRectF(self._sel_origin, cur).normalized())
        elif self._moved and self._pan_last is not None:
            d = pos - self._pan_last
            self._pan_last = pos
            self._vanim.stop()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            super().mouseReleaseEvent(event)
            return
        pos = event.position().toPoint()
        if self._hl_mode:
            if self._sel_item is not None:
                r = QRectF(self._sel_origin, self._pdf_point(pos)).normalized()
                self._cancel_selection()
                # Seleção minúscula = clique acidental → ignora.
                if r.width() >= 5 and r.height() >= 3:
                    self.selected.emit(r.left(), r.top(), r.right(), r.bottom())
        elif not self._moved and self._page >= 0:
            p = self._pdf_point(pos)
            self.clicked.emit(p.x(), p.y(), event.globalPosition().toPoint())
        self._press = None
        self._pan_last = None
        self._update_cursor()
        event.accept()
