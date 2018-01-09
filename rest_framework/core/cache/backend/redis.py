# -*- coding: utf-8 -*-
import uuid
import asyncio
import aioredis
import datetime
from rest_framework.core.cache.backend.base import BaseCache, DEFAULT_TIMEOUT
from rest_framework.core.exceptions import CompressorError
from rest_framework.utils.functional import import_object

__author__ = 'caowenbin'


DEFAULT_SERIALIZER = 'rest_framework.core.serializers.pickle.PickleSerializer'
DEFAULT_COMPRESSOR = 'rest_framework.core.compressors.identity.IdentityCompressor'

UNLOCK_SCRIPT = """
if redis.call("get",KEYS[1]) == ARGV[1] then
    return redis.call("del",KEYS[1])
else
    return 0
end"""

SET_IF_NOT_EXISTS = 'SET_IF_NOT_EXIST'

LOCK_TIMEOUT = 10
LOCK_RETRY_DELAY = 0.1
_NOTSET = object()


class Lock(object):
    def __init__(self, key, lock_id, cache, was_obtained=False):
        self.key = key
        self.lock_id = lock_id
        self.was_obtained = was_obtained
        self._cache = cache

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.unlock()

    @property
    async def is_locked(self):
        return await self._cache.check_lock(self)

    async def unlock(self):
        await self._cache.unlock(self)


