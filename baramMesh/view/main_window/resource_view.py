#!/usr/bin/env python
# -*- coding: utf-8 -*-

from dataclasses import fields
from urllib.parse import urlparse

import pyqtgraph as pg
from PySide6.QtCore import QCoreApplication, QEvent, QMargins, QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)
from PySide6QtAds import CDockWidget

from libbaram.app_path import APP_PATH
from baramMesh.monitor.resource_sampler import ResourceConfig, ResourceSampler


NORMAL = '#0072B2'
MESHING = '#E69F00'
WARN = '#F2C200'
CRITICAL = '#E03131'
PSU_WARN_RATIO = 0.8
MEMORY_WARN_RATIO = 0.85
MEMORY_CRITICAL_RATIO = 0.95
HISTORY_SECONDS = 300
SETTINGS_ORGANIZATION = 'BaramMonitor'
SETTINGS_APPLICATION = 'ResourceMonitor'
GIB = 1024 ** 3
LHM_HINT = 'Run LibreHardwareMonitor as administrator and enable Options → Remote Web Server → Run.'


def _mix(first: QColor, second: QColor, ratio: float):
    return QColor.fromRgbF(
        first.redF() * ratio + second.redF() * (1 - ratio),
        first.greenF() * ratio + second.greenF() * (1 - ratio),
        first.blueF() * ratio + second.blueF() * (1 - ratio))


def loadConfig() -> ResourceConfig:
    settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
    config = ResourceConfig(solverBinPath=str(APP_PATH.joinpath('solvers', 'openfoam', 'bin')))
    for f in fields(ResourceConfig):
        if f.name == 'solverBinPath':
            continue

        value = settings.value(f.name)
        if value is None:
            continue

        try:
            setattr(config, f.name, type(getattr(config, f.name))(value))
        except (TypeError, ValueError):
            pass

    return config


def saveConfig(config: ResourceConfig):
    settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
    for f in fields(ResourceConfig):
        if f.name != 'solverBinPath':
            settings.setValue(f.name, getattr(config, f.name))


class _MeterBar(QWidget):
    def __init__(self, trackColor: QColor):
        super().__init__()
        self._track = trackColor
        self._maximum = 1.0
        self._segments = []
        self._markers = []
        self.setFixedHeight(14)

    def setData(self, maximum, segments, markers=()):
        self._maximum = max(float(maximum), 1e-9)
        self._segments = list(segments)
        self._markers = list(markers)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.fillPath(path, self._track)

        painter.setClipPath(path)
        x = rect.left()
        for value, color in self._segments:
            width = rect.width() * max(value, 0) / self._maximum
            painter.fillRect(QRectF(x, rect.top(), width, rect.height()), QColor(color))
            x += width

        painter.setClipping(False)
        for value, color in self._markers:
            mx = rect.left() + rect.width() * min(max(value / self._maximum, 0), 1)
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(QPointF(mx, 0), QPointF(mx, self.height()))


class _Sparkline(pg.PlotWidget):
    def __init__(self, background: QColor):
        super().__init__(background=background)
        self.setFixedHeight(42)
        self.hideAxis('left')
        self.hideAxis('bottom')
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self.hideButtons()
        self.setAntialiasing(True)
        self.getPlotItem().setContentsMargins(0, 0, 0, 0)
        self.setXRange(-HISTORY_SECONDS, 0, padding=0)
        self._lines = []

    def addCurve(self, color, fill=False):
        if fill:
            brush = QColor(color)
            brush.setAlpha(60)
            return self.plot(pen=pg.mkPen(color, width=1.5), fillLevel=0, brush=brush)

        return self.plot(pen=pg.mkPen(color, width=1.5))

    def setLines(self, lines):
        for line in self._lines:
            self.removeItem(line)

        self._lines = []
        for value, color in lines:
            line = pg.InfiniteLine(pos=value, angle=0, pen=pg.mkPen(color, style=Qt.PenStyle.DashLine, width=1))
            self.addItem(line)
            self._lines.append(line)


