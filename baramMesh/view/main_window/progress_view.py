#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pyqtgraph as pg
from PySide6.QtCore import QCoreApplication, QEvent, QMargins, QTimer, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PySide6QtAds import CDockWidget

from baramMesh.openfoam.log_parser import SnappyLogParser


def _formatDuration(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


class ProgressWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._parser = SnappyLogParser()
        self._dirty = False

        self._status = QLabel('Waiting for snappyHexMesh output')
        self._status.setWordWrap(True)
        self._resetButton = QPushButton('Reset')
        self._resetButton.setFixedWidth(70)
        self._resetButton.clicked.connect(self.reset)

        self._cellsPlot = pg.PlotWidget()
        self._cellsPlot.setLabel('left', 'Total cells')
        self._cellsPlot.showGrid(x=True, y=True, alpha=0.3)
        self._cellsCurve = self._cellsPlot.plot(pen=pg.mkPen(width=2), symbol='o', symbolSize=5)

        self._selectedPlot = pg.PlotWidget()
        self._selectedPlot.setLabel('left', 'Selected for refinement')
        self._selectedPlot.setLabel('bottom', 'Refinement step')
        self._selectedPlot.setLogMode(y=True)
        self._selectedPlot.showGrid(x=True, y=True, alpha=0.3)
        self._selectedPlot.setXLink(self._cellsPlot)
        self._selectedCurve = self._selectedPlot.plot(pen=pg.mkPen(width=2), symbol='o', symbolSize=5)

        header = QHBoxLayout()
        header.addWidget(self._status, 1)
        header.addWidget(self._resetButton)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(QMargins(4, 4, 4, 4))
        layout.addLayout(header)
        layout.addWidget(self._cellsPlot, 1)
        layout.addWidget(self._selectedPlot, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    @Slot(str)
    def feed(self, line: str):
        if self._parser.feed(line):
            self._dirty = True

    @Slot()
    def reset(self):
        self._parser.reset()
        self._dirty = True
        self._refresh()

    def _refresh(self):
        if not self._dirty:
            return

        self._dirty = False
        state = self._parser.state
        samples = state.samples

        xs = [s.index for s in samples]
        self._cellsCurve.setData(xs, [s.total for s in samples])
        self._selectedCurve.setData(xs, [max(s.selected, 1) for s in samples])

        parts = []
        if state.phase:
            parts.append(state.phase)
        if state.iteration is not None and 'refinement' in state.phase:
            parts.append(f'iteration {state.iteration}')
        if state.morphIteration is not None and state.phase == 'snapping':
            parts.append(f'iteration {state.morphIteration}')
        if state.layerIteration is not None and state.phase == 'layer addition':
            parts.append(f'iteration {state.layerIteration}')
            if state.extrusionPercent is not None:
                parts.append(f'extruded {state.extrusionPercent:.1f}%')
        if state.totalCells is not None:
            parts.append(f'{state.totalCells:,} cells')
        if state.selected is not None:
            parts.append(f'{state.selected:,} selected')
        if samples and samples[-1].duration is not None:
            parts.append(f'last step {_formatDuration(samples[-1].duration)}')
        if samples:
            parts.append(f'elapsed {_formatDuration(samples[-1].wallTime)}')

        self._status.setText('  |  '.join(parts) if parts else 'Waiting for snappyHexMesh output')


class ProgressView(CDockWidget):
    def __init__(self):
        super().__init__(self._title())

        self.setWidget(ProgressWidget())

    def changeEvent(self, event):
        if event.type() == QEvent.Type.LanguageChange:
            self.setWindowTitle(self._title())

        super().changeEvent(event)

    def _title(self):
        return QCoreApplication.translate('ProgressView', 'Progress')
