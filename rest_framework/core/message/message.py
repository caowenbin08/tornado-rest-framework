# -*- coding: utf-8 -*-
from copy import copy

from collections import defaultdict
from collections import Hashable

__author__ = 'caowenbin'

__all__ = [
    'Context',
    'Broker',
    'sub',
    'unsub',
    'pub',
    'declare',
    'retract',
    'get_declarations',
    'has_declaration'
]


class Context(object):
    def __init__(self, **kw):
        # 中止消息传递 True代表中止
        self.discontinued = False
        self.__dict__.update(kw)


class Broker(object):
    def __init__(self):
        self._router = defaultdict(list)
        self._board = {}

    def sub(self, topic, func, front=False):
        """
        订阅
        :param topic:
        :param func:
        :param front:
        :return:
        """
        assert isinstance(topic, Hashable)
        assert callable(func)
        if func in self._router[topic]:
            return
        if front:
            self._router[topic].insert(0, func)
        else:
            self._router[topic].append(func)
        if topic in self._board:
            a, kw = self._board[topic]
            func(*a, **kw)

    def unsub(self, topic, func):
        """
        取消订阅
        :param topic:
        :param func:
        :return:
        """

        assert isinstance(topic, Hashable)
        assert callable(func)
        if topic not in self._router:
            return
        try:
            self._router[topic].remove(func)
        except ValueError:
            pass

    def pub(self, topic, *a, **kw):
        """
        发布消息
        :param topic:
        :param a:
        :param kw:
        :return:
        """

        assert isinstance(topic, Hashable)
        if topic not in self._router:
            return
        removed = []
        for func in copy(self._router[topic]):
            if func:
                ctx = func(*a, **kw)
            else:
                removed.append(func)
            try:
                if ctx and ctx.discontinued:
                    break
            except (AttributeError, TypeError):
                pass
        for i in removed:
            try:
                self._router[topic].remove(i)
            except ValueError:
                pass

    def declare(self, topic, *a, **kw):
        assert isinstance(topic, Hashable)
        self._board[topic] = (a, kw)
        return pub(topic, *a, **kw)

    def retract(self, topic):
        assert isinstance(topic, Hashable)
        try:
            self._board.pop(topic)
        except KeyError:
            pass

    def get_declarations(self):
        return self._board.keys()

    def has_declaration(self, topic):
        assert isinstance(topic, Hashable)
        return topic in self._board


_broker = Broker()
sub = _broker.sub
unsub = _broker.unsub
pub = _broker.pub
declare = _broker.declare
retract = _broker.retract
get_declarations = _broker.get_declarations
has_declaration = _broker.has_declaration
