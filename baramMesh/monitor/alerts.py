#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple


GIB = 1024 ** 3
MEMORY_THRESHOLDS = (0.85, 0.95)
MEMORY_HYSTERESIS = 0.03
TEMPERATURE_HYSTERESIS = 3.0
POWER_HYSTERESIS_WATTS = 5.0
PSU_WARN_RATIO = 0.8
STOP_GRACE_SECONDS = 8.0
EVENT_CAPACITY = 200


@dataclass
class Event:
    id: int
    time: float
    kind: str
    severity: str
    title: str
    message: str
    notify: bool

    def asDict(self):
        return {
            'id': self.id, 'time': self.time, 'kind': self.kind, 'severity': self.severity,
            'title': self.title, 'message': self.message, 'notify': self.notify
        }


class EventLog:
    def __init__(self, capacity: int = EVENT_CAPACITY, clock=time.time):
        self._events = deque(maxlen=capacity)
        self._clock = clock
        self._lastId = 0
        self._condition = threading.Condition()

    def add(self, kind, severity, title, message, notify=True) -> Event:
        with self._condition:
            self._lastId += 1
            event = Event(self._lastId, self._clock(), kind, severity, title, message, notify)
            self._events.append(event)
            self._condition.notify_all()

        return event

    def lastId(self) -> int:
        with self._condition:
            return self._lastId

    def since(self, lastId: int) -> List[Event]:
        with self._condition:
            return [event for event in self._events if event.id > lastId]

    def wait(self, lastId: int, timeout: float) -> List[Event]:
        with self._condition:
            self._condition.wait_for(lambda: self._lastId > lastId, timeout)
            return [event for event in self._events if event.id > lastId]


class _Level:
    def __init__(self, hysteresis: float):
        self.level = 0
        self.hysteresis = hysteresis

    def update(self, value: float, thresholds) -> Optional[Tuple[int, int]]:
        raised = 0
        held = 0
        for index, threshold in enumerate(thresholds, 1):
            if value >= threshold:
                raised = index

            if value >= threshold - self.hysteresis:
                held = index

        target = raised if raised > self.level else min(self.level, held)
        if target == self.level:
            return None

        old, self.level = self.level, target
        return old, target


