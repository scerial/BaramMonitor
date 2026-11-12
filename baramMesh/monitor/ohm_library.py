#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ctypes
import os
import sys


LIBRARY_FILE = 'OpenHardwareMonitorLib.dll'


def isAdministrator() -> bool:
    if sys.platform != 'win32':
        return True

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def findLibrary(configured, hintDirectories=()):
    candidates = []
    if configured:
        candidates.append(os.path.join(configured, LIBRARY_FILE) if os.path.isdir(configured) else configured)

    candidates.extend(os.path.join(directory, LIBRARY_FILE) for directory in hintDirectories if directory)
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), LIBRARY_FILE))

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def sensorTree(hardwareItems) -> dict:
    hardwareNodes = []

    def visit(hardware):
        hardware.Update()
        sensors = []
        for sensor in hardware.Sensors:
            value = sensor.Value
            if value is None:
                continue

            sensors.append({
                'Text': str(sensor.Name),
                'SensorId': str(sensor.Identifier),
                'Type': str(sensor.SensorType),
                'RawValue': float(value)
            })

        hardwareNodes.append({'Text': str(hardware.Name), 'Children': sensors})
        for sub in hardware.SubHardware:
            visit(sub)

    for hardware in hardwareItems:
        visit(hardware)

    return {'Children': [{'Text': 'PC', 'Children': hardwareNodes}]}


class OhmLibrary:
    def __init__(self, path: str):
        self.path = path
        self._computer = None

    def open(self):
        import clr

        directory = os.path.dirname(os.path.abspath(self.path))
        if directory not in sys.path:
            sys.path.append(directory)

        clr.AddReference(os.path.abspath(self.path))
        from OpenHardwareMonitor.Hardware import Computer

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.IsPsuEnabled = True
        computer.Open(False)
        self._computer = computer

    def read(self) -> dict:
        return sensorTree(list(self._computer.Hardware))

    def close(self):
        computer, self._computer = self._computer, None
        if computer is not None:
            try:
                computer.Close()
            except Exception:
                pass
