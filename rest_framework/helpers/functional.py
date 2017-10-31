# -*- coding: utf-8 -*-
import sys
from importlib import import_module
from collections import OrderedDict, MutableMapping
__author__ = 'caowenbin'


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
    Similar to Python's built in `dictionary[key] = value`,
    but takes a list of nested keys instead of a single key.

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


def load_object(object_path):
    """
    根据字符串对象路径加载对象
    :param object_path:
    :return:
    """
    if object_path is None:
        return object_path
    elif callable(object_path):
        return object_path

    try:
        dot = object_path.rindex('.')
    except ValueError:
        raise ValueError("Error loading object '%s': not a full path" % object_path)

    module_path, name = object_path[:dot], object_path[dot+1:]

    try:
        module = import_module(module_path)
        return getattr(module, name)
    except (ImportError, AttributeError):
        raise ImportError("Module '%s' doesn't define any object named '%s'" % (module_path, name))


def to_choices_dict(choices):
    """
    Convert choices into key/value dicts.

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
    Convert a group choices dict into a flat dict of choices.

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


def import_class_attribute(dotted_path):
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError:
        msg = "%s doesn't look like a module path" % dotted_path
        reraise(ImportError, ImportError(msg), sys.exc_info()[2])

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError:
        msg = 'Module "%s" does not define a "%s" attribute/class' % (
            module_path, class_name)
        reraise(ImportError, ImportError(msg), sys.exc_info()[2])


# class ReturnDict(OrderedDict):
#     """
#     返回字典结构的序列化数据
#     """
#
#     def __init__(self, *args, **kwargs):
#         self.serializer = kwargs.pop('serializer')
#         super(ReturnDict, self).__init__(*args, **kwargs)
#
#     def copy(self):
#         return ReturnDict(self, serializer=self.serializer)
#
#     def __repr__(self):
#         return dict.__repr__(self)
#
#     def __reduce__(self):
#         return dict, (dict(self),)


# class ReturnList(list):
#     """
#     返回列表结构的序列化数据
#     """
#
#     def __init__(self, *args, **kwargs):
#         self.serializer = kwargs.pop('serializer')
#         super(ReturnList, self).__init__(*args, **kwargs)
#
#     def __repr__(self):
#         return list.__repr__(self)
#
#     def __reduce__(self):
#         return list, (list(self),)


class BindingDict(MutableMapping):
    """
    这字典对象用于在串行存储领域。
    这样可以确保每当将字段添加到我们所调用的序列化程序时，
    `field.bind()`使`field_name` 和 `parent` 属性可以正确设置
    """

    def __init__(self, form_serializer):
        """

        :param form_serializer: 可能是表单类或序列类
        """
        self.form_serializer = form_serializer
        self.fields = OrderedDict()

    def __setitem__(self, key, field):
        self.fields[key] = field
        field.bind(field_name=key, parent=self.form_serializer)

    def __getitem__(self, key):
        return self.fields[key]

    def __delitem__(self, key):
        del self.fields[key]

    def __iter__(self):
        return iter(self.fields)

    def __len__(self):
        return len(self.fields)

    def __repr__(self):
        return dict.__repr__(self.fields)
