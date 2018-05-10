# -*- coding: utf-8 -*-
import time
import inspect
import string
import random
import hashlib
import asyncio
import functools
from importlib import import_module
from collections import OrderedDict

import collections

try:
    random = random.SystemRandom()
    using_sysrandom = True
except NotImplementedError:
    using_sysrandom = False


def add_metaclass(metaclass):
    """
    类装饰器
    用一个元类来创建一个类
    :param metaclass:
    :return:
    """
    def wrapper(cls):
        orig_vars = cls.__dict__.copy()
        slots = orig_vars.get('__slots__')
        if slots is not None:
            if isinstance(slots, str):
                slots = [slots]
            for slots_var in slots:
                orig_vars.pop(slots_var)
        orig_vars.pop('__dict__', None)
        orig_vars.pop('__weakref__', None)
        return metaclass(cls.__name__, cls.__bases__, orig_vars)
    return wrapper


def set_value(dictionary, keys, value):
    """
    类似于Python内置的字典`dictionary[key] = value`，
    但是需要一个嵌套键的列表，而不是一个键。

    set_value({'a': 1}, [], {'b': 2}) -> {'a': 1, 'b': 2}
    set_value({'a': 1}, ['x'], 2) -> {'a': 1, 'x': 2}
    set_value({'a': 1}, ['x', 'y'], 2) -> {'a': 1, 'x': {'y': 2}}
    """
    if not keys:
        dictionary.update(value)
        return

    for key in keys[:-1]:
        if key not in dictionary:
            dictionary[key] = {}
        dictionary = dictionary[key]

    dictionary[keys[-1]] = value


def to_choices_dict(choices):
    """
    选项值列表转为字典结构
    to_choices_dict([1]) -> {1: 1}
    to_choices_dict([(1, '1st'), (2, '2nd')]) -> {1: '1st', 2: '2nd'}
    to_choices_dict([('Group', ((1, '1st'), 2))]) -> {'Group': {1: '1st', 2: '2nd'}}
    """
    # Allow single, paired or grouped choices style:
    # choices = [1, 2, 3]
    # choices = [(1, 'First'), (2, 'Second'), (3, 'Third')]
    # choices = [('Category', ((1, 'First'), (2, 'Second'))), (3, 'Third')]
    ret = OrderedDict()
    for choice in choices:
        if not isinstance(choice, (list, tuple)):
            # single choice
            ret[choice] = choice
        else:
            key, value = choice
            if isinstance(value, (list, tuple)):
                # grouped choices (category, sub choices)
                ret[key] = to_choices_dict(value)
            else:
                # paired choice (key, display value)
                ret[key] = value
    return ret


def flatten_choices_dict(choices):
    """
    将选项组转成字典结构
    flatten_choices_dict({1: '1st', 2: '2nd'}) -> {1: '1st', 2: '2nd'}
    flatten_choices_dict({'Group': {1: '1st', 2: '2nd'}}) -> {1: '1st', 2: '2nd'}
    """
    ret = OrderedDict()
    for key, value in choices.items():
        if isinstance(value, dict):
            # grouped choices (category, sub choices)
            for sub_key, sub_value in value.items():
                ret[sub_key] = sub_value
        else:
            # choice (key, display value)
            ret[key] = value
    return ret


def reraise(tp, value, tb=None):
    if value is None:
        value = tp()
    if value.__traceback__ is not tb:
        raise value.with_traceback(tb)
    raise value


def import_object(obj_name):
    """
    根据对象名称导入
        import_object('x') is equivalent to 'import x'.
        import_object('x.y.z') is equivalent to 'from x.y import z'.

        >>> import tornado.escape
        >>> import_object('tornado.escape') is tornado.escape
        True
        >>> import_object('tornado.escape.utf8') is tornado.escape.utf8
        True
        >>> import_object('tornado') is tornado
        True
        >>> import_object('tornado.missing_module')
        Traceback (most recent call last):
            ...
        ImportError: No module named missing_module

    :param obj_name:
    :return:
    """
    if obj_name is None:
        return obj_name

    elif callable(obj_name):
        return obj_name

    if not isinstance(obj_name, str):
        obj_name = obj_name.encode('utf-8')

    if obj_name.count('.') == 0:
        return __import__(obj_name, None, None)
    try:
        module_path, class_name = obj_name.rsplit('.', 1)
    except ValueError:
        msg = "%s doesn't look like a module path" % obj_name
        raise ImportError(msg)

    obj = import_module(module_path)

    try:
        return getattr(obj, class_name)
    except AttributeError:
        msg = 'Module "%s" does not define a "%s" attribute/class"' % (module_path, class_name)
        raise ImportError(msg)


