# -*- coding: utf-8 -*-
from tornado import escape

from rest_framework.helpers.status import HTTP_200_OK

__author__ = 'caowenbin'


class Response(object):
    """
    响应处理
    """

    def __init__(self, data=None, status_code=HTTP_200_OK, template_name=None, headers=None, content_type=None):
        """

        :param data: 响应数据
        :param status_code: http状态码
        :param template_name: 模板名
        :param headers: 响应头
        :param content_type: 响应格式
        """

        self.__data = data
        self.status_code = status_code
        self.template_name = template_name
        self.content_type = content_type if content_type else "application/json"

        if headers:
            for name, value in iter(headers.items()):
                self[name] = value

    @property
    def data(self):
        return escape.json_encode(self.__data) if self.content_type == "application/json" else self.__data
