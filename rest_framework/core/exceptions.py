# -*- coding: utf-8 -*-
import json
from collections import UserList

from tornado.escape import xhtml_escape

from rest_framework.conf import settings
from rest_framework.utils import status
from rest_framework.core.translation import gettext as _
from rest_framework.utils.transcoder import force_text

__author__ = 'caowenbin'


class TornadoRuntimeWarning(RuntimeWarning):
    pass


class CompressorError(Exception):
    """
    压缩异常
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


class ValidationError(Exception):
    """An error while validating data."""
    def __init__(self, message, code=None, params=None):
        """
        The `message` argument can be a single error, a list of errors, or a
        dictionary that maps field names to lists of errors. What we define as
        an "error" can be either a simple string or an instance of
        ValidationError with its message attribute set, and what we define as
        list or dictionary can be an actual `list` or `dict` or an instance
        of ValidationError with its `error_list` or `error_dict` attribute set.
        """

        super(ValidationError, self).__init__(message, code, params)

        if isinstance(message, ValidationError):
            if hasattr(message, 'error_dict'):
                message = message.error_dict
            elif not hasattr(message, 'message'):
                message = message.error_list
            else:
                message, code, params = message.message, message.code, message.params

        if isinstance(message, dict):
            self.error_dict = {}
            for field, messages in message.items():
                if not isinstance(messages, ValidationError):
                    messages = ValidationError(messages)
                self.error_dict[field] = messages.error_list

        elif isinstance(message, list):
            self.error_list = []
            for message in message:
                # Normalize plain strings to instances of ValidationError.
                if not isinstance(message, ValidationError):
                    message = ValidationError(message)
                if hasattr(message, 'error_dict'):
                    self.error_list.extend(sum(message.error_dict.values(), []))
                else:
                    self.error_list.extend(message.error_list)

        else:
            self.message = message
            self.code = code
            self.params = params
            self.error_list = [self]

    @property
    def message_dict(self):
        getattr(self, 'error_dict')

        return dict(self)

    @property
    def messages(self):
        if hasattr(self, 'error_dict'):
            return sum(dict(self).values(), [])
        return list(self)

    def update_error_dict(self, error_dict):
        if hasattr(self, 'error_dict'):
            for field, error_list in self.error_dict.items():
                error_dict.setdefault(field, []).extend(error_list)
        else:
            error_dict.setdefault(settings.NON_FIELD_ERRORS, []).extend(self.error_list)
        return error_dict

    def __iter__(self):
        if hasattr(self, 'error_dict'):
            for field, errors in self.error_dict.items():
                yield field, list(ValidationError(errors))
        else:
            for error in self.error_list:
                message = error.message
                if error.params:
                    message %= error.params
                yield force_text(message)

    def __str__(self):
        if hasattr(self, 'error_dict'):
            return repr(dict(self))
        return repr(list(self))

    def __repr__(self):
        return 'ValidationError(%s)' % self


class ErrorDict(dict):
    """
    A collection of errors that knows how to display itself in various formats.

    The dictionary keys are the field names, and the values are the errors.
    """
    def as_data(self):
        return {f: list(e.as_data()[0])[0] for f, e in self.items()}

    def as_json(self, escape_html=False):
        return {f: e.get_json_data(escape_html) for f, e in self.items()}


class ErrorList(UserList, list):
    """
    A collection of errors that knows how to display itself in various formats.
    """
    def __init__(self, initlist=None):
        super(ErrorList, self).__init__(initlist)

    def as_data(self):
        return ValidationError(self.data).error_list

    def get_json_data(self, escape_html=False):
        errors = []
        for error in self.as_data():
            message = list(error)[0]
            errors.append({
                'message': xhtml_escape(message) if escape_html else message,
                'code': error.code or '',
            })
        return errors

    def as_json(self, escape_html=False):
        return json.dumps(self.get_json_data(escape_html))

    def __repr__(self):
        return repr(list(self))

    def __contains__(self, item):
        return item in list(self)

    def __eq__(self, other):
        return list(self) == other

    def __getitem__(self, i):
        error = self.data[i]
        if isinstance(error, ValidationError):
            return list(error)[0]
        return force_text(error)

    def __reduce_ex__(self, *args, **kwargs):
        info = super(UserList, self).__reduce_ex__(*args, **kwargs)
        return info[:3] + (None, None)


class FieldError(Exception):
    """Some kind of problem with a model field."""
    pass


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


class ErrorDetail(str):
    code = None

    def __new__(cls, string, code=None):
        self = super(ErrorDetail, cls).__new__(cls, string)
        self.code = code
        return self


class APIException(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _('A server error occurred')
    default_code = 'error'

    def __init__(self, detail=None, code=None, status_code=None):
        if detail is None:
            detail = self.default_detail

        if code is None:
            self.code = self.default_code

        if status_code is not None:
            self.status_code = status_code

        self.detail = self.get_error_details(detail)

    def get_error_details(self, detail):
        if isinstance(detail, list):
            ret = [self.get_error_details(item) for item in detail]
            return ret
        elif isinstance(detail, dict):
            ret = {key: self.get_error_details(value) for key, value in detail.items()}
            return ret

        text = force_text(detail)
        code = getattr(detail, 'code', self.code)
        return ErrorDetail(text, code)

    def __str__(self):
        return str(self.detail)


class ParseError(APIException):
    """
    解析异常
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Malformed request')
    default_code = 'parse_error'


class PaginationError(APIException):
    """
    分页异常
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid page')
    default_code = 'page_error'


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
