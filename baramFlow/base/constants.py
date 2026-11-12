#!/usr/bin/env python
# -*- coding: utf-8 -*-


from enum import Enum, IntFlag

from baramFlow.coredb.libdb import ElementEnum


class FieldCategory(ElementEnum):
    GEOMETRY    = 'geometry'
    BASIC       = 'basic'
    COLLATERAL  = 'collateral'
    PHASE       = 'phase'
    SPECIE      = 'specie'
    USER_SCALAR = 'userScalar'


class FieldType(ElementEnum):
    VECTOR = 'vector'
    SCALAR = 'scalar'


class VectorComponent(IntFlag):
    MAGNITUDE = 1
    X         = 2
    Y         = 4
    Z         = 8


class Function1Type(ElementEnum):
    CONSTANT    = "constant"
    TABLE       = "table"