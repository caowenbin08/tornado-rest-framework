# -*- coding: utf-8 -*-
import msgpack


class Handler:
    def dumps(self, value):
        return msgpack.dumps(value)

    def loads(self, value):
        return msgpack.loads(value, encoding="utf-8")
