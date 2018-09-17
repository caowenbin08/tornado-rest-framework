# -*- coding: utf-8 -*-
import asyncio
import aioredis
from aioredis import Redis


from rest_framework.core.cache.backend.base import BaseCache, DEFAULT_TIMEOUT


class OperationalError(Exception):
    pass


class AsyncConnectionContextManager:

    def __init__(self, cache):
        self._cache = cache
        self._is_init = False
        self._conn = None

    async def __aenter__(self):
        if not self._is_init:
            await self._cache.create_pool_connection()
            self._is_init = True
        conn = await self._cache.pool.acquire()
        self._conn = conn
        return Redis(self._conn)

    async def __aexit__(self, exc_type, exc_value, tb):
        try:
            self._cache.pool.release(self._conn)
        finally:
            self._conn = None


class CacheWrapper(BaseCache):
    def __init__(self, server, params: dict):
        super().__init__(server, params)
        self.closed = True
        self.pool = None
        self._loop = None
        self._auto_task = None

    @property
    def loop(self):
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def create_pool_connection(self, safe=True):
        if not self.closed:
            if safe:
                return
            raise OperationalError('Connection already open')

        connection_kwargs = {'loop': self.loop, **{k.lower(): v for k, v in self._options.items()}}
        if "timeout" in connection_kwargs:
            timeout = connection_kwargs.pop("timeout")
            connection_kwargs["create_connection_timeout"] = timeout
        self.pool = await aioredis.create_pool(self._server, **connection_kwargs)
        self.closed = False
        await self.init_engine()

    async def init_engine(self):
        self._auto_task = self.loop.create_task(self.keep_engine())

    async def keep_engine(self):
        while 1:
            async with self.pool.get() as conn:
                await conn.execute('ping')
            await asyncio.sleep(60)

    async def close_engine(self):
        if self._auto_task is not None:
            self._auto_task.cancel()

    def get_conn(self):
        return AsyncConnectionContextManager(self)

    @property
    async def client(self):
        await self.create_pool_connection()
        return Redis(self.pool)

    async def close(self, *args, **kwargs):
        if not self.closed and self.pool:
            await self.close_engine()
            self.pool.close()
            await self.pool.wait_closed()

    async def _get_redis_version(self):
        async with self.get_conn() as conn:
            server_info = await conn.execute(b'INFO')
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
        async with self.get_conn() as conn:
            return await conn.delete(key)

    async def delete_many(self, *keys):
        keys = [self.make_key(key) for key in keys]
        async with self.get_conn() as conn:
            return await conn.delete(*keys)

    async def expire(self, key, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.expire(key, timeout)

    async def set(self, key, value, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        async with self.get_conn() as conn:
            if timeout is None:
                return await conn.set(key, self.encode(value))
            return await conn.setex(key, timeout, self.encode(value))

    async def add(self, key, value, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)
        key = self.make_key(key)
        async with self.get_conn() as conn:
            added = await conn.setnx(key, self.encode(value))
            if added and timeout is not None:
                await conn.expire(key, timeout)

    async def set_many(self, mapping, timeout=DEFAULT_TIMEOUT):
        timeout = self.get_backend_timeout(timeout)

        async with self.get_conn() as conn:
            tr = conn.multi_exec()

            for key, value in self._items(mapping):
                key = self.make_key(key)
                tr.setex(key, timeout, self.encode(value))

            await tr.execute()

    async def get(self, key, default=None):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            result = await conn.get(key)
            if not result:
                return default
            return self.decode(result)

    async def get_many(self, keys):
        versioned_keys = [self.make_key(key) for key in keys]
        async with self.get_conn() as conn:
            cache_data = await conn.mget(*versioned_keys)
            final_data = {}
            for key, result in zip(keys, cache_data):
                if isinstance(result, bytes):
                    final_data[key] = self.decode(result)
                else:
                    final_data[key] = result
            return final_data

    async def inc(self, key, delta=1):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.incrby(key, delta)

    async def dec(self, key, delta=1):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.decrby(key, delta)

    async def clear_keys(self, key_prefix):
        """
        根据key前缀清空对应的key值
        :param key_prefix:
        :return:
        """
        async with self.get_conn() as conn:
            keys = await conn.keys(self.make_key('%s*' % key_prefix))
            if keys:
                return await conn.delete(*keys)
            return 0

    async def clear(self):
        async with self.get_conn() as conn:
            if self.key_prefix:
                keys = await conn.keys(self.make_key('*'))
                if keys:
                    await conn.delete(*keys)
            else:
                await conn.flushdb()

    async def hmset(self, key, field, value):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.hmset(key, field, self.encode(value))

    async def hmset_many(self, key, mapping, timeout=DEFAULT_TIMEOUT):
        key = self.make_key(key)
        timeout = self.get_backend_timeout(timeout)
        map_context = {k: self.encode(v) for k, v in self._items(mapping)}

        async with self.get_conn() as conn:
            result = await conn.hmset_dict(key, map_context)
            if result and timeout:
                result = await conn.expire(key, timeout)
            return result

    async def hmget(self, key, field, encoding="utf-8"):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            result = await conn.hmget(key, field, encoding)
            return self.decode(result[0])

    async def hmget_many(self, key, *fields, encoding="utf-8"):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            result = await conn.hmget(key, *fields, encoding)
            return [self.decode(r) for r in result]

    async def hgetall(self, key, encoding="utf-8"):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            result = await conn.hgetall(key, encoding=encoding)
            return {k: self.decode(v) for k, v in result.items()}

    async def sadd(self, key, *members):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.sadd(key, *members)

    async def smembers(self, key, encoding="utf8"):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.smembers(key, encoding=encoding)

    async def sismember(self, key, member):
        key = self.make_key(key)
        async with self.get_conn() as conn:
            return await conn.sismember(key, member)


