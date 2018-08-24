# -*- coding: utf-8 -*-
import datetime
import binascii
from decimal import Decimal


_PROTECTED_TYPES = (int, type(None), float, Decimal, datetime.datetime, datetime.date, datetime.time)


def is_protected_type(obj):

    return isinstance(obj, _PROTECTED_TYPES)


def force_text(s, encoding='utf-8', strings_only=False, errors='strict'):

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
        s = ' '.join(force_text(arg, encoding, strings_only, errors) for arg in s)

    return s


def force_bytes(s, encoding='utf-8', strings_only=False, errors='strict'):

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
    return binascii.b2a_hex(force_bytes(value, charset))


def hex2str(value):
    return binascii.a2b_hex(value)


def base36_to_int(s):

    if len(s) > 13:
        raise ValueError("Base36 input too large")
    value = int(s, 36)

    return value


def int_to_base36(i):
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

