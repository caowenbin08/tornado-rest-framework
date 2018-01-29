# -*- coding: utf-8 -*-
import datetime
import binascii
import string
from decimal import Decimal

from rest_framework.core import exceptions

__author__ = 'caowenbin'


_PROTECTED_TYPES = (int, type(None), float, Decimal, datetime.datetime, datetime.date, datetime.time)


def is_protected_type(obj):
    """
    是否为保护类型
    :param obj:
    :return:
    """

    return isinstance(obj, _PROTECTED_TYPES)


def force_text(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    转换为文本类型
    :param s:
    :param encoding:
    :param strings_only: 是否启用保护类型，默认否
    :param errors:
    :return:
    """

    if issubclass(type(s), str):
        return s

    if strings_only and is_protected_type(s):
        return s

    try:
        if not issubclass(type(s), str):
            s = str(s, encoding, errors) if isinstance(s, bytes) else str(s)
        else:
            s = s.decode(encoding, errors)
    except UnicodeDecodeError as e:
        if not isinstance(s, Exception):
            raise exceptions.UnicodeDecodeException(s, *e.args)
        else:
            s = ' '.join(force_text(arg, encoding, strings_only, errors) for arg in s)
    return s


def force_bytes(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    字符串转二进制字节
    :param s:
    :param encoding:
    :param strings_only:
    :param errors:
    :return:
    """
    if isinstance(s, bytes):
        if encoding in ("utf-8", "utf8"):
            return s
        else:
            return s.decode('utf-8', errors).encode(encoding, errors)

    if strings_only and is_protected_type(s):
        return s

    if isinstance(s, memoryview):
        return bytes(s)

    if not isinstance(s, str):
        try:
            return str(s).encode(encoding)
        except UnicodeEncodeError:
            if isinstance(s, Exception):
                return b' '.join(force_bytes(arg, encoding, strings_only, errors) for arg in s)
            return str(s).encode(encoding, errors)
    else:
        return s.encode(encoding, errors)


def str2hex(value, charset="utf8"):
    """
    字符串转16进制
    :param value:
    :param charset:
    :return:
    """
    return binascii.b2a_hex(force_bytes(value, charset))


def hex2str(value, charset="utf8"):
    """
    16进制转字符串
    :param value:
    :param charset:
    :return:
    """
    return binascii.a2b_hex(value)


def base36_to_int(s):
    """
    Converts a base 36 string to an ``int``. Raises ``ValueError` if the
    input won't fit into an int.
    """
    # To prevent overconsumption of server resources, reject any
    # base36 string that is longer than 13 base36 digits (13 digits
    # is sufficient to base36-encode any 64-bit integer)
    if len(s) > 13:
        raise ValueError("Base36 input too large")
    value = int(s, 36)

    return value


def int_to_base36(i):
    """
    Converts an integer to a base36 string
    """
    char_set = '0123456789abcdefghijklmnopqrstuvwxyz'
    if i < 0:
        raise ValueError("Negative base36 conversion input.")

    if i < 36:
        return char_set[i]
    b36 = ''
    while i != 0:
        i, n = divmod(i, 36)
        b36 = char_set[n] + b36
    return b36

