#!/usr/bin/env python
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from uuid import UUID

from vtkmodules.vtkCommonDataModel import vtkMultiBlockDataSet, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkPointDataToCellData
from vtkmodules.vtkFiltersParallelDIY2 import vtkProbeLineFilter
from vtkmodules.vtkFiltersSources import vtkLineSource

from baramFlow.coredb import coredb
from baramFlow.coredb.libdb import E, nsmap
from baramFlow.base.scaffold.scaffold import Scaffold
from libbaram.openfoam.polymesh import collectInternalMesh
from libbaram.vtk_threads import vtk_run_in_thread


@dataclass
class LineScaffold(Scaffold):
    point1X: str = '0'
    point1Y: str = '0'
    point1Z: str = '0'

    point2X: str = '1'
    point2Y: str = '0'
    point2Z: str = '0'

    numberOfSamples: int = 10

    @classmethod
    def parseScaffolds(cls) -> dict[UUID, Scaffold]:
        scaffolds: dict[UUID, Scaffold] = {}

        for e in coredb.CoreDB().getElements(Scaffold.SCAFFOLDS_PATH + '/lineScaffolds/lineScaffold'):
            s = LineScaffold.fromElement(e)
            scaffolds[s.uuid] = s

        return scaffolds

    @classmethod
    def fromElement(cls, e):
        uuid = UUID(e.find('uuid', namespaces=nsmap).text)
        name = e.find('name', namespaces=nsmap).text

        point1X = e.find('point1/x', namespaces=nsmap).text
        point1Y = e.find('point1/y', namespaces=nsmap).text
        point1Z = e.find('point1/z', namespaces=nsmap).text

        point2X = e.find('point2/x', namespaces=nsmap).text
        point2Y = e.find('point2/y', namespaces=nsmap).text
        point2Z = e.find('point2/z', namespaces=nsmap).text

        numberOfSamples = int(e.find('numberOfSamples', namespaces=nsmap).text)

        return LineScaffold(uuid=uuid,
                          name=name,
                          point1X=point1X,
                          point1Y=point1Y,
                          point1Z=point1Z,
                          point2X=point2X,
                          point2Y=point2Y,
                          point2Z=point2Z,
                          numberOfSamples=numberOfSamples)

    def toElement(self):
        return E('lineScaffold',
                 E('uuid', str(self.uuid)),
                 E('name', self.name),
                 E('point1',
                     E('x', self.point1X),
                     E('y', self.point1Y),
                     E('z', self.point1Z)),
                 E('point2',
                     E('x', self.point2X),
                     E('y', self.point2Y),
                     E('z', self.point2Z)),
                 E('numberOfSamples', str(self.numberOfSamples)))

    def xpath(self):
        return f'/lineScaffold[uuid="{str(self.uuid)}"]'

    def addElement(self):
        coredb.CoreDB().addElement(Scaffold.SCAFFOLDS_PATH + '/lineScaffolds', self.toElement())

    def removeElement(self):
        coredb.CoreDB().removeElement(Scaffold.SCAFFOLDS_PATH + '/lineScaffolds' + self.xpath())

    async def getDataSet(self, mBlock: vtkMultiBlockDataSet) -> vtkPolyData:
        mesh = await collectInternalMesh(mBlock)

        line = vtkLineSource()
        line.SetPoint1(float(self.point1X), float(self.point1Y), float(self.point1Z))
        line.SetPoint2(float(self.point2X), float(self.point2Y), float(self.point2Z))
        line.UseRegularRefinementOn()
        line.SetResolution(1)

        probe = vtkProbeLineFilter()
        probe.SetInputData(mesh)
        probe.SetSourceConnection(line.GetOutputPort())
        probe.SetSamplingPattern(vtkProbeLineFilter.SAMPLE_LINE_UNIFORMLY)
        probe.SetLineResolution(self.numberOfSamples)
        probe.PassPointArraysOn()
        probe.PassFieldArraysOn()
        probe.PassPartialArraysOn()
        probe.AggregateAsPolyDataOn()

        p2c = vtkPointDataToCellData()
        p2c.PassPointDataOn()
        p2c.ProcessAllArraysOn()
        p2c.SetInputConnection(probe.GetOutputPort())

        await vtk_run_in_thread(p2c.Update)

        return p2c.GetOutput()