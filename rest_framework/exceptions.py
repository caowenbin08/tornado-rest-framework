# -*- coding: utf-8 -*-
from tornado.web import HTTPError

from rest_framework.helpers import status
# from rest_framework.helpers.serializer_utils import ReturnDict

__author__ = 'caowenbin'


class UnicodeDecodeException(UnicodeDecodeError):
    def __init__(self, obj, *args):
        self.obj = obj
        UnicodeDecodeError.__init__(self, *args)

    def __str__(self):
        original = UnicodeDecodeError.__str__(self)
        return '%s. You passed in %r (%s)' % (original, self.obj, type(self.obj))


class ImproperlyConfigured(Exception):
    """配置文件不存在"""
    pass


def _get_error_details(data, default_code=None):
    """
    Descend into a nested data structure, forcing any
    lazy translation strings or strings into `ErrorDetail`.
    """
    from rest_framework.helpers.encoding import force_text
    if isinstance(data, list):
        ret = [
            _get_error_details(item, default_code) for item in data
        ]
        return ret
    elif isinstance(data, dict):
        ret = {
            key: _get_error_details(value, default_code)
            for key, value in data.items()
        }
        # if isinstance(data, ReturnDict):
        #     return ReturnDict(ret, serializer=data.serializer)
        return ret

    text = force_text(data)
    code = getattr(data, 'code', default_code)
    return ErrorDetail(text, code)


def _get_codes(detail):
    if isinstance(detail, list):
        return [_get_codes(item) for item in detail]
    elif isinstance(detail, dict):
        return {key: _get_codes(value) for key, value in detail.items()}
    return detail.code


def _get_full_details(detail):
    if isinstance(detail, list):
        return [_get_full_details(item) for item in detail]
    elif isinstance(detail, dict):
        return {key: _get_full_details(value) for key, value in detail.items()}
    return {
        'message': detail,
        'code': detail.code
    }


class ErrorDetail(str):
    code = None

    def __new__(cls, string, code=None):
        self = super(ErrorDetail, cls).__new__(cls, string)
        self.code = code
        return self


class ValidationError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = '非法请求参数'
    default_code = 'invalid'

    def __init__(self, detail, code=None):
        if detail is None:
            detail = self.default_detail
        if code is None:
            code = self.default_code

        if not isinstance(detail, (dict, list)):
            detail = [detail]

        self.detail = _get_error_details(detail, code)

    def __str__(self):
        return str(self.detail)

    def get_codes(self):
        """
        Return only the code part of the error details.

        Eg. {"name": ["required"]}
        """
        return _get_codes(self.detail)

    def get_full_details(self):
        """
        Return both the message & code parts of the error details.

        Eg. {"name": [{"message": "This field is required.", "code": "required"}]}
        """
        return _get_full_details(self.detail)


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


class APIException(HTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "服务器异常"
    default_code = 'error'

    def __init__(self, response_detail=None, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 log_message=None, *args, **kwargs):
        self.response_detail = response_detail
        super(APIException, self).__init__(status_code, log_message, *args, **kwargs)

