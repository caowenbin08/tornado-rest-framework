# -*- coding: utf-8 -*-
from rest_framework.utils.escape import json_encode
from rest_framework.utils.escape import json_decode
from rest_framework.utils.transcoder import force_bytes


class Handler:
    def dumps(self, value):
        return force_bytes(json_encode(value))

    def loads(self, value):
        return json_decode(value)
