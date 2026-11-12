#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from baramMesh.monitor.metrics_server import MetricsServer, pairingHosts, pairingLink, resolveBindHost
from baramMesh.monitor.resource_sampler import ResourceConfig, ResourceSampler


logger = logging.getLogger(__name__)

RETRY_MILLISECONDS = 15000
QR_SCALE = 6
QR_BORDER = 3

BIND_MODES = (
    ('tailscale', 'Tailscale only (recommended)'),
    ('all', 'Tailscale and local network'),
    ('local', 'This PC only (testing)')
)


class MobileBridge(QObject):
    statusChanged = Signal(str)

    def __init__(self, sampler: ResourceSampler, progressProvider: Callable[[], Optional[dict]], parent=None):
        super().__init__(parent)
        self._server = MetricsServer(sampler, progressProvider)
        self._config = None
        self._status = 'Off'
        self._active = None

        self._retry = QTimer(self)
        self._retry.setInterval(RETRY_MILLISECONDS)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self._attempt)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def statusText(self) -> str:
        return self._status

    def apply(self, config: ResourceConfig):
        self._config = config
        self._retry.stop()

        wanted = (config.mobileBind, config.mobilePort, config.mobileToken) if config.mobileEnabled else None
        if wanted == self._active and (wanted is None or self._server.running):
            return

        self._server.stop()
        self._active = None
        if wanted is None:
            self._setStatus('Off')
            return

        self._attempt()

    def shutdown(self):
        self._retry.stop()
        self._server.stop()

    def _attempt(self):
        config = self._config
        if config is None or not config.mobileEnabled:
            return

        try:
            host = resolveBindHost(config.mobileBind)
            self._server.start(host, config.mobilePort, config.mobileToken)
        except (OSError, ValueError) as e:
            logger.debug('Phone monitor could not start: %s', e)
            self._setStatus(f'Not running: {str(e).rstrip(".")}. Retrying every {RETRY_MILLISECONDS // 1000} s.')
            self._retry.start()
            return

        self._active = (config.mobileBind, config.mobilePort, config.mobileToken)
        address, port = self._server.address[:2]
        self._setStatus(f'Listening on {address}:{port}')

    def _setStatus(self, text: str):
        self._status = text
        self.statusChanged.emit(text)


def qrPixmap(text: str) -> Optional[QPixmap]:
    try:
        import segno
    except ImportError:
        return None

    matrix = [list(row) for row in segno.make(text, error='m').matrix]
    size = (len(matrix) + 2 * QR_BORDER) * QR_SCALE
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))

    painter = QPainter(image)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('black'))
    for y, row in enumerate(matrix):
        for x, filled in enumerate(row):
            if filled:
                painter.drawRect((x + QR_BORDER) * QR_SCALE, (y + QR_BORDER) * QR_SCALE, QR_SCALE, QR_SCALE)

    painter.end()
    return QPixmap.fromImage(image)


class PairingDialog(QDialog):
    def __init__(self, mode: str, port: int, token: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Pair a phone or tablet')
        self._port = port
        self._token = token

        intro = QLabel('Install the BaramMonitor app, then scan this code with the iPhone or iPad Camera. '
                       'Both devices must be signed in to the same Tailscale network.')
        intro.setWordWrap(True)

        self._hosts = QComboBox()
        self._hosts.addItems(pairingHosts(mode))
        self._hosts.currentTextChanged.connect(self._refresh)

        self._qr = QLabel()
        self._qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._link = QLabel()
        self._link.setWordWrap(True)
        self._link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        copy = QPushButton('Copy link')
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._currentLink()))

        row = QHBoxLayout()
        row.addWidget(QLabel('PC address'))
        row.addWidget(self._hosts, 1)
        row.addWidget(copy)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(row)
        layout.addWidget(self._qr)
        layout.addWidget(self._link)
        layout.addWidget(buttons)

        self._refresh()

    def _currentLink(self) -> str:
        return pairingLink(self._hosts.currentText(), self._port, self._token)

    def _refresh(self, *_):
        link = self._currentLink()
        pixmap = qrPixmap(link)
        if pixmap is None:
            self._qr.setText('Install the "segno" package to show a QR code, or copy the link below.')
        else:
            self._qr.setPixmap(pixmap)

        self._link.setText(link)
