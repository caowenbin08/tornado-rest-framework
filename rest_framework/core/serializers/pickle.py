# -*- coding: utf-8 -*-
try:
    import cPickle as pickle
except ImportError:
    import pickle


class Handler:
    _pickle_version = pickle.HIGHEST_PROTOCOL

    def dumps(self, value):
        return pickle.dumps(value, self._pickle_version)

    def loads(self, value):
        return pickle.loads(value)
