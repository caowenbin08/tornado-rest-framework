# -*- coding: utf-8 -*-
import asyncio
from time import time
import threading


class CachedProperty:
    """
    一般缓存
    """
    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self

        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


class AsyncCachedProperty(CachedProperty):
    """
    一般缓存
    """
    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    @asyncio.coroutine
    def __get__(self, obj, cls):
        if obj is None:
            return self

        if asyncio.iscoroutinefunction(self.func):
            v = yield from self.func(obj)
        else:
            v = self.func(obj)
        value = obj.__dict__[self.func.__name__] = v
        return value


class ThreadedCachedProperty:
    """
    用于多线程场景的缓存
    """

    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func
        self.lock = threading.RLock()

    def __get__(self, obj, cls):
        if obj is None:
            return self

        obj_dict = obj.__dict__
        name = self.func.__name__
        with self.lock:
            try:
                # check if the value was computed before the lock was acquired
                return obj_dict[name]
            except KeyError:
                # if not, do the calculation and release the lock
                return obj_dict.setdefault(name, self.func(obj))


class CachedPropertyWithTtl:
    """
    带失效时间的缓存，单位秒
    """

    def __init__(self, ttl=None):
        if callable(ttl):
            func = ttl
            ttl = None
        else:
            func = None
        self.ttl = ttl
        self._prepare_func(func)

    def __call__(self, func):
        self._prepare_func(func)
        return self

    def __get__(self, obj, cls):
        if obj is None:
            return self

        now = time()
        obj_dict = obj.__dict__
        name = self.__name__
        try:
            value, last_updated = obj_dict[name]
        except KeyError:
            pass
        else:
            ttl_expired = self.ttl and self.ttl < now - last_updated
            if not ttl_expired:
                return value

        value = self.func(obj)
        obj_dict[name] = (value, now)
        return value

    def __delete__(self, obj):
        obj.__dict__.pop(self.__name__, None)

    def __set__(self, obj, value):
        obj.__dict__[self.__name__] = (value, time())

    def _prepare_func(self, func):
        self.func = func
        if func:
            self.__doc__ = func.__doc__
            self.__name__ = func.__name__
            self.__module__ = func.__module__


class ThreadedCachedPropertyWithTtl(CachedPropertyWithTtl):
    """
    用于多线程场景的带失效时间的缓存
    单位秒
    """

    def __init__(self, ttl=None):
        super(ThreadedCachedPropertyWithTtl, self).__init__(ttl)
        self.lock = threading.RLock()

    def __get__(self, obj, cls):
        with self.lock:
            return super(ThreadedCachedPropertyWithTtl, self).__get__(obj, cls)

cached_property = CachedProperty
async_cached_property = AsyncCachedProperty

cached_property_ttl = CachedPropertyWithTtl
timed_cached_property = CachedPropertyWithTtl

threaded_cached_property = ThreadedCachedProperty
threaded_cached_property_ttl = ThreadedCachedPropertyWithTtl
timed_threaded_cached_property = ThreadedCachedPropertyWithTtl
