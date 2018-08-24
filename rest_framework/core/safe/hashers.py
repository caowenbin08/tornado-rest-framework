# -*- coding: utf-8 -*-
"""
关于处理密码加密的处理
"""
import time
import base64
import binascii
import functools
import importlib
import hashlib
import warnings
from collections import OrderedDict

from rest_framework.conf import settings
from rest_framework.core.exceptions import ImproperlyConfigured
from rest_framework.core.safe.crypto import pbkdf2, constant_time_compare
from rest_framework.utils.transcoder import force_bytes, force_text
from rest_framework.utils.functional import import_object, get_random_string

UNUSABLE_PASSWORD_PREFIX = '!'
UNUSABLE_PASSWORD_SUFFIX_LENGTH = 40


def is_password_usable(encoded_password):
    if encoded_password is None or encoded_password.startswith(UNUSABLE_PASSWORD_PREFIX):
        return False
    try:
        identify_hasher(encoded_password)
    except ValueError:
        return False
    return True


def check_password(password, encoded_password, restpwd=None, preferred='default'):
    """
    检查密码正确性
    :param password:
    :param encoded_password:
    :param restpwd: 如果密码加密格式不一样，则根据新的协议重置加密密码
    :param preferred:
    :return:
    """
    s = time.time()
    if password is None or not is_password_usable(encoded_password):
        return False

    preferred = get_hasher(preferred)
    hasher = identify_hasher(encoded_password)
    hasher_changed = hasher.algorithm != preferred.algorithm
    must_update = hasher_changed or preferred.must_update(encoded_password)
    is_correct = hasher.verify(password, encoded_password)
    # if not is_correct and not hasher_changed and must_update:
    #     hasher.harden_runtime(password, encoded_password)

    if restpwd and is_correct and must_update:
        restpwd(password)

    return is_correct


def make_password(password, salt=None, hasher='default'):
    """
    密码加密
    :param password:
    :param salt:
    :param hasher:
    :return:
    """

    if password is None:
        return UNUSABLE_PASSWORD_PREFIX + get_random_string(UNUSABLE_PASSWORD_SUFFIX_LENGTH)

    hasher = get_hasher(hasher)

    if not salt:
        salt = hasher.salt()

    return hasher.encode(password, salt)


@functools.lru_cache()
def get_hashers():
    hashers = []
    for hasher_path in settings.PASSWORD_HASHERS:
        hasher = import_object(hasher_path)()
        if not getattr(hasher, 'algorithm'):
            raise ImproperlyConfigured("hasher doesn't specify an algorithm name: %s" % hasher_path)
        hashers.append(hasher)
    return hashers


@functools.lru_cache()
def get_hashers_by_algorithm():
    return {hasher.algorithm: hasher for hasher in get_hashers()}


def get_hasher(algorithm='default'):
    if hasattr(algorithm, 'algorithm'):
        return algorithm

    elif algorithm == 'default':
        return get_hashers()[0]

    else:
        hashers = get_hashers_by_algorithm()
        try:
            return hashers[algorithm]
        except KeyError:
            raise ValueError("Unknown password hash_valing algorithm '%s'. "
                             "Did you specify it in the PASSWORD_HASHERS "
                             "setting?" % algorithm)


def identify_hasher(encoded_password):
    pwd_len = len(encoded_password)
    if (pwd_len == 32 and '$' not in encoded_password) or (pwd_len == 37 and encoded_password.startswith('md5$$')):
        algorithm = 'unsalted_md5'

    elif pwd_len == 46 and encoded_password.startswith('sha1$$'):
        algorithm = 'unsalted_sha1'
    else:
        algorithm = encoded_password.split('$', 1)[0]
    return get_hasher(algorithm)


def mask_password(encoded_password, show=6, char="*"):
    """
    掩饰密码hash显示
    :param encoded_password:
    :param show:
    :param char:
    :return:
    """
    masked = encoded_password[:show]
    masked += char * len(encoded_password[show:])
    return masked


