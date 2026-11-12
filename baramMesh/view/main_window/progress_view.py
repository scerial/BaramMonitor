#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math

import pyqtgraph as pg
from PySide6.QtCore import QCoreApplication, QEvent, QMargins, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PySide6QtAds import CDockWidget

from baramMesh.openfoam.log_parser import SnappyLogParser


PHASE_COLORS = {
    'Feature': '#CC79A7',
    'Surface': '#56B4E9',
    'Shell': '#E69F00',
    'Cleanup': '#999999'
}
ACCENT = '#0072B2'
CHIP_COLORS = {
    'idle': '#6b7280',
    'running': '#0072B2',
    'done': '#009E73',
    'warn': '#D55E00'
}
STALL_WINDOW = 10
STALL_TOLERANCE = 0.5
STALL_CEILING = 90


def _formatDuration(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


def _si(value):
    a = abs(value)
    for limit, suffix in ((1e9, 'G'), (1e6, 'M'), (1e3, 'k')):
        if a >= limit:
            return f'{value / limit:.3g}{suffix}'

    if a != 0 and a < 1e-3:
        return f'{value:.0e}'.replace('e-0', 'e-')

    return f'{value:.3g}'


def _mix(first: QColor, second: QColor, ratio: float):
    return QColor.fromRgbF(
        first.redF() * ratio + second.redF() * (1 - ratio),
        first.greenF() * ratio + second.greenF() * (1 - ratio),
        first.blueF() * ratio + second.blueF() * (1 - ratio))


def _sci(value):
    return f'{value:.1e}'.replace('e-0', 'e-')


def _phaseGroup(label):
    return label if label in PHASE_COLORS else 'Cleanup'


class _Axis(pg.AxisItem):
    def __init__(self, orientation, **kwargs):
        super().__init__(orientation, **kwargs)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        if self.logMode:
            values = [10 ** v for v in values]

        return [_si(v * scale) for v in values]


class _StatTile(QWidget):
    def __init__(self, valueFont, captionColor):
        super().__init__()
        self._value = QLabel('-')
        self._value.setFont(valueFont)
        self._caption = QLabel('')
        self._caption.setStyleSheet(f'color: {captionColor};')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(QMargins(10, 4, 10, 4))
        layout.setSpacing(0)
        layout.addWidget(self._value)
        layout.addWidget(self._caption)

    def set(self, caption, value):
        self._caption.setText(caption)
        self._value.setText(value)


class ProgressWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._parser = SnappyLogParser()
        self._dirty = False
        self._mode = None
        self._topLog = False
        self._dividers = []

        palette = self.palette()
        self._bg = palette.color(QPalette.ColorRole.Base)
        self._text = palette.color(QPalette.ColorRole.Text)
        self._muted = _mix(self._text, self._bg, 0.55)
        self._panel = _mix(self._text, self._bg, 0.07)

        valueFont = QFont(self.font())
        valueFont.setPointSizeF(self.font().pointSizeF() * 1.5)
        valueFont.setBold(True)

        self._tilesFrame = QFrame()
        self._tilesFrame.setStyleSheet(
            f'QFrame {{ background: {self._panel.name()}; border-radius: 6px; }}')
        tilesLayout = QHBoxLayout(self._tilesFrame)
        tilesLayout.setContentsMargins(QMargins(4, 2, 4, 2))
        self._tiles = [_StatTile(valueFont, self._muted.name()) for _ in range(5)]
        for tile in self._tiles:
            tilesLayout.addWidget(tile)
        tilesLayout.addStretch(1)

        self._chip = QLabel('')
        self._resetButton = QPushButton('Reset')
        self._resetButton.setFixedWidth(70)
        self._resetButton.clicked.connect(self.reset)

        self._legend = QLabel('')
        self._legend.setTextFormat(Qt.TextFormat.RichText)

        self._topPlot = self._makePlot()
        self._bottomPlot = self._makePlot()
        self._bottomPlot.setLogMode(y=True)
        self._bottomPlot.setXLink(self._topPlot)

        self._topCurve, self._topLatest, self._topLabel = self._makeCurves(self._topPlot)
        self._bottomCurve, self._bottomLatest, self._bottomLabel = self._makeCurves(self._bottomPlot)

        self._targetLine = pg.InfiniteLine(
            pos=100, angle=0, pen=pg.mkPen(self._muted, style=Qt.PenStyle.DashLine, width=1))
        self._topPlot.addItem(self._targetLine)
        self._targetLine.hide()

        header = QHBoxLayout()
        header.addWidget(self._tilesFrame, 1)
        header.addWidget(self._chip, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._resetButton, 0, Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(QMargins(4, 4, 4, 4))
        layout.addLayout(header)
        layout.addWidget(self._legend)
        layout.addWidget(self._topPlot, 1)
        layout.addWidget(self._bottomPlot, 1)

        self._applyMode('refinement')
        self._updateTiles(self._parser.state, 'refinement')
        self._updateChip(self._parser.state, 'refinement')

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def _makePlot(self):
        plot = pg.PlotWidget(background=self._bg, axisItems={'left': _Axis('left'), 'bottom': _Axis('bottom')})
        plot.setAntialiasing(True)
        plot.setMinimumHeight(110)
        plot.showGrid(x=True, y=True, alpha=0.18)
        for name in ('left', 'bottom'):
            axis = plot.getAxis(name)
            axis.setPen(pg.mkPen(self._muted))
            axis.setTextPen(pg.mkPen(self._text))

        return plot

    def _makeCurves(self, plot):
        curve = plot.plot(pen=pg.mkPen(self._muted, width=1.5), symbol='o', symbolSize=7,
                          symbolBrush=pg.mkBrush(ACCENT), symbolPen=pg.mkPen(self._bg, width=1))
        latest = plot.plot(pen=None, symbol='o', symbolSize=15, symbolBrush=(0, 0, 0, 0),
                           symbolPen=pg.mkPen(self._text, width=2))
        label = pg.TextItem(color=self._text, anchor=(1, 1.3))
        plot.addItem(label)
        label.hide()

        return curve, latest, label

    @Slot(str)
    def feed(self, line: str):
        if self._parser.feed(line):
            self._dirty = True

    @Slot()
    def reset(self):
        self._parser.reset()
        self._dirty = True
        self._refresh()

    def _modeFor(self, state):
        if state.phase == 'layer addition' and state.layerSamples:
            return 'layers'

        if state.phase == 'snapping':
            return 'snap'

        return 'refinement'

    def _applyMode(self, mode):
        if mode == self._mode:
            return

        self._mode = mode
        self._topLog = mode == 'snap'
        self._topPlot.setLogMode(y=self._topLog)
        self._topPlot.enableAutoRange()
        self._bottomPlot.enableAutoRange()

        if mode == 'layers':
            self._topPlot.setLabel('left', 'Extruded faces (%)')
            self._bottomPlot.setLabel('left', 'Illegal faces')
            self._bottomPlot.setLabel('bottom', 'Layer iteration')
            self._targetLine.show()
            self._topPlot.setYRange(0, 105, padding=0)
        elif mode == 'snap':
            self._topPlot.setLabel('left', 'Mean displacement (m)')
            self._bottomPlot.setLabel('left', 'Max displacement (m)')
            self._bottomPlot.setLabel('bottom', 'Morph iteration')
            self._targetLine.hide()
        else:
            self._topPlot.setLabel('left', 'Total cells')
            self._bottomPlot.setLabel('left', 'Selected for refinement')
            self._bottomPlot.setLabel('bottom', 'Refinement step')
            self._targetLine.hide()

    def _series(self, state, mode):
        if mode == 'layers':
            samples = state.layerSamples
            return ([s.iteration for s in samples], [s.extrudedPercent for s in samples],
                    [max(s.illegalFaces or 0, 1) for s in samples], None)

        if mode == 'snap':
            samples = state.snapSamples
            return ([s.iteration for s in samples], [s.average for s in samples],
                    [s.maximum for s in samples], None)

        samples = state.samples
        brushes = [pg.mkBrush(PHASE_COLORS[_phaseGroup(s.label)]) for s in samples]
        return ([s.index for s in samples], [s.total for s in samples],
                [max(s.selected, 1) for s in samples], brushes)

    def _plotSeries(self, xs, tops, bottoms, brushes, mode):
        kwargs = {'symbolBrush': brushes if brushes else pg.mkBrush(ACCENT),
                  'symbolPen': pg.mkPen(self._bg, width=1)}
        self._topCurve.setData(xs, tops, **kwargs)
        self._bottomCurve.setData(xs, bottoms, **kwargs)

        if not xs:
            for latest, label in ((self._topLatest, self._topLabel), (self._bottomLatest, self._bottomLabel)):
                latest.setData([], [])
                label.hide()

            return

        if mode == 'layers':
            topText, bottomText = f'{tops[-1]:.1f}%', _si(bottoms[-1])
        elif mode == 'snap':
            topText, bottomText = _sci(tops[-1]), _sci(bottoms[-1])
        else:
            topText, bottomText = _si(tops[-1]), _si(bottoms[-1])

        for latest, label, y, text, isLog in (
                (self._topLatest, self._topLabel, tops[-1], topText, self._topLog),
                (self._bottomLatest, self._bottomLabel, bottoms[-1], bottomText, True)):
            latest.setData([xs[-1]], [y])
            label.setText(text)
            label.setPos(xs[-1], math.log10(y) if isLog and y > 0 else y)
            label.show()

    def _updateDividers(self, state, mode):
        for plot, line in self._dividers:
            plot.removeItem(line)

        self._dividers = []
        if mode != 'refinement':
            return

        previous = None
        for sample in state.samples:
            group = _phaseGroup(sample.label)
            if previous is not None and group != previous:
                for plot in (self._topPlot, self._bottomPlot):
                    line = pg.InfiniteLine(pos=sample.index - 0.5, angle=90,
                                           pen=pg.mkPen(self._muted, style=Qt.PenStyle.DashLine, width=1))
                    plot.addItem(line)
                    self._dividers.append((plot, line))

            previous = group

    def _updateLegend(self, state, mode):
        if mode != 'refinement' or not state.samples:
            self._legend.hide()
            return

        groups = []
        for sample in state.samples:
            group = _phaseGroup(sample.label)
            if group not in groups:
                groups.append(group)

        self._legend.setText('&nbsp;&nbsp;'.join(
            f'<span style="color:{PHASE_COLORS[g]}">&#9679;</span> {g}' for g in groups))
        self._legend.show()

    def _tileItems(self, state, mode):
        if mode == 'layers':
            last = state.layerSamples[-1]
            return [('Phase', 'Layers'), ('Iteration', str(last.iteration)),
                    ('Extruded', f'{last.extrudedPercent:.1f}%'),
                    ('Illegal faces', f'{last.illegalFaces:,}' if last.illegalFaces is not None else '-'),
                    ('Elapsed', _formatDuration(last.wallTime))]

        if mode == 'snap':
            items = [('Phase', 'Snapping')]
            if state.morphIteration is not None:
                done = state.morphIteration + 1
                items.append(('Iteration', f'{done} / {state.morphTotal}' if state.morphTotal else str(done)))

            if state.snapSamples:
                items.append(('Mean disp. (m)', _sci(state.snapSamples[-1].average)))
                items.append(('Max disp. (m)', _sci(state.snapSamples[-1].maximum)))

            return items

        if not state.samples:
            return [('Phase', state.phase.capitalize())] if state.phase else []

        last = state.samples[-1]
        return [('Phase', _phaseGroup(last.label)), ('Iteration', str(last.iteration)),
                ('Cells', _si(last.total)), ('Selected', f'{last.selected:,}'),
                ('Elapsed', _formatDuration(last.wallTime))]

    def _updateTiles(self, state, mode):
        items = self._tileItems(state, mode)
        for index, tile in enumerate(self._tiles):
            if index < len(items):
                tile.set(*items[index])
                tile.show()
            else:
                tile.hide()

        self._tilesFrame.setVisible(bool(items))

    def _health(self, state, mode):
        if state.finished:
            if state.finishedIllegal == 0:
                return 'done', 'Finished, no errors'

            return 'warn', f'Finished with {state.finishedIllegal:,} illegal faces'

        if mode == 'layers':
            samples = state.layerSamples
            last = samples[-1]
            if last.illegalFaces == 0 and last.extrudedPercent >= 99:
                return 'done', 'Layers complete'

            if (len(samples) >= STALL_WINDOW and last.extrudedPercent < STALL_CEILING
                    and abs(last.extrudedPercent - samples[-STALL_WINDOW].extrudedPercent) < STALL_TOLERANCE):
                return 'warn', f'Stalled at {last.extrudedPercent:.0f}% extruded'

            return 'running', 'Adding layers'

        if mode == 'snap':
            return 'running', 'Snapping'

        if state.samples:
            last = state.samples[-1]
            if last.selected == 0:
                return 'done', f'{_phaseGroup(last.label)} converged'

            return 'running', f'Refining ({_phaseGroup(last.label).lower()})'

        if state.phase:
            return 'running', state.phase.capitalize()

        return 'idle', 'Waiting for output'

    def _updateChip(self, state, mode):
        key, text = self._health(state, mode)
        self._chip.setText(text)
        self._chip.setStyleSheet(
            f'background: {CHIP_COLORS[key]}; color: white; border-radius: 10px;'
            f' padding: 4px 12px; font-weight: 600;')

    def _refresh(self):
        if not self._dirty:
            return

        self._dirty = False
        state = self._parser.state
        mode = self._modeFor(state)

        self._applyMode(mode)
        xs, tops, bottoms, brushes = self._series(state, mode)
        self._plotSeries(xs, tops, bottoms, brushes, mode)
        self._updateDividers(state, mode)
        self._updateLegend(state, mode)
        self._updateTiles(state, mode)
        self._updateChip(state, mode)


class ProgressView(CDockWidget):
    def __init__(self):
        super().__init__(self._title())

        self.setWidget(ProgressWidget(), CDockWidget.eInsertMode.ForceNoScrollArea)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.LanguageChange:
            self.setWindowTitle(self._title())

        super().changeEvent(event)

    def _title(self):
        return QCoreApplication.translate('ProgressView', 'Progress')
