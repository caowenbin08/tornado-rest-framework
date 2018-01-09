# -*- coding: utf-8 -*-
from tornado.escape import json_encode

from rest_framework.utils.status import HTTP_200_OK

__author__ = 'caowenbin'


class Response(object):
    """
    响应处理
    """

    def __init__(self, data=None, status_code=HTTP_200_OK, template_name=None, headers=None,
                 content_type=None):
        """
        :param data: 响应数据
        :param status_code: http状态码
        :param template_name: 模板名
        :param headers: 响应头
        :param content_type: 响应格式
        """

        self._data = data
        self.status_code = status_code
        self.template_name = template_name
        self.content_type = "application/json" if content_type is None else content_type

        if headers:
            for name, value in iter(headers.items()):
                self[name] = value

    @property
    def data(self):
        return json_encode(self._data) if self.content_type == "application/json" else self._data
