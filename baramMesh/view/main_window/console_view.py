#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging

from PySide6.QtCore import QCoreApplication, QEvent, QMargins, Signal
from PySide6.QtGui import QFontDatabase

from PySide6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout
from PySide6QtAds import CDockWidget

from baramMesh.app import app


logger = logging.getLogger(__name__)

LOG_FILE_NAME = 'baramMesh.log'


class Console(QWidget):
    lineAppended = Signal(str)

    def __init__(self):
        super().__init__()
        self._logPath = None
        self._logFile = None
        self._view = QPlainTextEdit(self)

        charFormat = self._view.currentCharFormat()
        fixedFont = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        charFormat.setFont(fixedFont)
        self._view.setCurrentCharFormat(charFormat)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(QMargins(0, 0, 0, 0))
        layout.addWidget(self._view)

    def clear(self):
        self._view.clear()

    def append(self, text):
        self._view.appendPlainText(text)
        self._writeLog(text)
        self.lineAppended.emit(text)

    def appendError(self, text):
        self._view.appendPlainText(text)
        self._writeLog(text)

    def _writeLog(self, text):
        try:
            path = app.fileSystem.caseRoot() / LOG_FILE_NAME
            if path != self._logPath:
                self.closeLog()
                self._logFile = open(path, 'a', buffering=1, encoding='utf-8', errors='replace')
                self._logPath = path

            self._logFile.write(text + '\n')
        except Exception as e:
            logger.debug(f'Console log write failed: {e}')

    def closeLog(self):
        if self._logFile is not None:
            try:
                self._logFile.close()
            except OSError:
                pass

        self._logFile = None
        self._logPath = None


class ConsoleView(CDockWidget):
    def __init__(self):
        super().__init__(self._title())

        self.setWidget(Console())

    def changeEvent(self, event):
        if event.type() == QEvent.Type.LanguageChange:
            self.setWindowTitle(self._title())

        super().changeEvent(event)

    def clear(self):
        self.widget().clear()
        self.widget().closeLog()

    def _title(self):
        return QCoreApplication.translate('ConsoleView', 'Console')
