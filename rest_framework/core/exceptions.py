# -*- coding: utf-8 -*-
from collections import OrderedDict
from rest_framework.utils import status
from rest_framework.core.translation import lazy_gettext as _
from rest_framework.utils.transcoder import force_text

__author__ = 'caowenbin'


class CommandError(Exception):
    """
    命令异常
    """
    pass


class UnicodeDecodeException(UnicodeDecodeError):
    def __init__(self, obj, *args):
        self.obj = obj
        UnicodeDecodeError.__init__(self, *args)

    def __str__(self):
        original = UnicodeDecodeError.__str__(self)
        return '%s. You passed in %r (%s)' % (original, self.obj, type(self.obj))


class ImproperlyConfigured(Exception):
    """配置异常"""
    pass


class ErrorDetail(str):
    code = None

    def __new__(cls, text_value, code=None):
        self = super(ErrorDetail, cls).__new__(cls, text_value)
        self.code = code
        return self


def gen_error_detail(data, default_code=None):
    if isinstance(data, dict):
        ret = {k: gen_error_detail(v, default_code) for k, v in data.items()}
        return ret

    text = force_text(data)
    code = getattr(data, 'code', default_code)
    return ErrorDetail(text, code)


class ValidationError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid input')
    default_code = 'invalid'

    def __init__(self, detail, code=None):
        if detail is None:
            detail = self.default_detail

        if code is None:
            code = self.default_code

        self.detail = gen_error_detail(detail, code)

    def __str__(self):
        return str(self.detail)


class FieldDoesNotExist(Exception):
    """
    字段在model不存在
    """
    pass


class SkipFieldError(Exception):
    """
    可跳过的字段异常
    """
    pass


class ObjectDoesNotExist(Exception):
    """The requested object does not exist"""
    silent_variable_failure = True


class ApiException(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _('A server error occurred')
    default_code = 'error'

    def __init__(self, detail, code=None, status_code=None):
        if detail is None:
            detail = self.default_detail

        if code is None:
            code = self.default_code

        if status_code:
            self.status_code = status_code

        self.detail = gen_error_detail(detail, code)

    def __str__(self):
        return str(self.detail)


class ParseError(ApiException):
    """
    解析异常
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Malformed request')
    default_code = 'parse_error'


def translate_validation(error_dict):
    """
    字典结构的异常信息转化为ErrorDetail格式放在ValidationError中进行返回
    :param error_dict:
    :return:
    """

    exc = OrderedDict(
        (key, [ErrorDetail(e.message, code=e.code) for e in error_list])
        for key, error_list in error_dict.as_data().items()
    )

    return ValidationError(exc)


class IllegalAesKeyError(Exception):
    """
    不合法的AESKey
    """
    pass


class EncryptAESError(Exception):
    """
    AES加密失败
    """
    pass


class DecryptAESError(Exception):
    """
    AES解密失败
    """
    pass


class EncodeBase64Error(Exception):
    """
    Base64编码失败
    """
    pass


class DecodeBase64Error(Exception):
    """
    Base64解码失败
    """
    pass


class EncodeHexError(Exception):
    """
    16进制编码失败
    """
    pass


class DecodeHexError(Exception):
    """
    16进制解码失败
    """
    pass
