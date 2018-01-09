# -*- coding: utf-8 -*-
import re
import logging
from collections import Mapping

from rest_framework.utils.functional import is_simple_callable

__author__ = 'caowenbin'

__all__ = [
    'Field', 'BooleanField', 'NullBooleanField', 'CharField', 'UUIDField',
    'IntegerField', 'FloatField', 'DateTimeField', 'DateField', 'TimeField'
]
rest_log = logging.getLogger("tornado.rest_framework")
empty = object()

REGEX_TYPE = type(re.compile(''))


class Field(object):
    creation_counter = 0

    def __init__(self, verbose_name=None, source=None):
        """
        :param verbose_name: 字段注释名
        :param source: 来源
        """
        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1
        self.verbose_name = verbose_name
        self.source = source
        self.field_name = None
        self.parent = None

    def bind(self, field_name, parent):
        """
        Initializes the field name and parent for the field instance.
        Called when a field is added to the parent serializer instance.
        """

        self.field_name = field_name
        self.parent = parent

        # self.source should default to being the same as the field name.
        if self.source is None:
            self.source = field_name

        if self.source == '*':
            self.source_attrs = []
        else:
            self.source_attrs = self.source.split('.')

    def to_representation(self, value):
        """
        Transform the *outgoing* native value into primitive data.
        """
        raise NotImplementedError(
            '{cls}.to_representation() must be implemented for field '
            '{field_name}. If you do not need to support write operations '
            'you probably want to subclass `ReadOnlyField` instead.'.format(
                cls=self.__class__.__name__,
                field_name=self.field_name,
            )
        )

    def get_attribute(self, instance):
        """
        从对象获得最原始的值
        :param instance:
        :return:
        """
        if instance is None:
            return None

        for attr in self.source_attrs:
            if isinstance(instance, Mapping):
                instance = instance.get(attr, None)
            else:
                instance = getattr(instance, attr, None)

            if instance is None:
                return None

            if is_simple_callable(instance):
                instance = instance()

        return instance

    # def __new__(cls, *args, **kwargs):
    #     instance = super(Field, cls).__new__(cls)
    #     instance._args = args
    #     instance._kwargs = kwargs
    #     return instance
    #
    # def __deepcopy__(self, memo):
    #     args = [
    #         copy.deepcopy(item) if not isinstance(item, REGEX_TYPE) else item
    #         for item in self._args
    #     ]
    #     kwargs = {
    #         key: (copy.deepcopy(value) if (key not in ('validators', 'regex')) else value)
    #         for key, value in self._kwargs.items()
    #     }
    #     return self.__class__(*args, **kwargs)
    #
    # def __repr__(self):
    #     return "{source_name}={class_name}(*{arg_string}, **{kwarg_string})".format(
    #         source_name=self.source,
    #         class_name=self.__class__.__name__,
    #         arg_string=str(self._args),
    #         kwarg_string=str(self._kwargs)
    #     )


class BooleanField(Field):
    """
    布尔型
    """
    TRUE_VALUES = {
        't', 'T',
        'y', 'Y', 'yes', 'YES',
        'true', 'True', 'TRUE',
        'on', 'On', 'ON',
        '1', 1,
        True
    }
    FALSE_VALUES = {
        'f', 'F',
        'n', 'N', 'no', 'NO',
        'false', 'False', 'FALSE',
        'off', 'Off', 'OFF',
        '0', 0, 0.0,
        False
    }

    def to_representation(self, value):
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        return bool(value)