class AlertEngine:
    def __init__(self, log: EventLog):
        self._log = log
        self._memory = _Level(MEMORY_HYSTERESIS)
        self._temperature = _Level(TEMPERATURE_HYSTERESIS)
        self._cpuPower = _Level(POWER_HYSTERESIS_WATTS)
        self._psu = _Level(0.0)
        self._runId = None
        self._stalled = False
        self._finished = False
        self._phaseKey = None
        self._armed = False
        self._zeroSince = None

    def evaluate(self, sample, config, progress: Optional[dict], now: Optional[float] = None):
        now = time.monotonic() if now is None else now
        self._memoryAlerts(sample)
        self._temperatureAlerts(sample, config)
        self._powerAlerts(sample, config)
        self._progressAlerts(progress)
        self._processAlerts(sample, progress, now)

    def _memoryAlerts(self, sample):
        if not sample.memTotal:
            return

        ratio = sample.memUsed / sample.memTotal
        change = self._memory.update(ratio, MEMORY_THRESHOLDS)
        if change is None:
            return

        old, new = change
        detail = (f'{sample.memUsed / GIB:.1f} of {sample.memTotal / GIB:.1f} GB used '
                  f'({sample.memMeshing / GIB:.1f} GB by meshing)')
        if new == 2:
            self._log.add('memory', 'critical', 'Memory nearly full', detail)
        elif new == 1 and old == 0:
            self._log.add('memory', 'warning', 'Memory use high', detail)
        elif new == 0:
            self._log.add('memory', 'info', 'Memory use back to normal', detail, notify=False)

    def _temperatureAlerts(self, sample, config):
        if sample.cpuTemp is None:
            return

        change = self._temperature.update(sample.cpuTemp, (config.tempWarn, config.tempCritical))
        if change is None:
            return

        old, new = change
        if new == 2:
            self._log.add('temperature', 'critical', 'CPU at thermal limit',
                          f'{sample.cpuTemp:.0f} °C, limit {config.tempCritical:.0f} °C')
        elif new == 1 and old == 0:
            self._log.add('temperature', 'warning', 'CPU temperature high',
                          f'{sample.cpuTemp:.0f} °C, yellow from {config.tempWarn:.0f} °C')
        elif new == 0:
            self._log.add('temperature', 'info', 'CPU temperature back to normal',
                          f'{sample.cpuTemp:.0f} °C', notify=False)

    def _powerAlerts(self, sample, config):
        if sample.cpuPower is not None and not sample.cpuPowerEstimated:
            change = self._cpuPower.update(sample.cpuPower, (config.pptWatts * 0.98,))
            if change is not None:
                if change[1] > change[0]:
                    self._log.add('cpu_power', 'critical', 'CPU at power limit',
                                  f'{sample.cpuPower:.0f} W of {config.pptWatts:.0f} W package limit')
                else:
                    self._log.add('cpu_power', 'info', 'CPU power back below limit',
                                  f'{sample.cpuPower:.0f} W', notify=False)

        if config.psuWatts > 0 and sample.pcPower is not None:
            self._psu.hysteresis = config.psuWatts * 0.05
            change = self._psu.update(sample.pcPower, (config.psuWatts * PSU_WARN_RATIO, config.psuWatts))
            if change is None:
                return

            old, new = change
            kind = 'measured' if sample.pcPowerMeasured else 'estimated'
            detail = f'{sample.pcPower:.0f} W {kind} of {config.psuWatts:.0f} W PSU capacity'
            if new == 2:
                self._log.add('psu', 'critical', 'System power over PSU capacity', detail)
            elif new == 1 and old == 0:
                self._log.add('psu', 'warning', 'System power high', detail)
            elif new == 0:
                self._log.add('psu', 'info', 'System power back to normal', detail, notify=False)

    def _progressAlerts(self, progress):
        if not progress or not progress.get('program'):
            return

        if progress['runId'] != self._runId:
            self._runId = progress['runId']
            self._stalled = False
            self._finished = False
            self._phaseKey = None
            program = progress['program'].replace('\\', '/').split('/')[-1]
            self._log.add('run_started', 'info', 'Meshing started', program, notify=False)

        phaseKey = (progress['mode'], progress.get('phase'))
        if phaseKey != self._phaseKey and progress.get('phase'):
            if self._phaseKey is not None:
                self._log.add('phase', 'info', f'{progress["phase"].capitalize()} started',
                              f'{progress["step"]}', notify=False)

            self._phaseKey = phaseKey

        health = progress['health']
        if progress['mode'] == 'layers' and health['key'] == 'warn' and not self._stalled and not progress['finished']:
            self._stalled = True
            self._log.add('layers_stalled', 'warning', 'Layer addition stalled', health['text'])

        if progress['finished'] and not self._finished:
            self._finished = True
            illegal = progress['finishedIllegal']
            if illegal:
                self._log.add('run_finished', 'warning', f'{progress["step"]} finished with issues',
                              f'{illegal:,} illegal faces')
            else:
                self._log.add('run_finished', 'info', f'{progress["step"]} finished', 'No errors')

    def _processAlerts(self, sample, progress, now):
        finished = bool(progress and progress.get('finished'))
        if sample.meshingRanks > 0:
            self._armed = not finished
            self._zeroSince = None
            return

        if not self._armed or finished:
            self._armed = False
            return

        if self._zeroSince is None:
            self._zeroSince = now
            return

        if now - self._zeroSince >= STOP_GRACE_SECONDS:
            self._armed = False
            phase = (progress or {}).get('phase') or 'unknown'
            self._log.add('run_stopped', 'critical', 'Meshing stopped before finishing',
                          f'Processes ended without a completion message (last phase: {phase}). '
                          f'Possible crash, out of memory, or cancelled run.')
