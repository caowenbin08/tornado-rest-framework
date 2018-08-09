# -*- coding: utf-8 -*-
from rest_framework.utils import json
from rest_framework.utils.transcoder import force_text


def json_encode(value):
    return json.dumps(value, escape_forward_slashes=False)


def json_decode(value):
    return json.loads(force_text(value))
