#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field, replace
from typing import List, Optional

import psutil


MESHING_PROCESS_NAMES = {
    'snappyhexmesh', 'checkmesh', 'topset', 'blockmesh', 'surfacefeatureextract', 'surfacefeatures',
    'decomposepar', 'reconstructpar', 'reconstructparmesh', 'redistributepar', 'extrudemesh',
    'transformpoints', 'createpatch', 'splitmeshregions', 'foamtovtk'
}
MPI_LAUNCHER_NAMES = {'mpiexec', 'mpirun', 'smpd', 'orted', 'prterun', 'prted', 'hydra_pmi_proxy'}
INTEGRATED_GPU_MARKERS = ('Radeon(TM) Graphics', 'Radeon Graphics', 'UHD Graphics', 'HD Graphics', 'Iris')
LHM_RETRY_SECONDS = 10.0
NVIDIA_SMI_INTERVAL = 2.0

_NUMBER = re.compile(r'[-+]?\d+(?:[.,]\d+)?')


@dataclass
class ResourceConfig:
    tdpWatts: float = 120.0
    pptWatts: float = 162.0
    tempWarn: float = 85.0
    tempCritical: float = 89.0
    psuWatts: float = 0.0
    baselineWatts: float = 60.0
    lhmUrl: str = 'http://localhost:8085/data.json'
    solverBinPath: Optional[str] = None


@dataclass
class HardwareReading:
    cpuName: Optional[str] = None
    cpuTemp: Optional[float] = None
    cpuPower: Optional[float] = None
    gpuPower: Optional[float] = None
    gpuNames: List[str] = field(default_factory=list)
    psuPower: Optional[float] = None


@dataclass
class ResourceSample:
    time: float
    memTotal: int
    memUsed: int
    memMeshing: int
    meshingRanks: int
    cpuPercent: float
    cpuMeshingPercent: float
    logicalCores: int
    cpuName: Optional[str] = None
    cpuTemp: Optional[float] = None
    cpuPower: Optional[float] = None
    gpuPower: Optional[float] = None
    gpuNames: List[str] = field(default_factory=list)
    pcPower: Optional[float] = None
    pcPowerMeasured: bool = False
    sensorSource: Optional[str] = None
    sensorError: Optional[str] = None


def _numeric(node, key='Value'):
    raw = node.get(f'Raw{key}')
    if isinstance(raw, (int, float)):
        return float(raw)

    text = node.get(key)
    if isinstance(text, (int, float)):
        return float(text)

    if not isinstance(text, str):
        return None

    match = _NUMBER.search(text)
    return float(match.group(0).replace(',', '.')) if match else None


def _walkSensors(node, hardware=None, depth=0):
    if node.get('SensorId'):
        yield node, hardware

    for child in node.get('Children') or []:
        yield from _walkSensors(child, child.get('Text') if depth == 1 else hardware, depth + 1)


def _pick(items, preferences):
    for preference in preferences:
        for text, value in items:
            if preference.lower() in text.lower():
                return value

    return max((value for _, value in items), default=None)


def parseLibreHardwareMonitor(data) -> HardwareReading:
    reading = HardwareReading()
    cpuTemps, cpuPowers, psuPowers = [], [], []
    gpus = {}

    for node, hardware in _walkSensors(data):
        parts = node['SensorId'].split('/')
        family = parts[1] if len(parts) > 1 else ''
        kind = (node.get('Type') or (parts[3] if len(parts) > 3 else '')).lower()
        value = _numeric(node)
        if value is None:
            continue

        text = node.get('Text') or ''
        if family in ('amdcpu', 'intelcpu'):
            reading.cpuName = reading.cpuName or hardware
            if kind == 'temperature':
                cpuTemps.append((text, value))
            elif kind == 'power':
                cpuPowers.append((text, value))
        elif family.startswith('gpu') and kind == 'power':
            if hardware and any(marker in hardware for marker in INTEGRATED_GPU_MARKERS):
                continue

            key = '/'.join(parts[1:3])
            gpus.setdefault(key, (hardware, []))[1].append((text, value))
        elif family == 'psu' and kind == 'power':
            psuPowers.append((text, value))

    reading.cpuTemp = _pick(cpuTemps, ('Tctl', 'CPU Package', 'Package', 'Tdie'))
    reading.cpuPower = _pick(cpuPowers, ('Package',))
    if gpus:
        reading.gpuPower = sum(_pick(items, ('Package', 'Total', 'Board')) for _, items in gpus.values())
        reading.gpuNames = [name for name, _ in gpus.values() if name]

    reading.psuPower = _pick(psuPowers, ('Total',))

    return reading


def _linuxCpuTemperature():
    if not hasattr(psutil, 'sensors_temperatures'):
        return None

    try:
        sensors = psutil.sensors_temperatures()
    except Exception:
        return None

    for chip, preferences in (('k10temp', ('Tctl', 'Tdie')), ('coretemp', ('Package',)), ('zenpower', ('Tdie',))):
        entries = sensors.get(chip)
        if entries:
            return _pick([(entry.label or '', entry.current) for entry in entries], preferences)

    return None


