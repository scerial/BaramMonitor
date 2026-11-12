#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional


_REFINEMENT_ITERATION = re.compile(r'^\s*(\w[\w ]*?) refinement iteration (\d+)\s*$')
_SELECTED = re.compile(r'^\s*Selected for (?:feature |internal )?refinement\s*:\s*(\d+) cells \(out of (\d+)\)')
_MARKED = re.compile(r'^\s*Marked for refinement due to (.+?)\s*:\s*(\d+) cells')
_EDGES = re.compile(r'^\s*Number of edges\s*:\s*(\d+)')
_MORPH = re.compile(r'^\s*Morph iteration (\d+)')
_LAYER_ITERATION = re.compile(r'^\s*Layer addition iteration (\d+)')
_EXTRUDING = re.compile(r'^\s*Extruding (\d+) out of (\d+) faces \(([\d.]+)%\)')
_EXEC = re.compile(r'^\s*Exec\s*:\s*(\S+)')


@dataclass
class RefinementSample:
    index: int
    label: str
    iteration: int
    selected: int
    total: int
    wallTime: float
    duration: Optional[float] = None


@dataclass
class ProgressState:
    program: str = ''
    phase: str = ''
    iteration: Optional[int] = None
    selected: Optional[int] = None
    totalCells: Optional[int] = None
    edges: Optional[int] = None
    morphIteration: Optional[int] = None
    layerIteration: Optional[int] = None
    extrusionPercent: Optional[float] = None
    startTime: float = field(default_factory=time.monotonic)
    samples: List[RefinementSample] = field(default_factory=list)
    marked: dict = field(default_factory=dict)


class SnappyLogParser:
    def __init__(self):
        self.state = ProgressState()
        self._label = ''
        self._lastSampleTime: Optional[float] = None

    def reset(self):
        self.state = ProgressState()
        self._label = ''
        self._lastSampleTime = None

    def feed(self, line: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        state = self.state

        if m := _EXEC.match(line):
            if 'snappyHexMesh' in m.group(1):
                self.reset()
                self.state.program = m.group(1)
                return True

            return False

        if m := _REFINEMENT_ITERATION.match(line):
            self._label = m.group(1).strip()
            state.phase = f'{self._label} refinement'
            state.iteration = int(m.group(2))
            state.marked = {}
            return True

        if m := _MARKED.match(line):
            state.marked[m.group(1)] = int(m.group(2))
            return True

        if m := _SELECTED.match(line):
            selected, total = int(m.group(1)), int(m.group(2))
            duration = None if self._lastSampleTime is None else now - self._lastSampleTime
            self._lastSampleTime = now
            state.selected = selected
            state.totalCells = total
            state.samples.append(RefinementSample(
                index=len(state.samples), label=self._label, iteration=state.iteration or 0,
                selected=selected, total=total, wallTime=now - state.startTime, duration=duration))
            return True

        if m := _EDGES.match(line):
            state.edges = int(m.group(1))
            return True

        if m := _MORPH.match(line):
            state.phase = 'snapping'
            state.morphIteration = int(m.group(1))
            return True

        if m := _LAYER_ITERATION.match(line):
            state.phase = 'layer addition'
            state.layerIteration = int(m.group(1))
            state.extrusionPercent = None
            return True

        if m := _EXTRUDING.match(line):
            state.phase = 'layer addition'
            state.extrusionPercent = float(m.group(3))
            return True

        return False
