# -*- coding: utf-8 -*-
"""
安全加密码工具
"""
import hmac
import socket
import base64
import struct
import hashlib
import string
import binascii

from rest_framework.core.exceptions import IllegalAesKeyError
from rest_framework.utils.transcoder import force_bytes, force_text, str2hex, hex2str
from rest_framework.utils.functional import get_random_string

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


class ParamError(Exception):
    """
    参数非法
    """
    pass


class ValidateAppIdError(Exception):
    """
    非法应用标识
    """
    pass


class PKCS7Encoder(object):
    """
    提供基于PKCS7算法的加解密接口
    """

    block_size = 32

    @classmethod
    def encode(cls, text):
        """
        对需要加密的明文进行填充补位
        :param text: 需要进行填充补位操作的明文
        :return: 补齐明文字符串
        """
        text_length = len(text)
        # 计算需要填充的位数
        amount_to_pad = cls.block_size - (text_length % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
        # 获得补位所用的字符
        pad = chr(amount_to_pad)
        return text + pad * amount_to_pad

    @classmethod
    def decode(cls, decrypted):
        """
        删除解密后明文的补位字符
        :param decrypted: 解密后的明文
        :return: 删除补位字符后的明文
        """
        pad = ord(decrypted[-1])
        if pad < 1 or pad > cls.block_size:
            pad = 0
        return decrypted[:-pad]

pkcs7 = PKCS7Encoder


class MsgCrypt(object):
    """
    消息的加解密接口
    """

    def __init__(self, encoding_aec_key):
        """
        :param encoding_aec_key:加密所用的秘钥
        """
        from Crypto.Cipher import AES
        self.__gen_key(encoding_aec_key)
        # 设置加解密模式为AES的CBC模式
        self.mode = AES.MODE_CBC

    def __gen_key(self, encoding_aec_key):
        if not isinstance(encoding_aec_key, (bytes, str)):
            raise ValueError("encoding_aec_key type must bytes or str")

        if isinstance(encoding_aec_key, bytes):
            encoding_aec_key += b"=="
        else:
            encoding_aec_key += "=="

        try:
            self.key = base64.b64decode(encoding_aec_key)
        except:
            raise IllegalAesKeyError("EncodingAESKey Invalid")

    def encrypt(self, text):
        """
        对明文进行加密
        :param text: 需要加密的明文
        :return:
        """
        from Crypto.Cipher import AES
        # 16位随机字符串添加到明文开头
        text = get_random_string(length=16) + force_text(struct.pack("I", socket.htonl(len(text)))) + text
        # 使用自定义的填充方式对明文进行补位填充
        text = pkcs7.encode(text)
        # 加密
        allowed_chars = string.digits + string.ascii_letters + string.punctuation
        iv = get_random_string(length=16, allowed_chars=allowed_chars)
        cryptor = AES.new(self.key, self.mode, iv)
        cipher_text = cryptor.encrypt(text)
        # 加密后的字符串转化为16进制字符串
        cipher_text = force_bytes(iv) + cipher_text
        return str2hex(cipher_text)

    def decrypt(self, text):
        """
        对解密后的明文进行补位删除
        :param text: 密文
        :return: 删除填充补位后的明文
        """
        from Crypto.Cipher import AES

        cipher_text = hex2str(text)
        iv = cipher_text[:16]
        cryptor = AES.new(self.key, self.mode, iv)
        # 解密并去除16位随机字符串
        plain_text = force_text(cryptor.decrypt(cipher_text[16:])[16:])
        content = pkcs7.decode(plain_text)
        # pad = ord(plain_text[-1])
        # # 去除16位随机字符串
        # content = plain_text[16:-pad]
        msg_len = socket.ntohl(struct.unpack("I", force_bytes(content[:4]))[0])
        msg_content = content[4: msg_len+4]

        return msg_content
