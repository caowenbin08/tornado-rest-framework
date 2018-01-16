# -*- coding: utf-8 -*-
import zlib

from rest_framework.core.exceptions import CompressorError
from rest_framework.core.compressors.base import BaseCompressor


class ZlibCompressor(BaseCompressor):
    min_length = 15
    preset = 6

    def compress(self, value):
        if len(value) > self.min_length:
            return zlib.compress(value, self.preset)
        return value

    def decompress(self, value):
        try:
            return zlib.decompress(value)
        except zlib.error as e:
            raise CompressorError(e)