class _MetricCard(QFrame):
    def __init__(self, title, colors):
        super().__init__()
        self._colors = colors
        self.setObjectName('metricCard')
        self.setStyleSheet(f'QFrame#metricCard {{ background: {colors["panel"].name()}; border-radius: 6px; }}')

        titleLabel = QLabel(title)
        titleFont = QFont(self.font())
        titleFont.setBold(True)
        titleLabel.setFont(titleFont)

        self._value = QLabel('–')
        valueFont = QFont(self.font())
        valueFont.setPointSizeF(self.font().pointSizeF() * 1.35)
        valueFont.setBold(True)
        self._value.setFont(valueFont)

        self._chip = QLabel('')
        self._chip.hide()

        self.bar = _MeterBar(colors['track'])
        self._detail = QLabel('')
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet(f'color: {colors["muted"].name()};')
        self.spark = _Sparkline(colors['panel'])

        header = QHBoxLayout()
        header.addWidget(titleLabel)
        header.addStretch(1)
        header.addWidget(self._chip, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._value)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(QMargins(10, 6, 10, 6))
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(self.bar)
        layout.addWidget(self._detail)
        layout.addWidget(self.spark)

    def setValue(self, text):
        self._value.setText(text)

    def setDetail(self, text):
        self._detail.setText(text)

    def setChip(self, text=None, color=None):
        if not text:
            self._chip.hide()
            return

        foreground = '#1a1a1a' if color == WARN else 'white'
        self._chip.setText(text)
        self._chip.setStyleSheet(
            f'background: {color}; color: {foreground}; border-radius: 8px; padding: 2px 8px; font-weight: 600;')
        self._chip.show()


class ResourceSettingsDialog(QDialog):
    def __init__(self, config: ResourceConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Resource monitor settings')
        self._solverBinPath = config.solverBinPath

        self._tdp = self._spin(1, 1000, ' W')
        self._ppt = self._spin(1, 1500, ' W')
        self._warn = self._spin(30, 120, ' °C')
        self._critical = self._spin(30, 120, ' °C')
        self._psu = self._spin(0, 3000, ' W')
        self._psu.setSpecialValueText('Not set')
        self._baseline = self._spin(0, 500, ' W')
        self._url = QLineEdit()
        self._warn.valueChanged.connect(self._critical.setMinimum)

        form = QFormLayout()
        form.addRow('CPU TDP', self._tdp)
        form.addRow('CPU power limit (PPT)', self._ppt)
        form.addRow('Temperature: yellow from', self._warn)
        form.addRow('Temperature: red at', self._critical)
        form.addRow('PSU capacity', self._psu)
        form.addRow('Rest of system (estimate)', self._baseline)
        form.addRow('LibreHardwareMonitor URL', self._url)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self._load(ResourceConfig(solverBinPath=self._solverBinPath)))

        note = QLabel('Defaults are for an AMD Ryzen 7 7800X3D (120 W TDP, 162 W PPT, 89 °C limit).')
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

        self._load(config)

    def _spin(self, minimum, maximum, suffix):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(0)
        spin.setSuffix(suffix)
        return spin

    def _load(self, config):
        self._tdp.setValue(config.tdpWatts)
        self._ppt.setValue(config.pptWatts)
        self._warn.setValue(config.tempWarn)
        self._critical.setValue(config.tempCritical)
        self._psu.setValue(config.psuWatts)
        self._baseline.setValue(config.baselineWatts)
        self._url.setText(config.lhmUrl)

    def config(self) -> ResourceConfig:
        return ResourceConfig(
            tdpWatts=self._tdp.value(), pptWatts=self._ppt.value(), tempWarn=self._warn.value(),
            tempCritical=max(self._critical.value(), self._warn.value()), psuWatts=self._psu.value(),
            baselineWatts=self._baseline.value(), lhmUrl=self._url.text().strip(),
            solverBinPath=self._solverBinPath)


