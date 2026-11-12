#!/usr/bin/env python
# -*- coding: utf-8 -*-

from enum import Enum, auto

from PySide6.QtCore import QCoreApplication

from baramFlow.coredb.libdb import ElementEnum
from baramFlow.coredb import coredb


MODELS_XPATH = '/models'
ENERGY_MODELS_XPATH     = '/models/energyModels'


class Models(Enum):
    TURBULENCE  = auto()
    ENERGY      = auto()
    FLOW_TYPE   = auto()
    MULTIPHASE  = auto()
    SOLVER_TYPE = auto()
    SPECIES     = auto()
    SCALARS     = auto()
    DPM         = auto()


class DPMParticleType(ElementEnum):
    NONE        = 'none'
    INERT       = 'inert'
    DROPLET     = 'droplet'
    COMBUSTING  = 'combusting'


class DPMTrackingScheme(ElementEnum):
    IMPLICIT    = 'implicit'
    ANALYTIC    = 'analytic'


class DPMDragForce(ElementEnum):
    SPHERICAL               = 'sphereDrag'
    NON_SPHERICAL           = 'nonSphereDrag'
    DISTORTED_SPHERE        = 'distortedSphereDrag'
    WEN_AND_YU              = 'WenYuDrag'
    GIDASPOW                = 'ErgunWenYuDrag'
    DU_PIESSIS_AND_MASLIYAH = 'PlessisMasliyahDrag'
    TOMIYAMA                = 'TomiyamaDrag'


class DPMLiftForce(ElementEnum):
    NONE        = 'none'
    SAFFMAN_MEI = 'SaffmanMeiLiftForce'
    TOMIYAMA    = 'TomiyamaLift'


class Contamination(ElementEnum):
    NO_CONTAMINATION        = 'pure'
    SLIGHT_CONTAMINATION    = 'slight'
    FULL_CONTAMINATION      = 'full'


class DPMTurbulentDispersion(ElementEnum):
    NONE                    = 'none'
    STOCHASTIC_DISPERSION  = 'stochasticDispersionRAS'
    GRADIENT_DISPERSION     = 'gradientDispersionRAS'


class DPMHeatTransferSpeicification(ElementEnum):
    NONE            = 'none'
    RANZ_MARHALL    = 'RanzMarshall'


class DPMEvaporationModel(ElementEnum):
    NONE                            = 'none'
    DIFFUSION_CONTROLLED            = 'diffusionControlled'
    CONVECTION_DIFFUSION_CONTROLLED = 'convectionDiffusionControlled'


class DPMEnthalpyTransferType(ElementEnum):
    ENTHALPY_DIFFENENCE = 'enthalpyDifference'
    LATENT_HEAT         = 'latentHeat'


class DPMInjectionType(ElementEnum):
    POINT   = 'point'
    SURFACE = 'surface'
    CONE    = 'cone'


class DPMDiameterDistribution(ElementEnum):
    UNIFORM             = 'uniform'
    LINEAR              = 'linear'
    ROSIN_RAMMLER       = 'rosinRammler'
    MASS_ROSIN_RAMMLER  = 'massRosinRammler'
    NORMAL              = 'normal'


class DPMFlowRateSpec(ElementEnum):
    PARTICLE_COUNT  = 'particleCount'
    PARTICLE_VOLUME = 'particleVolume'


class DPMConeInjectorType(ElementEnum):
    POINT   = 'point'
    DISC    = 'disc'


class DPMParticleSpeed(ElementEnum):
    FROM_INJECTION_SPEED    = 'fromInjectionSpeed'
    FROM_PRESSURE           = 'fromPressure'
    FROM_DISCHARGE_COEFF    = 'fromDischargeCoeff'


class DPMParticleVelocityType(ElementEnum):
    CONSTANT    = 'constant'
    FACE_VALUE  = 'faceValue'
    CELL_VALUE  = 'cellValue'


DPM_INJECTION_TYPE_TEXTS = {
    DPMInjectionType.POINT      : QCoreApplication.translate('DPM', 'Point'),
    DPMInjectionType.SURFACE    : QCoreApplication.translate('DPM', 'Surface'),
    DPMInjectionType.CONE       : QCoreApplication.translate('DPM', 'Cone')
}


class ModelManager:
    @staticmethod
    def energyModelOn():
        coredb.CoreDB().setValue(ENERGY_MODELS_XPATH, 'on')

    @staticmethod
    def energyModelOff():
        coredb.CoreDB().setValue(ENERGY_MODELS_XPATH, 'off')
