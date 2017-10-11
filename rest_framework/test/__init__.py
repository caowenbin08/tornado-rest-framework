# -*- coding: utf-8 -*-
import os
__author__ = 'caowenbin'


def setup_module(module):
    os.environ.setdefault("TORNADO_REST_SETTINGS_MODULE", "rest_framework.test.settings")