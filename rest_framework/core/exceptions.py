from rest_framework.utils import status
from rest_framework.core.translation import lazy_translate as _
from rest_framework.utils.transcoder import force_text


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


class FieldError(Exception):
    """字段异常"""
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


class SkipFilterError(Exception):
    """
    可跳过的过滤字段异常
    """
    pass


class HTTPError(Exception):
    def __init__(self, status_code=500):
        self.status_code = status_code


def _get_error_details(data, default_code=None):
    """
    Descend into a nested data structure, forcing any
    lazy translation strings or strings into `ErrorDetail`.
    """

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


def get_full_details(detail):
    if isinstance(detail, list):
        return [get_full_details(item) for item in detail]
    elif isinstance(detail, dict):
        return {key: get_full_details(value) for key, value in detail.items()}
    return {
        'message': detail,
        'code': detail.code
    }


class ErrorDetail(str):
    """
    A string-like object that can additionally
    """
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
        self.code = self.default_code if code is None else code
        if status_code is not None:
            self.status_code = status_code

        self.detail = _get_error_details(detail, self.code)

    def __str__(self):
        return "%s" % self.detail

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
        return get_full_details(self.detail)


class ValidationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid input.')
    default_code = 'invalid'

    def __init__(self, detail=None, code=None, params=None, field=None):
        if detail is None:
            detail = self.default_detail
        self.code = self.default_code if code is None else code
        self.field = field
        if params is not None:
            detail %= params

        self.detail = _get_error_details(detail, self.code)

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


class RouteConfigurationError(Exception):
    pass


class ReverseNotFound(Exception):
    pass


class NotFound(Exception):
    pass


class MethodNotAllowed(Exception):
    pass