class BasePasswordHasher(object):
    """
    密码加密抽象类
    子类必须覆盖verify()、 encode()、 safe_summary()
    """
    algorithm = None
    library = None

    def _load_library(self):
        if self.library is not None:
            if isinstance(self.library, (tuple, list)):
                name, mod_path = self.library
            else:
                mod_path = self.library
            try:
                module = importlib.import_module(mod_path)
            except ImportError as e:
                raise ValueError("Couldn't load %r algorithm library: %s" % (self.__class__.__name__, e))
            return module
        raise ValueError("hasher %r doesn't specify a library attribute" % self.__class__.__name__)

    def salt(self):
        """
        随机盐
        """
        return get_random_string()

    def verify(self, password, encoded_password):
        """
        检查密码正确性
        """
        raise NotImplementedError('subclasses of BasePasswordHasher must provide a verify() method')

    def encode(self, password, salt):
        """
        加密
        """
        raise NotImplementedError('subclasses of BasePasswordHasher must provide an encode() method')

    def safe_summary(self, encoded_password):
        """
        返回安全值的总结
        结果是一本字典，将用在密码域
        必须显示来构建一个安全的密码表示
        :param encoded_password:
        :return:
        """
        raise NotImplementedError('subclasses of BasePasswordHasher must provide a safe_summary() method')

    def must_update(self, encoded_password):
        return False

    def harden_runtime(self, password, encoded_password):
        warnings.warn('subclasses of BasePasswordHasher should provide a harden_runtime() method')


class PBKDF2PasswordHasher(BasePasswordHasher):
    """
    安全的密码hash_valing使用PBKDF2算法（推荐）
    配置为使用PBKDF2 HMAC SHA256。
    其结果是一个64字节的二进制字符串。迭代可以改变
    安全但你必须重命名算法如果你改变SHA256。
    """
    algorithm = "pbkdf2_sha256"
    iterations = 100000
    digest = hashlib.sha256

    def encode(self, password, salt, iterations=None):
        assert password is not None
        assert salt and '$' not in salt
        if not iterations:
            iterations = self.iterations
        hash_val = pbkdf2(password, salt, iterations, digest=self.digest)
        hash_val = base64.b64encode(hash_val).decode('ascii').strip()
        return "%s$%d$%s$%s" % (self.algorithm, iterations, salt, hash_val)

    def verify(self, password, encoded_password):
        algorithm, iterations, salt, hash_val = encoded_password.split('$', 3)
        assert algorithm == self.algorithm
        encoded_password_2 = self.encode(password, salt, int(iterations))
        return constant_time_compare(encoded_password, encoded_password_2)

    def safe_summary(self, encoded_password):
        algorithm, iterations, salt, hash_val = encoded_password.split('$', 3)
        assert algorithm == self.algorithm
        return OrderedDict([
            ('algorithm', algorithm),
            ('iterations', iterations),
            ('salt', mask_password(salt)),
            ('hash', mask_password(hash_val)),
        ])

    def must_update(self, encoded_password):
        algorithm, iterations, salt, hash_val = encoded_password.split('$', 3)
        return int(iterations) != self.iterations

    def harden_runtime(self, password, encoded_password):
        algorithm, iterations, salt, hash_val = encoded_password.split('$', 3)
        extra_iterations = self.iterations - int(iterations)
        if extra_iterations > 0:
            self.encode(password, salt, extra_iterations)


class PBKDF2SHA1PasswordHasher(PBKDF2PasswordHasher):
    """
    交替使用PBKDF2和SHA1，默认频率通过PKCS 5推荐。这与其他兼容。
    实现PBKDF2，如OpenSSL的pkcs5_pbkdf2_hmac_sha1()。
    """
    algorithm = "pbkdf2_sha1"
    digest = hashlib.sha1