class NullBooleanField(Field):
    """
    可以为None的布尔型
    """
    TRUE_VALUES = {'t', 'T', 'true', 'True', 'TRUE', '1', 1, True}
    FALSE_VALUES = {'f', 'F', 'false', 'False', 'FALSE', '0', 0, 0.0, False}
    NULL_VALUES = {'n', 'N', 'null', 'Null', 'NULL', '', None}

    def __init__(self, *args, **kwargs):
        assert 'null' not in kwargs, '`null` is not a valid option.'
        kwargs['null'] = True
        super(NullBooleanField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if value in self.NULL_VALUES:
            return None
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        return bool(value)


class CharField(Field):
    """
    字符串类型
    """

    def to_representation(self, value):
        return str(value)


class UUIDField(Field):
    """
    uuid类型字段
    """
    valid_formats = ('hex_verbose', 'hex', 'int', 'urn')

    def __init__(self, *args, **kwargs):
        self.uuid_format = kwargs.pop('format', 'hex_verbose')
        if self.uuid_format not in self.valid_formats:
            raise ValueError(
                'Invalid format for uuid representation. '
                'Must be one of "{0}"'.format('", "'.join(self.valid_formats))
            )
        super(UUIDField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if value is None:
            return None

        if self.uuid_format == 'hex_verbose':
            return str(value)
        else:
            return getattr(value, self.uuid_format)


class IntegerField(Field):
    """
    整型字段
    """

    def to_representation(self, value):
        return int(value)


class FloatField(Field):
    """
    浮点型
    """

    def to_representation(self, value):
        return float(value)


class BaseTemporalField(Field):

    def __init__(self, output_format, *args, **kwargs):
        super(BaseTemporalField, self).__init__(*args, **kwargs)
        self.output_format = output_format

    def to_representation(self, value):
        if not value:
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        return value.strftime(self.output_format)


class DateTimeField(BaseTemporalField):
    def __init__(self, output_format="%Y-%m-%d %H:%M:%S", *args, **kwargs):
        super(DateTimeField, self).__init__(output_format, *args, **kwargs)


class DateField(BaseTemporalField):
    def __init__(self, output_format="%Y-%m-%d", *args, **kwargs):
        super(DateField, self).__init__(output_format, *args, **kwargs)


class TimeField(BaseTemporalField):
    """
    时间字段 时：分：秒
    """
    def __init__(self, output_format="%H:%M:%S", *args, **kwargs):
        super(TimeField, self).__init__(output_format, *args, **kwargs)


# class _UnvalidatedField(Field):
#     def __init__(self, *args, **kwargs):
#         super(_UnvalidatedField, self).__init__(*args, **kwargs)
#         self.allow_blank = True
#         self.allow_null = True
#
#     def to_python(self, data):
#         return data
#
#     def to_representation(self, value):
#         return value

#
# class ListField(Field):
#
#     child = _UnvalidatedField()
#     default_error_messages = {
#         'not_a_list': 'Expected a list of items but got type "{input_type}".',
#         'empty': 'This list may not be empty.',
#         'min_length': 'Ensure this field has at least {min_length} elements.',
#         'max_length': 'Ensure this field has no more than {max_length} elements.'
#     }
#
#     def __init__(self, *args, **kwargs):
#         self.child = kwargs.pop('child', copy.deepcopy(self.child))
#         self.allow_empty = kwargs.pop('allow_empty', True)
#         self.max_length = kwargs.pop('max_length', None)
#         self.min_length = kwargs.pop('min_length', None)
#
#         assert not inspect.isclass(self.child), '`child` has not been instantiated.'
#         assert self.child.source is None, (
#             "The `source` argument is not meaningful when applied to a `child=` field. "
#             "Remove `source=` from the field declaration."
#         )
#
#         super(ListField, self).__init__(*args, **kwargs)
#         self.child.bind(field_name='', parent=self)
#
#         if self.min_length is not None:
#             message = self.error_messages['min_length'].format(min_length=self.min_length)
#             self.validators.append(validators.MinLengthValidator(self.min_length, message=message))
#
#         if self.max_length is not None:
#             message = self.error_messages['max_length'].format(max_length=self.max_length)
#             self.validators.append(validators.MaxLengthValidator(self.max_length, message=message))
#
#     def get_value(self, dictionary):
#         if self.field_name not in dictionary:
#             if getattr(self.root, 'partial', False):
#                 return empty
#
#         return dictionary.get(self.field_name, empty)
#
#     def to_python(self, data):
#         """
#         List of dicts of native values <- List of dicts of primitive datatypes.
#         """
#         if isinstance(data, type('')) or isinstance(data, Mapping) or not hasattr(data, '__iter__'):
#             self.fail('not_a_list', input_type=type(data).__name__)
#         if not self.allow_empty and len(data) == 0:
#             self.fail('empty')
#         return [self.child.resolve_validation_data(item) for item in data]
#
#     def to_representation(self, data):
#         """
#         List of object instances -> List of dicts of primitive datatypes.
#         """
#         return [self.child.to_representation(item) if item is not None else None for item in data]
#
#
# class JSONField(Field):
#     """
#     JSON字段类型
#     """
#     default_error_messages = {
#         'invalid': 'Value must be valid JSON.'
#     }
#
#     def __init__(self, *args, **kwargs):
#         # 二进制的
#         self.binary = kwargs.pop('binary', False)
#         super(JSONField, self).__init__(*args, **kwargs)
#
#     def get_value(self, dictionary):
#         return dictionary.get(self.field_name, empty)
#
#     def to_python(self, data):
#         try:
#             if self.binary or getattr(data, 'is_json_string', False):
#                 if isinstance(data, bytes):
#                     data = data.decode('utf-8')
#                 return json.loads(data)
#             else:
#                 json.dumps(data)
#         except (TypeError, ValueError):
#             self.fail('invalid')
#
#         return data
#
#     def to_representation(self, value):
#         if self.binary:
#             value = json.dumps(value)
#             if isinstance(value, str):
#                 value = bytes(value.encode('utf-8'))
#         return value
