# -*- coding: utf-8 -*-
"""
解析请求参数
"""
from rest_framework.core.exceptions import ParseError, InvalidJSON
from rest_framework.utils.transcoder import force_text


class DataAndFiles(object):
    def __init__(self, data, files):
        self.data = data
        self.files = files


class BaseParser(object):
    media_type = None

    def parse(self, stream, media_type=None, parser_context=None):
        raise NotImplementedError(".parse() must be overridden.")


class JSONParser(BaseParser):
    media_type = 'application/json'

    async def parse(self, request):
        data = await request.json
        return data


class FormParser(BaseParser):
    media_type = 'application/x-www-form-urlencoded'

    async def parse(self, request):
        return {k: [v for v in vs] if len(vs) > 1 else vs[-1]
                async for k, vs in request.form if vs}


class MultiPartParser(BaseParser):
    media_type = 'multipart/form-data'

    async def parse(self, request):
        return {k: [v for v in vs] if len(vs) > 1 else vs[-1]
                async for k, vs in request.form if vs}


PARSER_MEDIA_TYPE = (JSONParser(), MultiPartParser(), FormParser())
