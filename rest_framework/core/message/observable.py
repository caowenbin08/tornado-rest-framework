# -*- coding: utf-8 -*-
from .message import Broker

__author__ = 'caowenbin'

__all__ = ['observable']


def observable(cls):
    t = cls.__init__

    def __init__(self, *a, **kw):
        b = Broker()
        self._message_broker = b
        t(self, *a, **kw)
        assert id(b) == id(self._message_broker), \
            "_message_broker is a reserved word for observable, don't use it any where."

    def sub(self, *a, **kw):
        self._message_broker.sub(*a, **kw)

    def unsub(self, *a, **kw):
        self._message_broker.unsub(*a, **kw)

    def pub(self, *a, **kw):
        self._message_broker.pub(*a, **kw)

    def declare(self, *a, **kw):
        self._message_broker.declare(*a, **kw)

    def retract(self, *a, **kw):
        self._message_broker.retract(*a, **kw)

    def get_declarations(self, *a, **kw):
        self._message_broker.get_declarations(*a, **kw)

    def has_declaration(self, *a, **kw):
        self._message_broker.has_declaration(*a, **kw)

    setattr(cls, '__init__', __init__)

    for k, v in dict(sub=sub,
                     unsub=unsub,
                     pub=pub,
                     declare=declare,
                     retract=retract,
                     get_declarations=get_declarations,
                     has_declaration=has_declaration).iteritems():
        assert not hasattr(cls, k)
        setattr(cls, k, v)
    return cls


if __name__ == '__main__':
    @observable
    class Foo(object):
        def __init__(self, name):
            print('hello, %s.' % name)


    foo = Foo('lai')
    foo.pub('greet')
