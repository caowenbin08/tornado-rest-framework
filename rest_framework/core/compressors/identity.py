# -*- coding: utf-8 -*-
from rest_framework.core.compressors.base import BaseCompressor
__author__ = 'caowenbin'


class IdentityCompressor(BaseCompressor):
    def compress(self, value):
        return value

    def decompress(self, value):
        return value