class AsyncRedisCache(BaseCache):
    def __init__(self, server, params: dict):
        super(AsyncRedisCache, self).__init__(params)
        self._client = None

        self._server = server
        self._params = params
        self._loop = params.pop('LOOP', None)
        self._options = params.pop('OPTIONS', {})
        serializer_path = self._params.pop('SERIALIZER', DEFAULT_SERIALIZER)
        compressor_path = self._params.pop('COMPRESSOR', DEFAULT_COMPRESSOR)
        serializer_cls = import_object(serializer_path)
        compressor_cls = import_object(compressor_path)
        self._serializer = serializer_cls(options=self._options)
        self._compressor = compressor_cls(options=self._options)

    async def _create_pool_connection(self):
        connection_kwargs = {'loop': self.loop, **{k.lower(): v for k, v in self._options.items()}}
        return await aioredis.create_redis_pool(self._server, **connection_kwargs)

    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT):
        if isinstance(timeout, datetime.timedelta):
            timeout = timeout.seconds + timeout.days * 24 * 3600

        if timeout == DEFAULT_TIMEOUT:
            timeout = int(self.default_timeout)
        elif timeout == 0:
            timeout = None
        return timeout

    def decode(self, data):
        try:
            data = int(data)
        except (ValueError, TypeError):
            try:
                data = self._compressor.decompress(data)
            except CompressorError:
                pass
            data = self._serializer.loads(data)
        return data

    def encode(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            data = self._serializer.dumps(data)
            data = self._compressor.compress(data)
        return data

    @property
    def loop(self):
        """
        延迟得到一个事件循环
        :return:
        """
        if not self._loop:
            self._loop = asyncio.get_event_loop()
        return self._loop

    @property
    async def client(self):
        """
        Lazily setup client connection
        """
        if self._client is None:
            self._client = await self._create_pool_connection()
        return self._client
    # Server API
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
    # Key API
    async def delete(self, key):
        """ Deletes a single key """
        with await (await self.client) as client:
            return await client.delete(key)

    async def delete_many(self, *keys):
        """ Deletes many keys """
        with await (await self.client) as client:
            return await client.delete(*keys)

    async def expire(self, key, timeout):
        """Set a timeout on key.

        if timeout is float it will be multiplied by 1000
        coerced to int and passed to `pexpire` method.

        Otherwise raises TypeError if timeout argument is not int.
        """
        with await (await self.client) as client:
            return await client.expire(key, timeout)

    # --------  String API -------
    async def set(self, key, value, ex=None, px=None, nx=False, xx=False):
        """
        Set the value at key ``key`` to ``value``
        :param key:
        :param value:
        :param ex: sets an expire flag on key ``name`` for ``ex`` seconds.
        :param px: sets an expire flag on key ``name`` for ``px`` milliseconds.
        :param nx: if set to True, set the value at key ``name`` to ``value`` if it
            does not already exist.
        :param xx: if set to True, set the value at key ``name`` to ``value`` if it
            already exists.
        :return:
        """
        expire = 0 if not ex else ex.seconds + ex.days * 24 * 3600 if isinstance(ex, datetime.timedelta) else ex
        pexpire = 0 if not ex else (px.seconds + px.days * 24 * 3600) * 1000 + int(px.microseconds / 1000)\
            if isinstance(px, datetime.timedelta) else px
        exist = "SET_IF_EXIST" if xx else 'SET_IF_NOT_EXIST' if nx else None
        with await (await self.client) as client:
            if await self.verify_version:
                return await client.set(key, self.encode(value), expire=expire, pexpire=pexpire, exist=exist)
            else:
                return await self.setex(key, value, expire if expire else int(pexpire/1000))

    async def setex(self, key, value, timeout=DEFAULT_TIMEOUT):
        """
        Set the value of key ``name`` to ``value`` that expires in ``time``
        seconds. ``time`` can be represented by an integer or a Python
        timedelta object.
        """
        seconds = self.get_backend_timeout(timeout)
        with await (await self.client) as client:
            return await client.setex(key, seconds, self.encode(value))

    async def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None, **kwargs):
        """ Takes a dictionary of key to value and sets all the keys to the value """
        expire = self.get_backend_timeout(timeout)
        with await (await self.client) as client:
            for key, value in data.items():
                key = self.make_key(key, version=version)
                await client.set(key, self.encode(value), expire=expire, **kwargs)

    async def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return await self.set(key, value, timeout=timeout, version=version)

    async def get(self, key, default=None, version=None):
        """ Gets a single key """
        # key = self.make_key(key, version=version)
        with await (await self.client) as client:
            result = await client.get(key)
            if not result:
                return default
            return self.decode(result)

    async def get_many(self, keys, version=None):
        """ Gets many keys and returns them in a dict of key -> value """
        versioned_keys = [self.make_key(key, version=version) for key in keys]
        with await (await self.client) as client:
            cache_data = await client.mget(*versioned_keys)
            final_data = {}
            for key, result in zip(keys, cache_data):
                if isinstance(result, bytes):
                    final_data[key] = self.decode(result)
                else:
                    final_data[key] = result
            return final_data

    async def get_or_set(self, key, default=None, timeout=DEFAULT_TIMEOUT, version=None):
        """ Gets a value from cache or sets it to the default """
        key = self.make_key(key, version=version)
        with await (await self.client) as client:
            data = await client.getset(key, self.encode(default))
            return self.decode(data)

    async def has_key(self, key, version=None):
        """ Checks to see if a key exists """
        with await (await self.client) as client:
            return bool(await client.exists(self.make_key(key, version=version)))

    async def incr(self, key, delta=1, version=None):
        """ Increments a key by the delta """
        key = self.make_key(key, version=version)
        with await (await self.client) as client:
            return await client.incrby(key, delta)

    async def decr(self, key, delta=1, version=None):
        """ Decrements a key by the delta. """
        key = self.make_key(key, version=version)
        with await (await self.client) as client:
            return await client.decrby(key, delta)

    async def clear(self):
        """
        Clears all keys. Not using flushall and instead returning a count for compatibility with other Django backends.
        """
        with await (await self.client) as client:
            keys = await client.keys(self.make_key('*'))
            count = len(keys)
            await client.delete(*keys)
            return count

    async def lock(self, key, timeout=LOCK_TIMEOUT, retries=3, version=None):
        """
        Attempts to obtain a redis lock on a specific key
        """
        key = self.make_key(key, version=version)
        lock_id = str(uuid.uuid4())

        obtained = await self._lock(key, lock_id, timeout)
        if not obtained:
            while retries and not obtained:
                retries -= 1
                await asyncio.sleep(LOCK_RETRY_DELAY)
                obtained = await self._lock(key, lock_id, timeout)
        return Lock(key=key, lock_id=lock_id, cache=self, was_obtained=obtained)

    async def _lock(self, key, lock_id, timeout):
        value = self.encode(lock_id)
        with await (await self.client) as client:
            return await client.set(key, value=value, expire=timeout, exist=SET_IF_NOT_EXISTS)

    async def check_lock(self, lock):
        """ Checks to see if a lock is still locked """
        with await (await self.client) as client:
            data = await client.get(lock.key)
            return self.decode(data) == lock.lock_id if data else False

    async def unlock(self, lock):
        """ Unlocks a lock """
        if lock.was_obtained:
            await self.run_lua(UNLOCK_SCRIPT, keys=[lock.key], args=[self.encode(lock.lock_id)])

    async def run_lua(self, script, keys=None, args=None):
        with await (await self.client) as client:
            return await client.eval(script, keys=keys, args=args)

    #  Hash API
    async def hmset_dict(self, key, *args, timeout=0, **kwargs):
        """Set multiple hash fields to multiple values.

        dict can be passed as first positional argument:

        >>> await redis.hmset_dict(
        ...     'key', {'field1': 'value1', 'field2': 'value2'})

        or keyword arguments can be used:

        >>> await redis.hmset_dict(
        ...     'key', field1='value1', field2='value2')

        or dict argument can be mixed with kwargs:

        >>> await redis.hmset_dict(
        ...     'key', {'field1': 'value1'}, field2='value2')

        .. note:: ``dict`` and ``kwargs`` not get mixed into single dictionary,
           if both specified and both have same key(s) -- ``kwargs`` will win:

           >>> await redis.hmset_dict('key', {'foo': 'bar'}, foo='baz')
           >>> await redis.hget('key', 'foo', encoding='utf-8')
           'baz'

        """
        with await (await self.client) as client:
            result = await client.hmset_dict(key, *args, **kwargs)
            if result and timeout is not None and timeout > 0:
                result = await client.expire(key, timeout)
            return result

    async def hmset(self, key, field, value, *pairs):
        """Set multiple hash fields to multiple values."""
        with await (await self.client) as client:
            return await client.hmset(key, field, value, *pairs)

    async def hset(self, key, field, value):
        """Set the string value of a hash field."""
        with await (await self.client) as client:
            return await client.hset(key, field, value)

    async def hmget(self, key, field, *fields, encoding="utf-8"):
        """Get the values of all the given fields."""
        with await (await self.client) as client:
            return await client.hmget(key, field, *fields, encoding)

    async def hgetall(self, key, encoding="utf-8"):
        """Get all the fields and values in a hash."""
        with await (await self.client) as client:
            return await client.hgetall(key, encoding=encoding)