class Argon2PasswordHasher(BasePasswordHasher):
    """
    安全的密码哈希算法使用argon2。
    这是密码散列大赛2013-2015年冠军
    （https://password-hash_valing.net）。它要求argon2 CFFI库
    取决于本机C代码，可能会导致可移植性问题。
    """
    algorithm = 'argon2'
    library = 'argon2'

    time_cost = 2
    memory_cost = 512
    parallelism = 2

    def encode(self, password, salt):
        argon2 = self._load_library()
        data = argon2.low_level.hash_val_secret(
            force_bytes(password),
            force_bytes(salt),
            time_cost=self.time_cost,
            memory_cost=self.memory_cost,
            parallelism=self.parallelism,
            hash_val_len=argon2.DEFAULT_hash_val_LENGTH,
            type=argon2.low_level.Type.I,
        )
        return self.algorithm + data.decode('ascii')

    def verify(self, password, encoded_password):
        argon2 = self._load_library()
        algorithm, rest = encoded_password.split('$', 1)
        assert algorithm == self.algorithm
        try:
            return argon2.low_level.verify_secret(
                force_bytes('$' + rest),
                force_bytes(password),
                type=argon2.low_level.Type.I,
            )
        except argon2.exceptions.VerificationError:
            return False

    def safe_summary(self, encoded_password):
        (algorithm, variety, version, time_cost, memory_cost, parallelism,
            salt, data) = self._decode(encoded_password)
        assert algorithm == self.algorithm
        return OrderedDict([
            ('algorithm', algorithm),
            ('variety', variety),
            ('version', version),
            ('memory cost', memory_cost),
            ('time cost', time_cost),
            ('parallelism', parallelism),
            ('salt', mask_password(salt)),
            ('hash', mask_password(data)),
        ])

    def must_update(self, encoded_password):
        (algorithm, variety, version, time_cost, memory_cost, parallelism,
            salt, data) = self._decode(encoded_password)
        assert algorithm == self.algorithm
        argon2 = self._load_library()
        return (
            argon2.low_level.ARGON2_VERSION != version or
            self.time_cost != time_cost or
            self.memory_cost != memory_cost or
            self.parallelism != parallelism
        )

    def harden_runtime(self, password, encoded_password):
        pass

    @staticmethod
    def _decode(encoded_password):
        bits = encoded_password.split('$')
        if len(bits) == 5:
            # Argon2 < 1.3
            algorithm, variety, raw_params, salt, data = bits
            version = 0x10
        else:
            assert len(bits) == 6
            algorithm, variety, raw_version, raw_params, salt, data = bits
            assert raw_version.startswith('v=')
            version = int(raw_version[len('v='):])
        params = dict(bit.split('=', 1) for bit in raw_params.split(','))
        assert len(params) == 3 and all(x in params for x in ('t', 'm', 'p'))
        time_cost = int(params['t'])
        memory_cost = int(params['m'])
        parallelism = int(params['p'])
        return (
            algorithm, variety, version, time_cost, memory_cost, parallelism,
            salt, data,
        )


class BCryptSHA256PasswordHasher(BasePasswordHasher):
    """
    安全的密码哈希算法使用BCrypt（推荐）这被许多人认为是最安全的算法，但你必须先安装BCrypt的库包。
    请注意此库依赖于本机C代码，可能会导致可移植性问题.
    """
    algorithm = "bcrypt_sha256"
    digest = hashlib.sha256
    library = ("bcrypt", "bcrypt")
    rounds = 12

    def salt(self):
        bcrypt = self._load_library()
        return bcrypt.gensalt(self.rounds)

    def encode(self, password, salt):
        bcrypt = self._load_library()
        if self.digest is not None:
            password = binascii.hexlify(self.digest(force_bytes(password)).digest())
        else:
            password = force_bytes(password)

        data = bcrypt.hash_valpw(password, salt)
        return "%s$%s" % (self.algorithm, force_text(data))

    def verify(self, password, encoded_password):
        algorithm, data = encoded_password.split('$', 1)
        assert algorithm == self.algorithm
        encoded_password_2 = self.encode(password, force_bytes(data))
        return constant_time_compare(encoded_password, encoded_password_2)

    def safe_summary(self, encoded_password):
        algorithm, empty, algostr, work_factor, data = encoded_password.split('$', 4)
        assert algorithm == self.algorithm
        salt, checksum = data[:22], data[22:]
        return OrderedDict([
            ('algorithm', algorithm),
            ('work factor', work_factor),
            ('salt', mask_password(salt)),
            ('checksum', mask_password(checksum)),
        ])

    def must_update(self, encoded_password):
        algorithm, empty, algostr, rounds, data = encoded_password.split('$', 4)
        return int(rounds) != self.rounds

    def harden_runtime(self, password, encoded_password):
        _, data = encoded_password.split('$', 1)
        salt = data[:29]  # BCrypt的salt的长度
        rounds = data.split('$')[2]
        # 工作因子是对数，增加一倍的负载
        diff = 2**(self.rounds - int(rounds)) - 1
        while diff > 0:
            self.encode(password, force_bytes(salt))
            diff -= 1


class BCryptPasswordHasher(BCryptSHA256PasswordHasher):
    algorithm = "bcrypt"
    digest = None


