# -*- coding: utf-8 -*-
try:
    import ujson as json
except ImportError:
    import json

try:
    import uvloop as asynclib
except ImportError:
    import asyncio as asynclib
