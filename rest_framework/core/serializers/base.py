# -*- coding: utf-8 -*-


class BaseSerializer(object):
    def __init__(self, options):
        pass

    def dumps(self, value):
        raise NotImplementedError

    def loads(self, value):
        raise NotImplementedError
