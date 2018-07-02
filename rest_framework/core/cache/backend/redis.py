# -*- coding: utf-8 -*-
import asyncio
import aioredis
from rest_framework.core.cache.backend.base import BaseCache, DEFAULT_TIMEOUT


class CacheWrapper(BaseCache):
    def __init__(self, server, params: dict):
        super().__init__(server, params)
        self._client = None
        self._loop = None

    @property
    def loop(self):
        if not self._loop:
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def _create_pool_connection(self):
        connection_kwargs = {'loop': self.loop, **{k.lower(): v for k, v in self._options.items()}}
        return await aioredis.create_redis_pool(self._server, **connection_kwargs)

    @property
    async def client(self):
        if self._client is None:
            self._client = await self._create_pool_connection()
        return self._client

    async def close(self, *args, **kwargs):
        if self._client is not None:
            self._client.close()
            await self._client.wait_closed()

    async def _get_redis_version(self):
        with await (await self.client) as client:
            server_info = await client.execute(b'INFO')
            for info in server_info.split(b"\r\n"):
                if b"redis_version" in info:
                    redis_version = info.split(b":")[1]
                    return redis_version
            return b""

    @property
    async def verify_version(self):
        """
        检查是否>=2.6版本
        :return:
        """
        redis_version = await self._get_redis_version()
        if redis_version < b"2.6":
            return False
        return True

    async def delete(self, key):
        key = self.make_key(key)
        with await (await self.client) as client:
            return await client.delete(key)

    async def delete_many(self, *keys):
        keys = [self.make_key(key) for key in keys]
        with await (await self.client) as client:
            return await client.delete(*keys)

    async def expire(self, key, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        with await (await self.client) as client:
            return await client.expire(key, timeout)

    async def set(self, key, value, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        with await (await self.client) as client:
            if timeout is None:
                return await client.set(key, self.encode(value))
            return await client.setex(key, timeout, self.encode(value))

    async def add(self, key, value, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        with await (await self.client) as client:
            added = await client.setnx(key, self.encode(value))
            if added and timeout is not None:
                await client.expire(key, timeout)

    async def set_many(self, mapping, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)

        with await (await self.client) as client:
            tr = client.multi_exec()

            for key, value in self._items(mapping):
                key = self.make_key(key)
                tr.setex(key, timeout, self.encode(value))

            await tr.execute()

    async def get(self, key, default=None):
        key = self.make_key(key)
        with await (await self.client) as client:
            result = await client.get(key)
            if not result:
                return default
            return self.decode(result)

    async def get_many(self, keys):
        versioned_keys = [self.make_key(key) for key in keys]
        with await (await self.client) as client:
            cache_data = await client.mget(*versioned_keys)
            final_data = {}
            for key, result in zip(keys, cache_data):
                if isinstance(result, bytes):
                    final_data[key] = self.decode(result)
                else:
                    final_data[key] = result
            return final_data

    async def inc(self, key, delta=1):
        key = self.make_key(key)
        with await (await self.client) as client:
            return await client.incrby(key, delta)

    async def dec(self, key, delta=1):
        key = self.make_key(key)
        with await (await self.client) as client:
            return await client.decrby(key, delta)

    async def clear_keys(self, key_prefix):
        """
        根据key前缀清空对应的key值
        :param key_prefix:
        :return:
        """
        with await (await self.client) as client:
            keys = await client.keys(self.make_key('%s*' % key_prefix))
            if keys:
                return await client.delete(*keys)
            return 0

    async def clear(self):
        with await (await self.client) as client:
            if self.key_prefix:
                keys = await client.keys(self.make_key('*'))
                if keys:
                    await client.delete(*keys)
            else:
                await client.flushdb()

    async def hmset(self, key, field, value):
        key = self.make_key(key)
        with await (await self.client) as client:
            return await client.hmset(key, field, self.encode(value))

    async def hmset_many(self, key, mapping, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)
        map_context = {k: self.encode(v) for k, v in self._items(mapping)}

        with await (await self.client) as client:
            result = await client.hmset_dict(key, map_context)
            if result and timeout:
                result = await client.expire(key, timeout)
            return result

    async def hmget(self, key, field, encoding="utf-8"):
        key = self.make_key(key)
        with await (await self.client) as client:
            result = await client.hmget(key, field, encoding)
            return self.decode(result[0])

    async def hmget_many(self, key, *fields, encoding="utf-8"):
        key = self.make_key(key)
        with await (await self.client) as client:
            result = await client.hmget(key, *fields, encoding)
            return [self.decode(r) for r in result]

    async def hgetall(self, key, encoding="utf-8"):
        key = self.make_key(key)
        with await (await self.client) as c:
            result = await c.hgetall(key, encoding=encoding)
            return {k: self.decode(v) for k, v in result.items()}
