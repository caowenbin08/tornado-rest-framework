# -*- coding: utf-8 -*-
"""
http 状态码
"""
from rest_framework.core.translation import lazy_translate as _


def is_informational(code):
    """
    是否消息（1字头）
    :param code:
    :return:
    """
    return 100 <= code <= 199


def is_success(code):
    """
    是否请求接收成功
    :param code:
    :return:
    """
    return 200 <= code <= 299


def is_redirect(code):
    """
    是否为重定向
    :param code:
    :return:
    """
    return 300 <= code <= 399


def is_client_error(code):
    """
    是否请求错误
    :param code:
    :return:
    """
    return 400 <= code <= 499


def is_server_error(code):
    """
    是否服务器错误（5、6字头）
    :param code:
    :return:
    """
    return 500 <= code <= 599


HTTP_CODES = {}


class HttpCodeDetail(int):
    code = None

    def __new__(cls, value, phrase, description=''):
        self = super(HttpCodeDetail, cls).__new__(cls, value)
        self.phrase = phrase
        self.description = description
        HTTP_CODES[value] = self
        return self


HTTP_200_OK = HttpCodeDetail(200, 'OK', _('Request fulfilled, document follows'))
HTTP_201_CREATED = HttpCodeDetail(201, 'Created', _('Document created, URL follows'))
HTTP_400_BAD_REQUEST = HttpCodeDetail(
    400, 'BadRequest', _('Bad request syntax or unsupported method'))
HTTP_401_UNAUTHORIZED = HttpCodeDetail(
    401, 'Unauthorized', _('No permission -- see authorization schemes'))
HTTP_403_FORBIDDEN = HttpCodeDetail(
    403, 'Forbidden', _('Request forbidden -- authorization will not help'))
HTTP_404_NOT_FOUND = HttpCodeDetail(
    404, 'NotFound', _('Nothing matches the given URI'))
HTTP_405_METHOD_NOT_ALLOWED = HttpCodeDetail(
    405, 'MethodNotAllowed', _('Specified method is invalid for this resource'))
HTTP_415_UNSUPPORTED_MEDIA_TYPE = HttpCodeDetail(
    415, 'UnsupportedMediaType', _('Entity body in unsupported format'))
HTTP_500_INTERNAL_SERVER_ERROR = HttpCodeDetail(
    500, 'InternalServerError', _('Server got itself in trouble'))
HTTP_502_BAD_GATEWAY = HttpCodeDetail(
    502, 'BadGateway', _('Invalid responses from another server/proxy'))
HTTP_503_SERVICE_UNAVAILABLE = HttpCodeDetail(
    503, 'ServiceUnavailable', _('The server cannot process the request due to a high load'))
HTTP_504_GATEWAY_TIMEOUT = HttpCodeDetail(
    504, 'GatewayTimeout', _('The gateway server did not receive a timely response'))
HTTP_505_HTTP_VERSION_NOT_SUPPORTED = HttpCodeDetail(
    505, 'HTTPVersionNotSupported', _('Cannot fulfill request'))

