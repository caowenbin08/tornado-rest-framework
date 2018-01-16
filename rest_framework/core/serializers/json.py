# -*- coding: utf-8 -*-
import json

from rest_framework.core.serializers.base import BaseSerializer
from rest_framework.utils.transcoder import force_bytes, force_text


class JSONSerializer(BaseSerializer):
    def dumps(self, value):
        return force_bytes(json.dumps(value))

    def loads(self, value):
        return json.loads(force_text(value))