class OrderedDictStorage(OrderedDict):
    """
    对有序字典进行扩展，使其支持通过 dict.a形式访问以代替dict['a']
    Example::
        >>> o = OrderedDictStorage(a=1)
        >>> print o.a
        1
        >>> o['a']
        1
        >>> o.a = 2
        >>> print o['a']
        2
        >>> del o.a
        >>> print o.a
        None
    """
    __slots__ = ()
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
    __getitem__ = dict.get
    __getattr__ = dict.get
    __copy__ = lambda self: OrderedDictStorage(self)

    def getlist(self, key):
        """
        存储值作为列表返回。
        如果值是一个列表，它将直接返回。
        如果对象为空，则返回空列表，否则，将返回`[value]`。

        Example output for a query string of `?x=abc&y=abc&y=def`::
            >>> request = OrderedDictStorage()
            >>> request.vars = OrderedDictStorage()
            >>> request.vars.x = 'abc'
            >>> request.vars.y = ['abc', 'def']
            >>> request.vars.getlist('x')
            ['abc']
            >>> request.vars.getlist('y')
            ['abc', 'def']
            >>> request.vars.getlist('z')
            []
        :param key:
        :return:
        """

        value = self.get(key, [])
        if value is None or isinstance(value, (list, tuple)):
            return value
        else:
            return [value]

    def getfirst(self, key, default=None):
        """
        返回给定的列表或值本身的第一个值。
        如果值是一个列表，它的第一个项目将被返回；否则，该值将直接返回。
        Example output for a query string of `?x=abc&y=abc&y=def`::
            >>> request = OrderedDictStorage()
            >>> request.vars = OrderedDictStorage()
            >>> request.vars.x = 'abc'
            >>> request.vars.y = ['abc', 'def']
            >>> request.vars.getfirst('x')
            'abc'
            >>> request.vars.getfirst('y')
            'abc'
            >>> request.vars.getfirst('z')
        """
        values = self.getlist(key)
        return values[0] if values else default

    def getlast(self, key, default=None):
        """
        返回给定值的列表或值本身的最后一个值。
        如果该值是一个列表，则将返回最后一个项；否则，该值将直接返回。
        Simulated output with a query string of `?x=abc&y=abc&y=def`::
            >>> request = OrderedDictStorage()
            >>> request.vars = OrderedDictStorage()
            >>> request.vars.x = 'abc'
            >>> request.vars.y = ['abc', 'def']
            >>> request.vars.getlast('x')
            'abc'
            >>> request.vars.getlast('y')
            'def'
            >>> request.vars.getlast('z')
        """
        values = self.getlist(key)
        return values[-1] if values else default


def is_simple_callable(obj):
    """
    如果对象是可调用的，不带参数，则为true
    :param obj:
    :return:
    """
    if not (inspect.isfunction(obj) or inspect.ismethod(obj)):
        return False

    sig = inspect.signature(obj)
    params = sig.parameters.values()
    return all(
        param.kind == param.VAR_POSITIONAL or
        param.kind == param.VAR_KEYWORD or
        param.default != param.empty
        for param in params
    )


def get_random_string(length=12, allowed_chars=None):
    """
    生成对应长度的随机字符串
    :param length:
    :param allowed_chars:
    :return:
    """
    if allowed_chars is None:
        allowed_chars = string.digits + string.ascii_letters

    if not using_sysrandom:
        random.seed(hashlib.sha256(("%s%s" % (random.getstate(), time.time())).encode('utf-8')).digest())
    return ''.join(random.choice(allowed_chars) for _ in range(length))


def get_attribute(instance, attributes):
    """
    Similar to Python's built in `getattr(instance, attr)`,
    but takes a list of nested attributes, instead of a single attribute.

    Also accepts either attribute lookup on objects or dictionary lookups.
    """
    for attr in attributes:
        if instance is None:
            return None

        if isinstance(instance, collections.Mapping):
            instance = instance[attr]
        else:
            instance = getattr(instance, attr)

        if is_simple_callable(instance):
            try:
                instance = instance()
            except (AttributeError, KeyError) as exc:
                # If we raised an Attribute or KeyError here it'd get treated
                # as an omitted field in `Field.get_attribute()`. Instead we
                # raise a ValueError to ensure the exception is not masked.
                raise ValueError('Exception raised in callable attribute "{0}"; '
                                 'original exception was: {1}'.format(attr, exc))

    return instance


def convert_asyncio_task(method):
    """
    解决tornado中使用aiohttp的ClientSession出现异常：
        Timeout context manager should be used inside a task
    :param method:
    :return:
    """
    @functools.wraps(method)
    async def wrapper(self, *args, **kwargs):
        coro = method(self, *args, **kwargs)
        return await asyncio.ensure_future(coro)
    return wrapper
