"""
同步，主要调用redis-py库包
https://github.com/andymccurdy/redis-py
"""
from redis import StrictRedis


from rest_framework.core.cache.backend.base import BaseCache, DEFAULT_TIMEOUT


class CacheWrapper(BaseCache):
    def __init__(self, server, params: dict):
        super().__init__(server, params)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = StrictRedis.from_url(url=self._server, **self._options)
        return self._client

    async def delete(self, key):
        key = self.make_key(key)
        return self.client.delete(key)

    async def delete_many(self, *keys):
        keys = [self.make_key(key) for key in keys]
        return self.client.delete(*keys)

    async def expire(self, key, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        return self.client.expire(key, timeout)

    async def set(self, key, value, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        if timeout is None:
            return self.client.set(key, self.encode(value))
        return self.client.setex(key, timeout, self.encode(value))

    async def add(self, key, value, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        added = self.client.setnx(key, self.encode(value))
        if added and timeout is not None:
            self.client.expire(key, timeout)
        return added

    async def get(self, key, default=None):
        key = self.make_key(key)
        result = self.client.get(key)
        if not result:
            return default
        return self.decode(result)

    async def get_delete(self, key, default=None):
        key = self.make_key(key)
        result = self.client.get(key)
        if not result:
            return default
        self.client.delete(key)
        return self.decode(result)

    async def get_many(self, keys):
        versioned_keys = [self.make_key(key) for key in keys]
        cache_data = self.client.mget(*versioned_keys)
        final_data = {key: self.decode(result) for key, result in zip(keys, cache_data)}
        return final_data

    async def inc(self, key, delta=1, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        result = self.client.incrby(key, delta)
        timeout = self.get_backend_timeout(timeout)
        if result and timeout is not None:
            self.client.expire(key, timeout)
        return result

    async def dec(self, key, delta=1):
        key = self.make_key(key)
        return self.client.decrby(key, delta)

    async def clear_keys(self, key_prefix):
        """
        根据key前缀清空对应的key值
        """
        keys = self.client.keys(self.make_key(f'{key_prefix}*'))
        if keys:
            return self.client.delete(*keys)
        return 0

    async def clear(self):
        if self._is_make_key:
            keys = self.client.keys(self.make_key('*'))
            if keys:
                return self.client.delete(*keys)
        else:
            return self.client.flushdb()

    async def hset(self, key, field, value, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)
        result = self.client.hset(key, field, self.encode(value))
        if timeout:
            self.client.expire(key, timeout)

        return result

    async def hsetnx(self, key, field, value, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)
        result = self.client.hsetnx(key, field, self.encode(value))
        if result and timeout:
            self.client.expire(key, timeout)
        return result

    async def hmset(self, key, mapping, timeout=DEFAULT_TIMEOUT):
        if not mapping:
            raise ValueError('mapping can not be empty')

        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)
        map_context = {k: self.encode(v) for k, v in self._items(mapping)}

        result = self.client.hmset(key, map_context)
        if result and timeout:
            result = self.client.expire(key, timeout)
        return result

    async def hmget(self, key, field):
        key = self.make_key(key)
        result = self.client.hmget(key, field)
        return self.decode(result[0])

    async def hmget_many(self, key, *fields):
        key = self.make_key(key)
        result = self.client.hmget(key, *fields)
        return [self.decode(r) for r in result]

    async def hgetall(self, key):
        key = self.make_key(key)
        result = self.client.hgetall(key)
        return {k: self.decode(v) for k, v in result.items()}

    async def sadd(self, key, *members):
        key = self.make_key(key)
        return self.client.sadd(key, *members)

    async def smembers(self, key):
        key = self.make_key(key)
        return self.client.smembers(key)

    async def sismember(self, key, member):
        key = self.make_key(key)
        return self.client.sismember(key, member)


