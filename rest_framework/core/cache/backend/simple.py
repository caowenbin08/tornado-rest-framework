# -*- coding: utf-8 -*-
from time import time

from rest_framework.core.cache.backend.base import BaseCache, DEFAULT_TIMEOUT


class CacheWrapper(BaseCache):
    """
    简单的内存缓存；
    适用于单个进程环境，主要用于开发服务器；
    非线程安全的
    """
    def __init__(self, server, params: dict):
        super().__init__(server, params)
        self._cache = {}
        # 缓存个数，默认不限制
        self._threshold = self._options.get("THRESHOLD", 0)

    def _prune(self):
        if self._threshold == 0:
            return

        if len(self._cache) > self._threshold:
            now = time()
            for idx, (key, (expires, _)) in enumerate(self._cache.items()):
                if expires is not None and (expires <= now or idx % 3 == 0):
                    self._cache.pop(key, None)

    def get(self, key):
        key = self.make_key(key)
        expires, value = self._cache.get(key, (0, None))
        if expires is None or expires > time():
            return self.decode(value)

    def set(self, key, value, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)

        self._prune()
        self._cache[key] = ((time() + timeout) if timeout else timeout, self.encode(value))

    async def add(self, key, value, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)

        if len(self._cache) > self._threshold:
            self._prune()
        item = ((time() + timeout) if timeout else timeout, self.encode(value))
        self._cache.setdefault(key, item)

    async def delete(self, key):
        key = self.make_key(key)
        self._cache.pop(key, None)

    async def clear(self):
        self._cache.clear()

    async def clear_keys(self, key_prefix):
        key = self.make_key(key_prefix)
        del_keys = [k for k in self._cache.keys() if k.startswith(key)]
        for k in del_keys:
            self._cache.pop(k, None)
        return len(del_keys)
