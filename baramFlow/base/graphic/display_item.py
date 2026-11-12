#!/usr/bin/env python
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from dataclasses import field as dataClassField
from uuid import UUID

from PySide6.QtGui import QColor

from vtkmodules.vtkCommonDataModel import vtkDataSet

from baramFlow.coredb.libdb import E, nsmap
from baramFlow.base.constants import VectorComponent
from baramFlow.base.field import Field
from baramFlow.base.scaffold.scaffolds_db import ScaffoldsDB
from baramFlow.libbaram.util import getScalarRange, getVectorRange

from libbaram.async_signal import AsyncSignal


@dataclass
class DisplayItem:
    instanceUpdated: AsyncSignal = dataClassField(init=False)

    scaffoldUuid: UUID  = UUID(int = 0)
    dataSet: vtkDataSet = None

    visibility: bool = True
    opacity: float = 1
    solidColor: bool = False
    color: QColor = dataClassField(default_factory=lambda: QColor.fromString('#FFFFFF'))
    edges: bool = False
    faces: bool = True
    frontFaceCulling: bool = False
    vectorsOn: bool = False
    streamlinesOn: bool = False
    maxNumberOfSamplePoints: int = 100
    streamlinesIntegrateForward: bool = True
    streamlinesIntegrateBackward: bool = False

    def __post_init__(self):
        self.instanceUpdated = AsyncSignal(UUID)

    @classmethod
    def fromElement(cls, e):
        scaffoldUuid = UUID(e.find('scaffoldUuid', namespaces=nsmap).text)
        visibility = (e.find('visibility', namespaces=nsmap).text == 'true')
        opacity = float(e.find('opacity', namespaces=nsmap).text)
        solidColor = (e.find('solidColor', namespaces=nsmap).text == 'true')
        color = QColor.fromString(e.find('color', namespaces=nsmap).text)
        edges = (e.find('edges', namespaces=nsmap).text == 'true')
        faces = (e.find('faces', namespaces=nsmap).text == 'true')
        frontFaceCulling = (e.find('frontFaceCulling', namespaces=nsmap).text == 'true')
        vectorsOn = (e.find('vectorsOn', namespaces=nsmap).text == 'true')
        streamlinesOn = (e.find('streamlinesOn', namespaces=nsmap).text == 'true')
        maxNumberOfSamplePoints = int(e.find('maxNumberOfSamplePoints', namespaces=nsmap).text)
        streamlinesIntegrateForward = True if e.find('streamlinesIntegrateForward', namespaces=nsmap).text == 'true' else False
        streamlinesIntegrateBackward = True if e.find('streamlinesIntegrateBackward', namespaces=nsmap).text == 'true' else False

        return DisplayItem(scaffoldUuid=scaffoldUuid,
                           visibility=visibility,
                           opacity=opacity,
                           solidColor=solidColor,
                           color=color,
                           edges=edges,
                           faces=faces,
                           frontFaceCulling=frontFaceCulling,
                           vectorsOn=vectorsOn,
                           streamlinesOn=streamlinesOn,
                           maxNumberOfSamplePoints=maxNumberOfSamplePoints,
                           streamlinesIntegrateForward=streamlinesIntegrateForward,
                           streamlinesIntegrateBackward=streamlinesIntegrateBackward)

    def toElement(self):
        return E('displayItem',
                 E('scaffoldUuid', str(self.scaffoldUuid)),
                 E('visibility', self.visibility),
                 E('opacity', str(self.opacity)),
                 E('solidColor', self.solidColor),
                 E('color', self.color.name()),
                 E('edges', self.edges),
                 E('faces', self.faces),
                 E('frontFaceCulling', self.frontFaceCulling),
                 E('vectorsOn', self.vectorsOn),
                 E('streamlinesOn', self.streamlinesOn),
                 E('maxNumberOfSamplePoints', str(self.maxNumberOfSamplePoints)),
                 E('streamlinesIntegrateForward', self.streamlinesIntegrateForward),
                 E('streamlinesIntegrateBackward', self.streamlinesIntegrateBackward))

    async def markUpdated(self):
        await self.instanceUpdated.emit(self.scaffoldUuid)

    @property
    def name(self):
        scaffold = ScaffoldsDB().getScaffold(self.scaffoldUuid)
        return scaffold.name

    def getScalarRange(self, scalar: Field, useNodeValues: bool) -> tuple[float, float]:
        return getScalarRange(self.dataSet, scalar, useNodeValues)

    def getVectorRange(self, scalar: Field, vectorComponent: VectorComponent, useNodeValues: bool) -> tuple[float, float]:
        return getVectorRange(self.dataSet, scalar, vectorComponent, useNodeValues)