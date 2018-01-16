# -*- coding: utf-8 -*-
from rest_framework.core.exceptions import ImproperlyConfigured
from rest_framework.core.serializers.base import BaseSerializer

try:
    import cPickle as pickle
except ImportError:
    import pickle


class PickleSerializer(BaseSerializer):
    def __init__(self, options):
        self._pickle_version = -1
        self.setup_pickle_version(options)

    def setup_pickle_version(self, options):
        if "PICKLE_VERSION" in options:
            try:
                self._pickle_version = int(options["PICKLE_VERSION"])
            except (ValueError, TypeError):
                raise ImproperlyConfigured("PICKLE_VERSION value must be an integer")

    def dumps(self, value):
        return pickle.dumps(value, self._pickle_version)

    def loads(self, value):
        return pickle.loads(value)
