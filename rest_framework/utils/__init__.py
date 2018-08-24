# -*- coding: utf-8 -*-
try:
    import ujson as jsonlib
    has_ujson = True
except ImportError:
    import json as jsonlib
    has_ujson = False