class ResourceSampler:
    def __init__(self, config: ResourceConfig, interval=1.0, historySeconds=300):
        self._config = config
        self._interval = interval
        self._history = deque(maxlen=int(historySeconds / interval) + 1)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._lhmRetryAt = 0.0
        self._lhmError = None
        self._nvidiaSmi = shutil.which('nvidia-smi')
        self._nvidiaAt = 0.0
        self._nvidiaPower = None
        self._logicalCores = psutil.cpu_count() or 1

    @property
    def config(self):
        with self._lock:
            return replace(self._config)

    def setConfig(self, config: ResourceConfig):
        with self._lock:
            urlChanged = config.lhmUrl != self._config.lhmUrl
            self._config = replace(config)

        if urlChanged:
            self._lhmRetryAt = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='ResourceSampler', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def latest(self) -> Optional[ResourceSample]:
        with self._lock:
            return self._history[-1] if self._history else None

    def history(self) -> List[ResourceSample]:
        with self._lock:
            return list(self._history)

    def _run(self):
        psutil.cpu_percent(None)
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                sample = self.sampleOnce()
                with self._lock:
                    self._history.append(sample)
            except Exception:
                pass

            self._stop.wait(max(0.0, self._interval - (time.monotonic() - started)))

    def sampleOnce(self) -> ResourceSample:
        config = self.config
        now = time.monotonic()

        memory = psutil.virtual_memory()
        memMeshing, ranks, meshingCpu = self._meshingUsage(config)

        sample = ResourceSample(
            time=now, memTotal=memory.total, memUsed=memory.total - memory.available,
            memMeshing=memMeshing, meshingRanks=ranks, cpuPercent=psutil.cpu_percent(None),
            cpuMeshingPercent=min(100.0, meshingCpu / self._logicalCores), logicalCores=self._logicalCores)

        reading = self._readLibreHardwareMonitor(config, now)
        if reading is not None:
            sample.sensorSource = 'LibreHardwareMonitor'
            sample.cpuName = reading.cpuName
            sample.cpuTemp = reading.cpuTemp
            sample.cpuPower = reading.cpuPower
            sample.gpuPower = reading.gpuPower
            sample.gpuNames = reading.gpuNames
            if reading.psuPower is not None:
                sample.pcPower = reading.psuPower
                sample.pcPowerMeasured = True
        else:
            sample.sensorError = self._lhmError
            sample.cpuTemp = _linuxCpuTemperature()
            if sample.cpuTemp is not None:
                sample.sensorSource = 'psutil'

        if sample.gpuPower is None:
            sample.gpuPower = self._readNvidiaSmi(now)

        if not sample.pcPowerMeasured and sample.cpuPower is not None:
            sample.pcPower = sample.cpuPower + (sample.gpuPower or 0.0) + config.baselineWatts

        return sample

    def _meshingUsage(self, config):
        solverBin = os.path.normcase(str(config.solverBinPath)) if config.solverBinPath else None
        memory, ranks, cpu = 0, 0, 0.0

        for process in psutil.process_iter(['name', 'exe']):
            name = (process.info.get('name') or '').lower()
            stem = name[:-4] if name.endswith('.exe') else name
            exe = process.info.get('exe')
            launcher = stem in MPI_LAUNCHER_NAMES
            meshing = stem in MESHING_PROCESS_NAMES or bool(
                solverBin and exe and os.path.normcase(exe).startswith(solverBin))
            if not (launcher or meshing):
                continue

            try:
                memory += process.memory_info().rss
                cpu += process.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            if meshing and not launcher:
                ranks += 1

        return memory, ranks, cpu

    def _readLibreHardwareMonitor(self, config, now) -> Optional[HardwareReading]:
        if not config.lhmUrl or now < self._lhmRetryAt:
            return None

        try:
            with urllib.request.urlopen(config.lhmUrl, timeout=0.5) as response:
                data = json.loads(response.read().decode('utf-8', errors='replace'))
        except Exception as e:
            self._lhmError = f'{type(e).__name__}: {e}'
            self._lhmRetryAt = now + LHM_RETRY_SECONDS
            return None

        self._lhmError = None
        return parseLibreHardwareMonitor(data)

    def _readNvidiaSmi(self, now):
        if not self._nvidiaSmi:
            return None

        if now - self._nvidiaAt < NVIDIA_SMI_INTERVAL:
            return self._nvidiaPower

        self._nvidiaAt = now
        try:
            output = subprocess.run(
                [self._nvidiaSmi, '--query-gpu=power.draw', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
            values = [float(v) for v in (line.strip() for line in output.splitlines()) if _NUMBER.fullmatch(v)]
            self._nvidiaPower = sum(values) if values else None
        except Exception:
            self._nvidiaPower = None

        return self._nvidiaPower
