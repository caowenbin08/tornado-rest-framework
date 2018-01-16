# -*- coding: utf-8 -*-
import asyncio
import weakref
import functools
import sys

# python 3.4 compat
if sys.version_info < (3, 5):
    def iscoroutinefunction(func):
        return hasattr(func, '_is_coroutine') and (func._is_coroutine is True)
else:
    iscoroutinefunction = asyncio.iscoroutinefunction


class Signal(object):
    restricted_keywords = ('callback', 'sender', 'senders', 'key', 'keys', 'weak')

    def __init__(self, loop=None, **kwargs):
        for key in self.restricted_keywords:
            if key in kwargs:
                raise ValueError('Keyword "{}" is restricted'.format(key))

        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        self._default_kwargs = kwargs
        self._by_senders = {}
        self._by_keys = {}
        self._all = set()
        self._locks_senders = {}
        self._locks_keys = {}
        self._lock_all = asyncio.Lock()
        self._lock_by_senders = asyncio.Lock()
        self._lock_by_keys = asyncio.Lock()

    @asyncio.coroutine
    def async_connect(self, callback, sender=None, senders=None, key=None, keys=None, weak=True):
        weak_callback = yield from self._get_ref(callback, weak)

        if (sender is None) and (senders is None) and (key is None) and (keys is None):
            # 订阅总是在发送信号时激活回调
            with (yield from self._lock_all):
                self._all.add(weak_callback)
        else:
            if sender is not None:
                yield from self._add_sender(sender, weak_callback)

            if senders is not None:
                for sender in senders:
                    yield from self._add_sender(sender, weak_callback)

            if key is not None:
                yield from self._add_key(key, weak_callback)

            if keys is not None:
                for key in keys:
                    yield from self._add_key(key, weak_callback)

    def connect(self, callback, sender=None, senders=None, key=None, keys=None, weak=True):
        self._loop.create_task(self.async_connect(callback, sender, senders, key, keys, weak))

    @asyncio.coroutine
    def disconnect(self, callback=None, sender=None, senders=None, key=None, keys=None, weak=True):
        weak_callback = yield from self._get_ref(callback, weak)

        if (sender is None) and (senders is None) and (key is None) and (keys is None):
            # removing from _all signals
            # need a lock because we are changing the size of the dict
            if weak_callback in self._all:
                with (yield from self._lock_all):
                    self._all.remove(weak_callback)

            with (yield from self._lock_by_senders):
                sender_keys = list(self._by_senders.keys())
            for sender in sender_keys:
                yield from self._disconnect_from_sender(weak_callback, sender, is_id=True)

            with (yield from self._lock_by_keys):
                key_keys = list(self._by_keys.keys())
            for key in key_keys:
                yield from self._disconnect_from_key(weak_callback, key)

        else:
            # only disconnect from specific senders/keys
            if sender is not None:
                yield from self._disconnect_from_sender(weak_callback, sender)

            if senders is not None:
                for sender in senders:
                    yield from self._disconnect_from_sender(weak_callback, sender)

            if key is not None:
                yield from self._disconnect_from_key(weak_callback, key)

            if keys is not None:
                for key in keys:
                    yield from self._disconnect_from_key(weak_callback, key)

    @asyncio.coroutine
    def async_send(self, sender=None, senders=None, key=None, keys=None, **kwargs):
        """
        :param sender: 发送者
        :param senders: 发件人
        :param key:
        :param keys:
        :param kwargs:
        :return:
        """
        default_kwargs = self._default_kwargs.copy()
        for keyword in kwargs:
            if keyword not in default_kwargs:
                raise ValueError('You can not add new kwargs to an existing signal.')

        default_kwargs.update(kwargs)

        if senders is not None:
            senders = set(senders)
        else:
            senders = set()
        if sender is not None:
            senders.add(sender)

        if keys is not None:
            keys = set(keys)
        else:
            keys = set()

        if key is not None:
            keys.add(key)

        live_callbacks = set()

        # 收集连接到所有发送呼叫的回调
        with (yield from self._lock_all):
            all_callbacks = yield from self._get_callbacks(self._all)

        live_callbacks = live_callbacks | all_callbacks

        # 收集发件人筛选的回调
        sender_callbacks = set()
        for sender in senders:
            id_ = yield from self._make_id(sender)
            if id_ in self._by_senders:
                sender_lock = self._get_lock(self._locks_senders, id_)
                with (yield from sender_lock):
                    new_sender_callbacks = yield from self._get_callbacks(self._by_senders[id_])

                    if not new_sender_callbacks:
                        with (yield from self._lock_by_senders):
                            # Do some pruning
                            del (self._by_senders[id_])
                            del (self._locks_senders[id_])
                    else:
                        sender_callbacks = sender_callbacks | new_sender_callbacks

        live_callbacks = live_callbacks | sender_callbacks

        # 收集关键过滤的回调
        key_callbacks = set()
        for key in keys:
            if key in self._by_keys:
                key_lock = self._get_lock(self._locks_keys, key)
                with (yield from key_lock):
                    new_key_callbacks = yield from self._get_callbacks(self._by_keys[key])

                    if not new_key_callbacks:
                        # Do some pruning
                        with (yield from self._lock_by_keys):
                            del (self._by_keys[key])
                            del (self._locks_keys[key])
                    else:
                        key_callbacks = key_callbacks | new_key_callbacks

        live_callbacks = live_callbacks | key_callbacks

        # 安排所有收集的回调

        for callback in live_callbacks:
            yield from self._call_callback(callback, senders, keys, **default_kwargs)

        return len(live_callbacks)

    def send(self, sender=None, senders=None, key=None, keys=None, **kwargs):
        self._loop.create_task(self.async_send(sender, senders, key, keys, **kwargs))

    @asyncio.coroutine
    def _call_callback(self, callback, senders, keys, **kwargs):
        fn = functools.partial(callback, signal=self, senders=senders, keys=keys, **kwargs)
        if iscoroutinefunction(callback):
            self._loop.create_task(fn())
        else:
            self._loop.call_soon_threadsafe(fn)

    @staticmethod
    @asyncio.coroutine
    def _get_callbacks(collection):
        dead_callbacks = []
        live_callbacks = set()

        for ref in collection:
            # Get the actual callback if it is a weak reference
            if isinstance(ref, weakref.ref):
                callback = ref()
            else:
                callback = ref

            if not callback:
                dead_callbacks.append(ref)
                continue
            else:
                live_callbacks.add(callback)

        # Prune the dead callbacks
        if dead_callbacks:
            for callback in dead_callbacks:
                collection.remove(callback)

        return live_callbacks

    @staticmethod
    @asyncio.coroutine
    def _make_id(target):
        if hasattr(target, '__func__') and hasattr(target, '__self__'):
            return (id(target.__self__), id(target.__func__))
        return id(target)

    @asyncio.coroutine
    def _add_sender(self, sender, weak_callback):
        id_ = yield from self._make_id(sender)
        if id_ not in self._by_senders:
            with (yield from self._lock_by_senders):
                self._by_senders[id_] = set()

        sender_lock = self._get_lock(self._locks_senders, id_)
        with (yield from sender_lock):
            self._by_senders[id_].add(weak_callback)

    @asyncio.coroutine
    def _add_key(self, key, weak_callback):
        if key not in self._by_keys:
            with (yield from self._lock_by_keys):
                self._by_keys[key] = set()

        key_lock = self._get_lock(self._locks_keys, key)
        with (yield from key_lock):
            self._by_keys[key].add(weak_callback)

    @staticmethod
    @asyncio.coroutine
    def _get_ref(callback, weak=True):
        if weak:
            # Check if callback is an instance method or not
            if hasattr(callback, '__func__') and hasattr(callback, '__self__'):
                ref = weakref.WeakMethod
            else:
                ref = weakref.ref

            weak_callback = ref(callback)
        else:
            weak_callback = callback
        return weak_callback

    @asyncio.coroutine
    def _disconnect_from_sender(self, weak_callback, sender, is_id=False):
        if not is_id:
            id_ = yield from self._make_id(sender)
        else:
            id_ = sender
        if id_ in self._by_senders:
            if weak_callback in self._by_senders[id_]:
                sender_lock = self._get_lock(self._locks_senders, id_)
                with (yield from sender_lock):
                    self._by_senders[id_].remove(weak_callback)
                    if len(self._by_senders[id_]) == 0:
                        # We can do some cleanup
                        with (yield from self._lock_by_senders):
                            del (self._by_senders[id_])
                            del (self._locks_senders[id_])

    @asyncio.coroutine
    def _disconnect_from_key(self, weak_callback, key):
        if key in self._by_keys:
            if weak_callback in self._by_keys[key]:
                key_lock = self._get_lock(self._locks_keys, key)
                with (yield from key_lock):
                    self._by_keys[key].remove(weak_callback)
                    if len(self._by_keys[key]) == 0:
                        # We can do some cleanup
                        with (yield from self._lock_by_keys):
                            del (self._by_keys[key])
                            del (self._locks_keys[key])

    @staticmethod
    def _get_lock(map_, key):
        if key not in map_:
            map_[key] = asyncio.Lock()
        return map_[key]
