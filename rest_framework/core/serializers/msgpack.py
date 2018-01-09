# -*- coding: utf-8 -*-
import msgpack

from rest_framework.core.serializers.base import BaseSerializer


class MSGPackSerializer(BaseSerializer):
    def dumps(self, value):
        return msgpack.dumps(value)

    def loads(self, value):
        return msgpack.loads(value, encoding="utf-8")