class ResourceWidget(QWidget):
    def __init__(self, sampler: ResourceSampler = None):
        super().__init__()
        palette = self.palette()
        background = palette.color(QPalette.ColorRole.Base)
        text = palette.color(QPalette.ColorRole.Text)
        self._colors = {
            'panel': _mix(text, background, 0.06),
            'track': _mix(text, background, 0.14),
            'muted': _mix(text, background, 0.55),
            'other': _mix(text, background, 0.40)
        }

        self._sampler = sampler or ResourceSampler(loadConfig(), historySeconds=HISTORY_SECONDS)
        self._sampler.start()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._sampler.stop)

        self._source = QLabel('')
        self._source.setStyleSheet(f'color: {self._colors["muted"].name()};')
        self._source.setWordWrap(True)
        settingsButton = QPushButton('Settings…')
        settingsButton.clicked.connect(self._openSettings)

        self._memory = _MetricCard('Memory', self._colors)
        self._cpu = _MetricCard('CPU usage', self._colors)
        self._temperature = _MetricCard('CPU temperature', self._colors)
        self._cpuPower = _MetricCard('CPU power', self._colors)
        self._pcPower = _MetricCard('PC power', self._colors)

        self._memoryUsedCurve = self._memory.spark.addCurve(self._colors['other'])
        self._memoryMeshingCurve = self._memory.spark.addCurve(MESHING, fill=True)
        self._cpuCurve = self._cpu.spark.addCurve(NORMAL, fill=True)
        self._cpuMeshingCurve = self._cpu.spark.addCurve(MESHING)
        self._temperatureCurve = self._temperature.spark.addCurve(NORMAL)
        self._cpuPowerCurve = self._cpuPower.spark.addCurve(NORMAL, fill=True)
        self._pcPowerCurve = self._pcPower.spark.addCurve(NORMAL, fill=True)

        header = QHBoxLayout()
        header.addWidget(self._source, 1)
        header.addWidget(settingsButton, 0, Qt.AlignmentFlag.AlignTop)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.addWidget(self._memory, 0, 0)
        grid.addWidget(self._cpu, 0, 1)
        grid.addWidget(self._temperature, 1, 0)
        grid.addWidget(self._cpuPower, 1, 1)
        grid.addWidget(self._pcPower, 2, 0, 1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(QMargins(6, 6, 6, 6))
        layout.addLayout(header)
        layout.addLayout(grid)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _openSettings(self):
        dialog = ResourceSettingsDialog(self._sampler.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.config()
            saveConfig(config)
            self._sampler.setConfig(config)
            self.refresh()

    def refresh(self):
        sample = self._sampler.latest()
        if sample is None:
            return

        config = self._sampler.config
        history = self._sampler.history()
        xs = [h.time - sample.time for h in history]

        self._refreshSource(sample, config)
        self._refreshMemory(sample, history, xs)
        self._refreshCpu(sample, history, xs)
        self._refreshTemperature(sample, config, history, xs)
        self._refreshCpuPower(sample, config, history, xs)
        self._refreshPcPower(sample, config, history, xs)

    def _refreshSource(self, sample, config):
        if sample.sensorSource == 'LibreHardwareMonitor':
            host = urlparse(config.lhmUrl).netloc or config.lhmUrl
            parts = [f'Temperature and power from LibreHardwareMonitor ({host})']
            if sample.cpuName:
                parts.append(sample.cpuName)
            if sample.gpuNames:
                parts.append(', '.join(sample.gpuNames))
            self._source.setText('  ·  '.join(parts))
        else:
            self._source.setText(f'Temperature and power unavailable: LibreHardwareMonitor not reachable at '
                                 f'{config.lhmUrl}. {LHM_HINT}')

    def _refreshMemory(self, sample, history, xs):
        card = self._memory
        total, used = sample.memTotal, sample.memUsed
        meshing = min(sample.memMeshing, used)
        other = used - meshing
        ratio = used / total if total else 0

        card.setValue(f'{used / GIB:.1f} / {total / GIB:.1f} GB')
        card.bar.setData(total, [(meshing, MESHING), (other, self._colors['other'])])
        if ratio >= MEMORY_CRITICAL_RATIO:
            card.setChip('Nearly full', CRITICAL)
        elif ratio >= MEMORY_WARN_RATIO:
            card.setChip('High', WARN)
        else:
            card.setChip()

        if sample.meshingRanks:
            plural = 'es' if sample.meshingRanks != 1 else ''
            meshingText = f'<span style="color:{MESHING}">■</span> Meshing {meshing / GIB:.1f} GB in ' \
                          f'{sample.meshingRanks} process{plural}'
        else:
            meshingText = f'<span style="color:{MESHING}">■</span> No meshing running'

        card.setDetail(f'{meshingText} · other {other / GIB:.1f} GB · free {(total - used) / GIB:.1f} GB')
        self._memoryUsedCurve.setData(xs, [h.memUsed / GIB for h in history])
        self._memoryMeshingCurve.setData(xs, [min(h.memMeshing, h.memUsed) / GIB for h in history])
        card.spark.setYRange(0, total / GIB, padding=0.05)

    def _refreshCpu(self, sample, history, xs):
        card = self._cpu
        meshing = min(sample.cpuMeshingPercent, sample.cpuPercent)
        card.setValue(f'{sample.cpuPercent:.0f}%')
        card.bar.setData(100, [(meshing, MESHING), (sample.cpuPercent - meshing, NORMAL)])
        card.setChip()
        card.setDetail(f'<span style="color:{MESHING}">■</span> Meshing {meshing:.0f}% · '
                       f'{sample.logicalCores} logical cores')
        self._cpuCurve.setData(xs, [h.cpuPercent for h in history])
        self._cpuMeshingCurve.setData(xs, [min(h.cpuMeshingPercent, h.cpuPercent) for h in history])
        card.spark.setYRange(0, 100, padding=0.05)

    def _unavailable(self, card, reason):
        card.setValue('–')
        card.setChip()
        card.bar.setData(1, [])
        card.setDetail(reason)
        card.spark.setLines([])

    def _refreshTemperature(self, sample, config, history, xs):
        card = self._temperature
        points = [(x, h.cpuTemp) for x, h in zip(xs, history) if h.cpuTemp is not None]
        self._temperatureCurve.setData([p[0] for p in points], [p[1] for p in points])
        card.spark.setLines([(config.tempWarn, WARN), (config.tempCritical, CRITICAL)])
        card.spark.setYRange(30, max(100.0, config.tempCritical + 5), padding=0)

        if sample.cpuTemp is None:
            self._unavailable(card, 'Unavailable: no CPU temperature sensor (see the note above).')
            return

        temperature = sample.cpuTemp
        if temperature >= config.tempCritical:
            color = CRITICAL
            card.setChip('At limit', CRITICAL)
        elif temperature >= config.tempWarn:
            color = WARN
            card.setChip('Near limit', WARN)
        else:
            color = NORMAL
            card.setChip()

        card.setValue(f'{temperature:.1f} °C')
        card.bar.setData(max(100.0, config.tempCritical + 5), [(temperature, color)],
                         [(config.tempWarn, WARN), (config.tempCritical, CRITICAL)])
        card.setDetail(f'Yellow from {config.tempWarn:.0f} °C · red at {config.tempCritical:.0f} °C')

    def _refreshCpuPower(self, sample, config, history, xs):
        card = self._cpuPower
        points = [(x, h.cpuPower) for x, h in zip(xs, history) if h.cpuPower is not None]
        self._cpuPowerCurve.setData([p[0] for p in points], [p[1] for p in points])
        scale = max(config.pptWatts, config.tdpWatts) * 1.05
        card.spark.setLines([(config.tdpWatts, self._colors['muted']), (config.pptWatts, CRITICAL)])
        card.spark.setYRange(0, scale, padding=0)

        if sample.cpuPower is None:
            self._unavailable(card, 'Unavailable: no CPU power sensor (see the note above).')
            return

        power = sample.cpuPower
        if power >= config.pptWatts * 0.98:
            color = CRITICAL
            card.setChip('At PPT limit', CRITICAL)
        elif power > config.tdpWatts:
            color = WARN
            card.setChip('Above TDP', WARN)
        else:
            color = NORMAL
            card.setChip()

        card.setValue(f'{power:.0f} W / {config.tdpWatts:.0f} W TDP ({power / config.tdpWatts:.0%})')
        card.bar.setData(scale, [(power, color)], [(config.tdpWatts, self._colors['muted']),
                                                    (config.pptWatts, CRITICAL)])
        card.setDetail(f'TDP {config.tdpWatts:.0f} W · package power limit (PPT) {config.pptWatts:.0f} W')

    def _refreshPcPower(self, sample, config, history, xs):
        card = self._pcPower
        points = [(x, h.pcPower) for x, h in zip(xs, history) if h.pcPower is not None]
        self._pcPowerCurve.setData([p[0] for p in points], [p[1] for p in points])
        psu = config.psuWatts

        if sample.pcPower is None:
            self._unavailable(card, 'Unavailable: the estimate needs the CPU power sensor (see the note above).')
            return

        power = sample.pcPower
        if sample.pcPowerMeasured:
            source = 'Measured by the PSU sensor'
        else:
            gpu = f'{sample.gpuPower:.0f} W' if sample.gpuPower is not None else 'n/a'
            source = (f'Estimate: CPU {sample.cpuPower:.0f} W + GPU {gpu} + rest of system '
                      f'{config.baselineWatts:.0f} W')

        if psu > 0:
            ratio = power / psu
            if ratio >= 1:
                color = CRITICAL
                card.setChip('Over PSU capacity', CRITICAL)
            elif ratio >= PSU_WARN_RATIO:
                color = WARN
                card.setChip('High load', WARN)
            else:
                color = NORMAL
                card.setChip()

            card.setValue(f'{power:.0f} W / {psu:.0f} W PSU ({ratio:.0%})')
            card.bar.setData(psu * 1.05, [(power, color)], [(psu * PSU_WARN_RATIO, WARN), (psu, CRITICAL)])
            card.setDetail(f'{source} · yellow from {PSU_WARN_RATIO:.0%} of PSU capacity')
            card.spark.setLines([(psu * PSU_WARN_RATIO, WARN), (psu, CRITICAL)])
            card.spark.setYRange(0, psu * 1.05, padding=0)
        else:
            card.setChip()
            card.setValue(f'{power:.0f} W')
            card.bar.setData(max(power * 2, 1), [(power, NORMAL)])
            card.setDetail(f'{source} · set your PSU capacity in Settings to compare')
            card.spark.setLines([])
            card.spark.enableAutoRange(axis='y')


class ResourceView(CDockWidget):
    def __init__(self, sampler: ResourceSampler = None):
        super().__init__(self._title())

        self.setWidget(ResourceWidget(sampler))

    def changeEvent(self, event):
        if event.type() == QEvent.Type.LanguageChange:
            self.setWindowTitle(self._title())

        super().changeEvent(event)

    def _title(self):
        return QCoreApplication.translate('ResourceView', 'Resources')