class SHA1PasswordHasher(BasePasswordHasher):

    algorithm = "sha1"

    def encode(self, password, salt):
        assert password is not None
        assert salt and '$' not in salt
        hash_val = hashlib.sha1(force_bytes(salt + password)).hexdigest()
        return "%s$%s$%s" % (self.algorithm, salt, hash_val)

    def verify(self, password, encoded_password):
        algorithm, salt, hash_val = encoded_password.split('$', 2)
        assert algorithm == self.algorithm
        encoded_password_2 = self.encode(password, salt)
        return constant_time_compare(encoded_password, encoded_password_2)

    def safe_summary(self, encoded_password):
        algorithm, salt, hash_val = encoded_password.split('$', 2)
        assert algorithm == self.algorithm
        return OrderedDict([
            ('algorithm', algorithm),
            ('salt', mask_password(salt, show=2)),
            ('hash', mask_password(hash_val)),
        ])

    def harden_runtime(self, password, encoded_password):
        pass


class MD5PasswordHasher(BasePasswordHasher):

    algorithm = "md5"

    def encode(self, password, salt):
        assert password is not None
        assert salt and '$' not in salt
        hash_val = hashlib.md5(force_bytes(salt + password)).hexdigest()
        return "%s$%s$%s" % (self.algorithm, salt, hash_val)

    def verify(self, password, encoded_password):
        algorithm, salt, hash_val = encoded_password.split('$', 2)
        assert algorithm == self.algorithm
        encoded_password_2 = self.encode(password, salt)
        return constant_time_compare(encoded_password, encoded_password_2)

    def safe_summary(self, encoded_password):
        algorithm, salt, hash_val = encoded_password.split('$', 2)
        assert algorithm == self.algorithm
        return OrderedDict([
            ('algorithm', algorithm),
            ('salt', mask_password(salt, show=2)),
            ('hash', mask_password(hash_val)),
        ])

    def harden_runtime(self, password, encoded_password):
        pass


class UnsaltedSHA1PasswordHasher(BasePasswordHasher):

    algorithm = "unsalted_sha1"

    def salt(self):
        return ''

    def encode(self, password, salt):
        assert salt == ''
        hash_val = hashlib.sha1(force_bytes(password)).hexdigest()
        return 'sha1$$%s' % hash_val

    def verify(self, password, encoded_password):
        encoded_password_2 = self.encode(password, '')
        return constant_time_compare(encoded_password, encoded_password_2)

    def safe_summary(self, encoded_password):
        assert encoded_password.startswith('sha1$$')
        hash_val = encoded_password[6:]
        return OrderedDict([
            ('algorithm', self.algorithm),
            ('hash', mask_password(hash_val)),
        ])

    def harden_runtime(self, password, encoded_password):
        pass


class UnsaltedMD5PasswordHasher(BasePasswordHasher):

    algorithm = "unsalted_md5"

    def salt(self):
        return ''

    def encode(self, password, salt):
        assert salt == ''
        return hashlib.md5(force_bytes(password)).hexdigest()

    def verify(self, password, encoded_password):
        if len(encoded_password) == 37 and encoded_password.startswith('md5$$'):
            encoded_password = encoded_password[5:]
        encoded_password_2 = self.encode(password, '')
        return constant_time_compare(encoded_password, encoded_password_2)

    def safe_summary(self, encoded_password):
        return OrderedDict([
            ('algorithm', self.algorithm),
            ('hash', mask_password(encoded_password, show=3)),
        ])

    def harden_runtime(self, password, encoded_password):
        pass


class CryptPasswordHasher(BasePasswordHasher):

    algorithm = "crypt"
    library = "crypt"

    def salt(self):
        return get_random_string(2)

    def encode(self, password, salt):
        crypt = self._load_library()
        assert len(salt) == 2
        data = crypt.crypt(force_text(password), salt)
        assert data is not None  # A platform like OpenBSD with a dummy crypt module.
        # we don't need to store the salt, but Django used to do this
        return "%s$%s$%s" % (self.algorithm, '', data)

    def verify(self, password, encoded_password):
        crypt = self._load_library()
        algorithm, salt, data = encoded_password.split('$', 2)
        assert algorithm == self.algorithm
        return constant_time_compare(data, crypt.crypt(force_text(password), data))

    def safe_summary(self, encoded_password):
        algorithm, salt, data = encoded_password.split('$', 2)
        assert algorithm == self.algorithm
        return OrderedDict([
            ('algorithm', algorithm),
            ('salt', salt),
            ('hash', mask_password(data, show=3)),
        ])

    def harden_runtime(self, password, encoded_password):
        pass
