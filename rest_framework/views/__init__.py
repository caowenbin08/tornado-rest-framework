# -*- coding: utf-8 -*-
from rest_framework.views.generics import (
    GenericAPIHandler,
    ListAPIHandler,
    CreateAPIHandler,
    RetrieveUpdateAPIHandler,
    DestroyAPIHandler
)
from rest_framework.views.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin
)
from rest_framework.views.generics import __all__ as generics_all
from rest_framework.views.mixins import __all__ as mixin_all

__author__ = 'caowenbin'

__all__ = generics_all + mixin_all
