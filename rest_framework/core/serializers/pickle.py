# -*- coding: utf-8 -*-
import pickle


class Handler:

    def dumps(self, value):
        return pickle.dumps(value, protocol=1)

    def loads(self, value):
        return pickle.loads(value)
