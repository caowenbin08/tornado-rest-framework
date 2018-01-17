# -*- coding: utf-8 -*-
"""
在Python 3的asyncio基础结构上实现了两个基元（await和spawn）。
这两个函数允许我们从同步代码中调用异步函数
"""
import sys
import heapq
import logging
import time
from asyncio.log import logger
from asyncio.tasks import Task, async
from asyncio.coroutines import iscoroutinefunction
from asyncio.events import get_event_loop

__author__ = 'caowenbin'


class RecursionMonitor(object):
    def __init__(self):
        self.max = 10000
        self.threshold = 100
        self.limit = sys.getrecursionlimit()
        self.current = 0
        self.old_current = 0
        self.t0 = time.time()

    def incr(self):
        self.current += 1

        if __debug__:
            self.show_debug_info()

        if self.current + self.threshold > self.limit:
            self.limit += 1000

            if self.limit < self.max:
                sys.setrecursionlimit(self.limit)
                logger.warning('increased recursion limit to {}'.format(self.limit))

    def decr(self):
        self.current -= 1

    def show_debug_info(self):
        changed = self.old_current != self.current
        now = time.time()
        if now - self.t0 > 1 and changed:
            self.t0 = now
            self.old_current = self.current
            logger.debug('aioawait recursion: {}'.format(self.current))


recursion = RecursionMonitor()


def await(coro, loop=None):
    recursion.incr()
    try:
        if loop is None:
            loop = get_event_loop()

        if iscoroutinefunction(coro):
            coro = coro()

        if isinstance(coro, Task):
            future = coro
        else:
            future = Task(coro, loop=loop)

        def _run_until_complete():
            add_delay = False

            while not future.done():
                t0 = time.monotonic()
                _run_once(loop, timeout=(0.1 if add_delay else None))
                add_delay = (time.monotonic()-t0) < 0.001

            return future.result()

        if loop.is_running():
            # old_task = Task.current_tasks()
            # try:
            return _run_until_complete()
            # finally:
                # Task._current_tasks[loop] = old_task
        else:
            loop._running = True
            try:
                return _run_until_complete()
            finally:
                loop._running = False

    finally:
        recursion.decr()


def spawn(coro, loop=None):
    if loop is None:
        loop = get_event_loop()
    if iscoroutinefunction(coro):
        coro = coro()
    return async(coro, loop=loop)


def _run_once(self, timeout=None):
    while self._scheduled and self._scheduled[0]._cancelled:
        heapq.heappop(self._scheduled)

    if self._ready:
        timeout = 0
    elif self._scheduled:
        when = self._scheduled[0]._when
        timeout = max(0, when - self.time())

    if __debug__ and logger.isEnabledFor(logging.INFO):
        t0 = self.time()
        event_list = self._selector.select(timeout)
        t1 = self.time()
        tdiff = t1-t0
        if tdiff > 0.001:
            if tdiff >= 1:
                level = logging.INFO
            else:
                level = logging.DEBUG
            if timeout is not None:
                logger.log(level, 'poll %.4f took %.4f seconds', timeout, tdiff)
            else:
                logger.log(level, 'poll took %.4f seconds', tdiff)
    else:
        event_list = self._selector.select(timeout)

    self._process_events(event_list)

    end_time = self.time() + self._clock_resolution
    while self._scheduled:
        handle = self._scheduled[0]
        if handle._when >= end_time:
            break
        handle = heapq.heappop(self._scheduled)
        self._ready.append(handle)

    while self._ready:
        handle = self._ready.popleft()
        if not handle._cancelled:
            handle._run()
