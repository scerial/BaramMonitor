#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from typing import Optional, Tuple


STALL_WINDOW = 10
STALL_TOLERANCE = 0.5
STALL_CEILING = 90
REFINEMENT_GROUPS = ('Feature', 'Surface', 'Shell')


def refinementGroup(label: str) -> str:
    return label if label in REFINEMENT_GROUPS else 'Cleanup'


def layersStalled(samples) -> bool:
    if len(samples) < STALL_WINDOW:
        return False

    last = samples[-1]
    return (last.extrudedPercent < STALL_CEILING
            and abs(last.extrudedPercent - samples[-STALL_WINDOW].extrudedPercent) < STALL_TOLERANCE)


def progressMode(state) -> str:
    if state.phase == 'layer addition' and state.layerSamples:
        return 'layers'

    if state.phase == 'snapping':
        return 'snap'

    return 'refinement'


def stepName(state) -> str:
    if state.layerSamples:
        return 'Layer addition'

    if state.snapSamples:
        return 'Snapping'

    return 'Castellation'


def progressHealth(state, mode: Optional[str] = None) -> Tuple[str, str]:
    mode = mode or progressMode(state)

    if state.finished:
        if state.finishedIllegal == 0:
            return 'done', 'Finished, no errors'

        return 'warn', f'Finished with {state.finishedIllegal:,} illegal faces'

    if mode == 'layers':
        last = state.layerSamples[-1]
        if last.illegalFaces == 0 and last.extrudedPercent >= 99:
            return 'done', 'Layers complete'

        if layersStalled(state.layerSamples):
            return 'warn', f'Stalled at {last.extrudedPercent:.0f}% extruded'

        return 'running', 'Adding layers'

    if mode == 'snap':
        return 'running', 'Snapping'

    if state.samples:
        last = state.samples[-1]
        if last.selected == 0:
            return 'done', f'{refinementGroup(last.label)} converged'

        return 'running', f'Refining ({refinementGroup(last.label).lower()})'

    if state.phase:
        return 'running', state.phase.capitalize()

    return 'idle', 'Waiting for output'


def progressSnapshot(state, now: Optional[float] = None, maxPoints: int = 120) -> dict:
    now = time.monotonic() if now is None else now
    mode = progressMode(state)
    key, text = progressHealth(state, mode)
    active = bool(state.program or state.phase)

    return {
        'runId': state.startTime,
        'program': state.program,
        'phase': state.phase,
        'mode': mode,
        'step': stepName(state),
        'health': {'key': key, 'text': text},
        'elapsed': round(now - state.startTime, 1) if active else None,
        'iteration': state.iteration,
        'selected': state.selected,
        'totalCells': state.totalCells,
        'morphIteration': state.morphIteration,
        'morphTotal': state.morphTotal,
        'layerIteration': state.layerIteration,
        'extrusionPercent': state.extrusionPercent,
        'lastIllegal': state.lastIllegal,
        'finished': state.finished,
        'finishedIllegal': state.finishedIllegal,
        'refinementSteps': len(state.samples),
        'series': {
            'selected': [s.selected for s in state.samples[-maxPoints:]],
            'extruded': [round(s.extrudedPercent, 2) for s in state.layerSamples[-maxPoints:]]
        }
    }
