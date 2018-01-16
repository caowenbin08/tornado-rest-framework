# -*- coding: utf-8 -*-
import lzma

from rest_framework.core.exceptions import CompressorError
from rest_framework.core.compressors.base import BaseCompressor


class LzmaCompressor(BaseCompressor):
    min_length = 100
    preset = 4

    def compress(self, value):
        if len(value) > self.min_length:
            return lzma.compress(value, preset=self.preset)
        return value

    def decompress(self, value):
        try:
            return lzma.decompress(value)
        except lzma.LZMAError as e:
            raise CompressorError(e)
