# -*- coding: utf-8 -*-
import binascii
import hashlib
import hmac
import random
import struct
import time

from rest_framework.helpers.helpers.encoding import force_bytes

try:
    random = random.SystemRandom()
    using_sysrandom = True
except NotImplementedError:
    using_sysrandom = False


def get_random_string(length=12, allowed_chars=None):
    """
    生成对应长度的随机字符串
    :param length:
    :param allowed_chars:
    :return:
    """
    if allowed_chars is None:
        allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    if not using_sysrandom:
        random.seed(hashlib.sha256(("%s%s" % (random.getstate(), time.time())).encode('utf-8')).digest())

    return ''.join(random.choice(allowed_chars) for _ in range(length))


if hasattr(hmac, "compare_digest"):
    def constant_time_compare(val1, val2):
        return hmac.compare_digest(force_bytes(val1), force_bytes(val2))
else:
    def constant_time_compare(val1, val2):
        if len(val1) != len(val2):
            return False
        result = 0
        if isinstance(val1, bytes) and isinstance(val2, bytes):
            for x, y in zip(val1, val2):
                result |= x ^ y
        else:
            for x, y in zip(val1, val2):
                result |= ord(x) ^ ord(y)
        return result == 0


def _bin_to_long(x):
    """
    二进制转长整数
    """
    return int(binascii.hexlify(x), 16)


def _long_to_bin(x, hex_format_string):
    """
    长整数转二进制
    """
    return binascii.unhexlify((hex_format_string % x).encode('ascii'))


if hasattr(hashlib, "pbkdf2_hmac"):
    def pbkdf2(password, salt, iterations, dklen=0, digest=None):
        if digest is None:
            digest = hashlib.sha256

        if not dklen:
            dklen = None

        password = force_bytes(password)
        salt = force_bytes(salt)
        return hashlib.pbkdf2_hmac(
            digest().name, password, salt, iterations, dklen)
else:
    def pbkdf2(password, salt, iterations, dklen=0, digest=None):
        assert iterations > 0
        if not digest:
            digest = hashlib.sha256
        password = force_bytes(password)
        salt = force_bytes(salt)
        hlen = digest().digest_size
        if not dklen:
            dklen = hlen
        if dklen > (2 ** 32 - 1) * hlen:
            raise OverflowError('dklen too big')
        L = -(-dklen // hlen)
        r = dklen - (L - 1) * hlen

        hex_format_string = "%%0%ix" % (hlen * 2)

        inner, outer = digest(), digest()
        if len(password) > inner.block_size:
            password = digest(password).digest()
        password += b'\x00' * (inner.block_size - len(password))
        inner.update(password.translate(hmac.trans_36))
        outer.update(password.translate(hmac.trans_5C))

        def F(i):
            u = salt + struct.pack(b'>I', i)
            result = 0
            for j in range(int(iterations)):
                dig1, dig2 = inner.copy(), outer.copy()
                dig1.update(u)
                dig2.update(dig1.digest())
                u = dig2.digest()
                result ^= _bin_to_long(u)
            return _long_to_bin(result, hex_format_string)

        T = [F(x) for x in range(1, L)]
        return b''.join(T) + F(L)[:r]
