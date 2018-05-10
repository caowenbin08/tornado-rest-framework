# -*- coding: utf-8 -*-
import base64
import datetime
import functools
import hashlib
import inspect
import logging
import asyncio
import string
from importlib import import_module

from rest_framework.core.singnals import app_closed
from rest_framework.core.exceptions import CompressorError
from rest_framework.utils.transcoder import force_bytes

DEFAULT_TIMEOUT = object()
DEFAULT_SERIALIZER = 'rest_framework.core.serializers.null'
DEFAULT_COMPRESSOR = 'rest_framework.core.compressors.null'
logger = logging.getLogger(__name__)

valid_chars = set(string.ascii_letters + string.digits + '_.')
delchars = ''.join(c for c in map(chr, range(256)) if c not in valid_chars)
null_control = (dict((k, None) for k in delchars),)


class BaseCache:
    def __init__(self, server, params: dict):
        self._server = server
        self.key_prefix = force_bytes(params.get('KEY_PREFIX', b''))
        self.default_timeout = params.get("DEFAULT_TIMEOUT", 300)
        self._options = params.get('OPTIONS', {})
        self._serializer = import_module(params.get('SERIALIZER', DEFAULT_SERIALIZER)).Handler()
        self._compressor = import_module(params.get('COMPRESSOR', DEFAULT_COMPRESSOR)).Handler()
        app_closed.connect(self.close)

    def decode(self, data):
        if data is None:
            return None

        if not isinstance(data, (bool, int, float)):
            try:
                data = self._compressor.decompress(data)
            except CompressorError:
                pass
            data = self._serializer.loads(data)

        return data

    def encode(self, data):
        if not isinstance(data, (bool, int, float)):
            data = self._serializer.dumps(data)
            data = self._compressor.compress(data)
        return data

    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT):
        if isinstance(timeout, datetime.timedelta):
            timeout = timeout.seconds + timeout.days * 24 * 3600

        if timeout == DEFAULT_TIMEOUT:
            timeout = int(self.default_timeout)
        elif timeout == 0:
            timeout = None
        return timeout

    def make_key(self, key):
        return b"%b%b" % (self.key_prefix, force_bytes(key))

    def get(self, key):
        """
        在缓存中查找密钥key并返回它的值。 如果该键不存在，则返回None
        :param key:
        :return:
        """
        return None

    def delete(self, key):
        """
        从缓存中删除`key`。 如果它不存在于缓存中什么都没发生
        :param key:
        :return:
        """
        pass

    def get_many(self, *keys):
        """
        返回给定键的值列表, 如果键不存在，则返回None
        :param keys:
        :return:
        """
        return map(self.get, keys)

    def get_dict(self, *keys):
        """
        像get_many函数执行，只是返回字典结构
        :param keys:
        :return:
        """
        return dict(zip(keys, self.get_many(*keys)))

    def set(self, key, value, timeout=None):
        """
        将新key/value添加到缓存（如果密钥已存在于缓存中，则覆盖该值）
        :param key:
        :param value:
        :param timeout:
        :return:
        """
        pass

    def add(self, key, value, timeout=None):
        """
        像set函数工作，但不会覆盖已经存在的键的值
        :param key:
        :param value:
        :param timeout:
        :return:
        """
        pass

    @staticmethod
    def _items(mapping):
        if hasattr(mapping, "items"):
            return mapping.items()
        return mapping

    def set_many(self, mapping, timeout=None):
        """
        从映射中设置多个键和值
        :param mapping:
        :param timeout:
        :return:
        """
        for key, value in self._items(mapping):
            self.set(key, value, timeout)

    def delete_many(self, *keys):
        """
        一次删除多个键
        :param keys:
        :return:
        """
        for key in keys:
            self.delete(key)

    def clear(self):
        """
        清除缓存
        请记住，并非所有缓存都支持完全清除缓存
        :return:
        """
        pass

    def inc(self, key, delta=1):
        """
        按delta增加一个键的值。 如果密钥尚不存在，则用delta进行初始化。
        为了支持缓存，这是一个原子操作
        :param key:
        :param delta:
        :return:
        """
        self.set(key, (self.get(key) or 0) + delta)

    def dec(self, key, delta=1):
        """
        按delta增加一个键的值。 如果密钥不存在，则使用-delta进行初始化；
        为了支持缓存，这是一个原子操作
        :param key:
        :param delta:
        :return:
        """
        self.set(key, (self.get(key) or 0) - delta)

    def close(self, *args, **kwargs):
        """
        关闭连接
        :param kwargs:
        :return:
        """
        pass

    def cached(self, key, timeout=DEFAULT_TIMEOUT):
        """
        自定义缓存key
        :param key:
        :param timeout:
        :return:
        """
        def decorator(f):
            @functools.wraps(f)
            async def decorated_function(*args, **kwargs):
                cache_key = self.make_key(key)

                try:
                    cache_value = self.get(cache_key)
                    if asyncio.iscoroutine(cache_value):
                        cache_value = await cache_value

                except Exception:
                    logger.exception("Get cache error, Exception possibly due to cache backend")
                    value = f(*args, **kwargs)
                    if asyncio.iscoroutine(value):
                        value = await value
                    return value

                if cache_value is not None:
                    return cache_value

                new_value = f(*args, **kwargs)
                if asyncio.iscoroutine(new_value):
                    new_value = await new_value

                try:
                    if asyncio.iscoroutinefunction(self.set):
                        await self.set(cache_key, new_value, timeout=timeout)
                    else:
                        self.set(cache_key, new_value, timeout=timeout)
                except Exception:
                    logger.exception("Set cache error, Exception possibly due to cache backend")

                finally:
                    return new_value

            return decorated_function
        return decorator

    def _memoize_make_cache_key(self, f, *args, **kwargs):
            m_args = inspect.getfullargspec(f)[0]
            module = f.__module__

            if hasattr(f, '__qualname__'):
                name = f.__qualname__
            else:
                klass = getattr(f, '__self__', None)

                if klass and not inspect.isclass(klass):
                    klass = klass.__class__

                if not klass:
                    klass = getattr(f, 'im_class', None)

                if not klass:
                    if m_args and args:
                        if m_args[0] == 'self':
                            klass = args[0].__class__
                        elif m_args[0] == 'cls':
                            klass = args[0]

                if klass:
                    name = klass.__name__ + '.' + f.__name__
                else:
                    name = f.__name__

            fname = '.'.join((module, name))
            fname = fname.translate(*null_control)

            if callable(f):
                keyargs, keykwargs = self._memoize_kwargs_to_args(f, *args, **kwargs)
            else:
                keyargs, keykwargs = args, kwargs

            try:
                updated = "{0}{1}{2}".format(fname, keyargs, keykwargs)
            except AttributeError:
                updated = "%s%s%s" % (fname, keyargs, keykwargs)

            cache_key = hashlib.md5()
            cache_key.update(updated.encode('utf-8'))
            cache_key = base64.b64encode(cache_key.digest())[:16]
            cache_key = cache_key.decode('utf-8')

            return cache_key

    @staticmethod
    def _memoize_kwargs_to_args(f, *args, **kwargs):
        new_args = []
        arg_num = 0
        argspec = inspect.getfullargspec(f)

        args_len = len(argspec.args)
        for i in range(args_len):
            if i == 0 and argspec.args[i] in ('self', 'cls'):
                arg = repr(args[0])
                arg_num += 1
            elif argspec.args[i] in kwargs:
                arg = kwargs[argspec.args[i]]
            elif arg_num < len(args):
                arg = args[arg_num]
                arg_num += 1
            elif abs(i-args_len) <= len(argspec.defaults):
                arg = argspec.defaults[i-args_len]
                arg_num += 1
            else:
                arg = None
                arg_num += 1
            new_args.append(arg)

        return tuple(new_args), {}

    def memoize(self, timeout=DEFAULT_TIMEOUT):
        """
        请求参数也作为cache的key一部分
        :param timeout:
        :return:
        """
        def memoize(f):
            @functools.wraps(f)
            async def decorated_function(*args, **kwargs):
                cache_key = self._memoize_make_cache_key(f, *args, **kwargs)
                cache_key = self.make_key(cache_key)
                try:
                    cache_value = self.get(cache_key)
                    if asyncio.iscoroutine(cache_value):
                        cache_value = await cache_value

                except Exception:
                    logger.exception("Get cache error, Exception possibly due to cache backend")
                    value = f(*args, **kwargs)
                    if asyncio.iscoroutine(value):
                        value = await value
                    return value

                if cache_value is not None:
                    return cache_value

                new_value = f(*args, **kwargs)
                if asyncio.iscoroutine(new_value):
                    new_value = await new_value

                try:
                    if asyncio.iscoroutinefunction(self.set):
                        await self.set(cache_key, new_value, timeout=timeout)
                    else:
                        self.set(cache_key, new_value, timeout=timeout)
                except Exception:
                    logger.exception("Set cache error, Exception possibly due to cache backend")

                finally:
                    return new_value

            return decorated_function

        return memoize
