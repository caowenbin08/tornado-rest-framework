# -*- coding: utf-8 -*-
import datetime
from decimal import Decimal

from rest_framework import exceptions

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
        if encoding == 'utf-8':
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
                # An Exception subclass containing non-ASCII data that doesn't
                # know how to print itself properly. We shouldn't raise a
                # further exception.
                return b' '.join(force_bytes(arg, encoding, strings_only, errors) for arg in s)
            return str(s).encode(encoding, errors)
    else:
        return s.encode(encoding, errors)
