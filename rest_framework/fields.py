# -*- coding: utf-8 -*-
import collections
import copy
import datetime
import inspect
import json
import re
import uuid
import logging

from rest_framework.exceptions import ValidationError
from rest_framework.helpers import functional
from rest_framework.validators import MaxLengthValidator, MinLengthValidator, EmailValidator, RegexValidator, \
    URLValidator, IPAddressValidator, MaxValueValidator, MinValueValidator

__author__ = 'caowenbin'

__all__ = [
    'empty', 'Field', 'BooleanField', 'NullBooleanField', 'CharField', 'EmailField',
    'RegexField', 'URLField', 'UUIDField', 'IPAddressField',
    'IntegerField', 'FloatField', 'DateTimeField', 'DateField',
    'TimeField',  'ChoiceField', 'MultipleChoiceField',  '_UnvalidatedField', 'ListField', 'JSONField'
]
rest_log = logging.getLogger("tornado.rest_framework")
empty = object()

REGEX_TYPE = type(re.compile(''))

NOT_REQUIRED_DEFAULT = '不能同时设置`required` 和 `default`'


class Field(object):
    # 这个主要用于字段顺序跟定义的顺序一致
    _creation_counter = 0
    default_validators = []

    def __init__(self, verbose_name=None, required=True, default=None, source=None, error_messages=None,
                 validators=None, null=False, read_only=False,):
        """
        :param verbose_name: 字段注释名
        :param required: 参数是否必传,默认必传
        :param default: 默认值，可以是固定值或函数方法
        :param source: 来源
        :param error_messages: 错误信息
        :param validators: 检查方法
        :param null: 值是否可以为None，默认不允许，True代表允许
        :param read_only: 只读  默认为False(可选)
        """
        self._creation_counter = Field._creation_counter
        Field._creation_counter += 1
        if null is True:
            required = False

        # 如果赋予默认值，则required自动转为False
        if default is not None:
            required = False

        assert not (required and default is not None), NOT_REQUIRED_DEFAULT
        assert isinstance(error_messages, (dict, type(None))), "error_messages type must dict"
        assert isinstance(validators, (list, tuple, set, type(None))), "validators type must list or tuple"
        self.verbose_name = verbose_name
        self.required = required
        self.default = default
        self.source = source
        self.null = null
        self.read_only = read_only
        self._validators = []

        if validators is not None:
            self.validators = validators[:]

        # These are set up by `.bind()` when the field is added to a serializer.
        self.field_name = None
        self.parent = None

        messages = {"required": "此字段为必选字段", "null": "不能为空"}
        for cls in reversed(self.__class__.__mro__):
            messages.update(getattr(cls, 'default_error_messages', {}))

        messages.update(error_messages or {})
        self.error_messages = messages

    def bind(self, field_name, parent):
        """
        Initializes the field name and parent for the field instance.
        Called when a field is added to the parent serializer instance.
        """

        # In order to enforce a consistent style, we error if a redundant
        # 'source' argument has been used. For example:
        # my_field = serializer.CharField(source='my_field')
        assert self.source != field_name, (
            "It is redundant to specify `source='%s'` on field '%s' in "
            "serializer '%s', because it is the same as the field name. "
            "Remove the `source` keyword argument." %
            (field_name, self.__class__.__name__, parent.__class__.__name__)
        )

        self.field_name = field_name
        self.parent = parent

        # self.source should default to being the same as the field name.
        if self.source is None:
            self.source = field_name

        # self.source_attrs is a list of attributes that need to be looked up
        # when serializing the instance, or populating the validated data.
        if self.source == '*':
            self.source_attrs = []
        else:
            self.source_attrs = self.source.split('.')

    @property
    def validators(self):
        if not hasattr(self, '_validators'):
            self._validators = self.get_validators()
        return self._validators

    @validators.setter
    def validators(self, validators):
        self._validators = validators

    def get_validators(self):
        return self.default_validators[:]

    def get_value(self, dictionary):
        """
        从表单获取此字段的值
        :param dictionary:
        :return:
        """
        return dictionary.get(self.field_name, empty)

    # def get_attribute(self, instance):
    #     """
    #     Given the *outgoing* object instance, return the primitive value
    #     that should be used for this field.
    #     """
    #     try:
    #         return get_attribute(instance, self.source_attrs)
    #     except (KeyError, AttributeError) as exc:
    #         if self.default is not empty:
    #             return self.get_default()
    #         if not self.required:
    #             raise SkipField()
    #         msg = (
    #             'Got {exc_type} when attempting to get a value for field '
    #             '`{field}` on serializer `{serializer}`.\nThe serializer '
    #             'field might be named incorrectly and not match '
    #             'any attribute or key on the `{instance}` instance.\n'
    #             'Original exception text was: {exc}.'.format(
    #                 exc_type=type(exc).__name__,
    #                 field=self.field_name,
    #                 serializer=self.parent.__class__.__name__,
    #                 instance=instance.__class__.__name__,
    #                 exc=exc
    #             )
    #         )
    #         raise type(exc)(msg)

    def get_default(self):
        """
        字段默认值
        :return:
        """
        if callable(self.default):
            if hasattr(self.default, 'set_context'):
                self.default.set_context(self)
            value = self.default()
        else:
            value = self.default

        if value is None:
            default_method_name = 'gen_{field_name}'.format(field_name=self.field_name)
            if hasattr(self.parent, default_method_name):
                value = getattr(self.parent, default_method_name)()

        if value is None and not self.null:
            self.fail('null')

        return value

    def validate_empty_values(self, data):
        """
        检查字段是否有值
        """
        if data is empty:
            if self.required:
                self.fail('required')

            return True, self.get_default()

        if data is None:
            if not self.null:
                self.fail('null')

            return True, None

        return False, data

    def to_internal_value(self, data):
        raise NotImplementedError('`to_internal_value()` must be implemented.')

    def run_validation(self, data=empty):
        """
        执行约束条件或约束方法
        :param data:
        :return:
        """
        is_empty_value, data = self.validate_empty_values(data)

        if is_empty_value:
            return data

        value = self.to_internal_value(data)
        self.run_validators(value)

        return value

    def run_validators(self, value):
        """
        约束方法检查
        :param value:
        :return:
        """
        errors = []
        for validator in self.validators:
            if hasattr(validator, 'set_context'):
                validator.set_context(self)

            try:
                validator(value)
            except ValidationError as exc:
                errors.extend(exc.detail)

        if errors:
            raise ValidationError(errors)

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

    def fail(self, key, **kwargs):
        try:
            msg = self.error_messages[key]
        except KeyError:
            msg = "self.error_messages没有找到{key}".format(key=key)
            raise AssertionError(msg)

        message_string = msg.format(**kwargs)

        raise ValidationError(message_string, code=key)

    # @property
    # def root(self):
    #     """
    #     Returns the top-level serializer for this field.
    #     """
    #     root = self
    #     while root.parent is not None:
    #         root = root.parent
    #     return root

    # @property
    # def context(self):
    #     """
    #     Returns the context as passed to the root serializer on initialization.
    #     """
    #     return getattr(self.root, '_context', {})

    def __new__(cls, *args, **kwargs):
        """
        When a field is instantiated, we store the arguments that were used,
        so that we can present a helpful representation of the object.
        """
        instance = super(Field, cls).__new__(cls)
        instance._args = args
        instance._kwargs = kwargs
        return instance

    def __deepcopy__(self, memo):
        """
        When cloning fields we instantiate using the arguments it was
        originally created with, rather than copying the complete state.
        """
        args = [
            copy.deepcopy(item) if not isinstance(item, REGEX_TYPE) else item
            for item in self._args
        ]
        kwargs = {
            key: (copy.deepcopy(value) if (key not in ('validators', 'regex')) else value)
            for key, value in self._kwargs.items()
        }
        return self.__class__(*args, **kwargs)

    def __repr__(self):
        return "{source_name}={class_name}(*{arg_string}, **{kwarg_string})".format(
            source_name=self.source,
            class_name=self.__class__.__name__,
            arg_string=str(self._args),
            kwarg_string=str(self._kwargs)
        )


class BooleanField(Field):
    """
    布尔型
    """
    default_error_messages = {
        'invalid': '"{input}"不是有效Boolean类型值'
    }
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

    def __init__(self, *args, **kwargs):
        assert 'null' not in kwargs, '`null` is not a valid option. Use `NullBooleanField` instead.'
        super(BooleanField, self).__init__(*args, **kwargs)

    def to_internal_value(self, data):
        try:
            if data in self.TRUE_VALUES:
                return True
            elif data in self.FALSE_VALUES:
                return False
        except TypeError:
            pass
        self.fail('invalid', input=data)

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
    default_error_messages = {
        'invalid': '"{input}" 不是有效Boolean类型值'
    }
    TRUE_VALUES = {'t', 'T', 'true', 'True', 'TRUE', '1', 1, True}
    FALSE_VALUES = {'f', 'F', 'false', 'False', 'FALSE', '0', 0, 0.0, False}
    NULL_VALUES = {'n', 'N', 'null', 'Null', 'NULL', '', None}

    def __init__(self, *args, **kwargs):
        assert 'null' not in kwargs, '`null` is not a valid option.'
        kwargs['null'] = True
        super(NullBooleanField, self).__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if data in self.TRUE_VALUES:
            return True
        elif data in self.FALSE_VALUES:
            return False
        elif data in self.NULL_VALUES:
            return None
        self.fail('invalid', input=data)

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
    default_error_messages = {
        'invalid': '请输入一个有效的字符串',
    }

    def __init__(self, *args, **kwargs):
        # 是否去掉两边的空白符
        self.trim_whitespace = kwargs.pop('trim_whitespace', True)
        self.max_length = kwargs.pop('max_length', None)
        self.min_length = kwargs.pop('min_length', None)
        null = kwargs.get("null", False)
        assert not (null is True and self.min_length not in (None, 0)), "不能同时设置`null`和`min_length`"
        super(CharField, self).__init__(*args, **kwargs)

        if self.max_length is not None:
            self.validators.append(MaxLengthValidator(self.max_length))

        if self.min_length is not None:
            self.validators.append(MinLengthValidator(self.min_length))

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, (str, int, float,)):
            self.fail('invalid')

        value = str(data)

        return value.strip() if self.trim_whitespace else value

    def to_representation(self, value):
        return str(value)


class EmailField(CharField):
    """
    邮箱字段类型
    """
    default_error_messages = {
        'invalid': '请输入有效的电子邮箱地址'
    }

    def __init__(self, *args, **kwargs):
        super(EmailField, self).__init__(*args, **kwargs)
        self.validators.append(EmailValidator())


class RegexField(CharField):
    """
    正则表达式字段类型
    """
    default_error_messages = {
        'invalid': '该值与所需的模式不匹配.'
    }

    def __init__(self, regex, *args, **kwargs):
        super(RegexField, self).__init__(*args, **kwargs)
        validator = RegexValidator(regex=regex, message=self.error_messages['invalid'])
        self.validators.append(validator)


class URLField(CharField):
    """
    url字段类型
    """
    default_error_messages = {
        'invalid': '请输入一个有效的URL'
    }

    def __init__(self, *args, **kwargs):
        super(URLField, self).__init__(*args, **kwargs)
        self.validators.append(URLValidator(message=self.error_messages['invalid']))


class UUIDField(Field):
    """
    uuid类型字段
    """
    valid_formats = ('hex_verbose', 'hex', 'int', 'urn')

    default_error_messages = {
        'invalid': '"{value}"不是一个有效的UUID类型值.'
    }

    def __init__(self, *args, **kwargs):
        self.uuid_format = kwargs.pop('format', 'hex_verbose')
        if self.uuid_format not in self.valid_formats:
            raise ValueError(
                'Invalid format for uuid representation. '
                'Must be one of "{0}"'.format('", "'.join(self.valid_formats))
            )
        super(UUIDField, self).__init__(*args, **kwargs)

    def to_internal_value(self, data):

        if not isinstance(data, uuid.UUID):
            try:
                if isinstance(data, int):
                    return uuid.UUID(int=data)
                elif isinstance(data, str):
                    return uuid.UUID(hex=data)
                else:
                    self.fail('invalid', value=data)
            except ValueError:
                self.fail('invalid', value=data)
        return data

    def to_representation(self, value):
        if value is None:
            return None

        if self.uuid_format == 'hex_verbose':
            return str(value)
        else:
            return getattr(value, self.uuid_format)


class IPAddressField(CharField):
    """IP地址字段，包括ipv4或ipv6"""

    default_error_messages = {
        'invalid': '输入一个有效的ipv4或ipv6地址.'
    }

    def __init__(self, protocol='both', *args, **kwargs):
        """
        :param protocol: ip地址类型 both（包括ipv4、ipv6）、ipv4、ipv6
        :param kwargs:
        """
        self.protocol = protocol.lower()
        super(IPAddressField, self).__init__(*args, **kwargs)
        self.validators.append(IPAddressValidator(self.protocol))


class IntegerField(Field):
    """
    整型字段
    """
    default_error_messages = {
        'invalid': '请输入一个有效的整数',
        'max_value': '不能超过{max_value}.',
        'min_value': '不能小于{min_value}.',
        'max_string_length': '字符串整型值过长'
    }
    MAX_STRING_LENGTH = 1000
    re_decimal = re.compile(r'\.0*\s*$')

    def __init__(self, *args, **kwargs):
        null = kwargs.get("null", False)
        assert null is False, "`null`必须设为False"
        self.max_value = kwargs.pop('max_value', None)
        self.min_value = kwargs.pop('min_value', None)
        super(IntegerField, self).__init__(*args, **kwargs)

        if self.max_value is not None:
            message = self.error_messages['max_value'].format(max_value=self.max_value)
            self.validators.append(MaxValueValidator(self.max_value, message=message))

        if self.min_value is not None:
            message = self.error_messages['min_value'].format(min_value=self.min_value)
            self.validators.append(MinValueValidator(self.min_value, message=message))

    def to_internal_value(self, data):
        if isinstance(data, bool):
            return int(data)

        if isinstance(data, str) and len(data) > self.MAX_STRING_LENGTH:
            self.fail('max_string_length')

        try:
            data = int(self.re_decimal.sub('', str(data)))
        except (ValueError, TypeError):
            self.fail('invalid')
        return data

    def to_representation(self, value):
        return int(value)


class FloatField(Field):
    """
    浮点型
    """
    default_error_messages = {
        'invalid': '请输入一个有效的浮点型值',
        'max_value': '不能超过{max_value}.',
        'min_value': '不能小于{min_value}.',
        'max_string_length': '字符串数值过长'
    }
    MAX_STRING_LENGTH = 1000

    def __init__(self, *args, **kwargs):
        null = kwargs.get("null", False)
        assert null is False, "`null`必须设为False"
        self.max_value = kwargs.pop('max_value', None)
        self.min_value = kwargs.pop('min_value', None)
        super(FloatField, self).__init__(*args, **kwargs)

        if self.max_value is not None:
            message = self.error_messages['max_value'].format(max_value=self.max_value)
            self.validators.append(MaxValueValidator(self.max_value, message=message))

        if self.min_value is not None:
            message = self.error_messages['min_value'].format(min_value=self.min_value)
            self.validators.append(MinValueValidator(self.min_value, message=message))

    def to_internal_value(self, data):

        if isinstance(data, str) and len(data) > self.MAX_STRING_LENGTH:
            self.fail('max_string_length')

        try:
            return float(data)
        except (TypeError, ValueError):
            self.fail('invalid')

    def to_representation(self, value):
        return float(value)


class DateTimeField(Field):

    default_error_messages = {
        'invalid': 'Datetime has wrong format. Use one of these formats instead: {format}.',
    }
    datetime_parser = datetime.datetime.strptime

    def __init__(self, output_format="%Y-%m-%d %H:%M:%S", input_formats="%Y-%m-%d %H:%M:%S", *args, **kwargs):
        self.output_format = output_format
        self.input_formats = input_formats
        super(DateTimeField, self).__init__(*args, **kwargs)

    def to_internal_value(self, value):
        if value is None:
            return value

        if isinstance(value, datetime.datetime):
            return value

        if isinstance(value, datetime.date):
            value = datetime.datetime(value.year, value.month, value.day)
            return value

        try:
            value = self.datetime_parser(value, self.input_formats)
            return value
        except (ValueError, TypeError):
            self.fail('invalid', format=self.input_formats)

    def to_representation(self, value):
        if not value:
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        return value.strftime(self.output_format)


class DateField(Field):
    default_error_messages = {
        'invalid': 'Date has wrong format. Use one of these formats instead: {format}.',
    }
    datetime_parser = datetime.datetime.strptime

    def __init__(self, output_format="%Y-%m-%d", input_formats="%Y-%m-%d", *args, **kwargs):
        self.output_format = output_format
        self.input_formats = input_formats
        super(DateField, self).__init__(*args, **kwargs)

    def to_internal_value(self, value):
        if value is None:
            return value

        if isinstance(value, datetime.datetime):
            value = datetime.date(value.year, value.month, value.day)
            return value

        if isinstance(value, datetime.date):
            return value

        try:
            value = self.datetime_parser(value, self.input_formats)
            return value.date()
        except (ValueError, TypeError):
            self.fail('invalid', format=self.input_formats)

    def to_representation(self, value):
        if not value:
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        return value.strftime(self.output_format)


class TimeField(Field):
    default_error_messages = {
        'invalid': 'Time has wrong format. Use one of these formats instead: {format}.',
    }
    datetime_parser = datetime.datetime.strptime

    def __init__(self, output_format="%H:%M:%S", input_formats="%H:%M:%S", *args, **kwargs):
        self.output_format = output_format
        self.input_formats = input_formats
        super(TimeField, self).__init__(*args, **kwargs)

    def to_internal_value(self, value):
        if value is None:
            return value

        if isinstance(value, datetime.datetime):
            return value.time()

        if isinstance(value, datetime.time):
            return value

        try:
            parsed = self.datetime_parser(value, self.input_formats)
            return parsed.time()
        except (ValueError, TypeError) as e:
            rest_log.error(e)
            self.fail('invalid', format=self.input_formats)

    def to_representation(self, value):
        if value in (None, ''):
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        return value.strftime(self.output_format)


class ChoiceField(Field):
    """
    选项字段类型
    """
    default_error_messages = {
        'invalid_choice': "'{input}'不在选项（{choices}）中"
    }

    def __init__(self, choices, *args, **kwargs):
        self.grouped_choices = functional.to_choices_dict(choices)
        self.choices = functional.flatten_choices_dict(self.grouped_choices)
        self.choice_strings_to_values = {str(key): key for key in self.choices.keys()}
        super(ChoiceField, self).__init__(*args, **kwargs)

    def to_internal_value(self, data):
        try:
            return self.choice_strings_to_values[str(data)]
        except KeyError:
            choices = ', '.join(self.choice_strings_to_values.keys())
            self.fail(key='invalid_choice', input=data, choices=choices)

    def to_representation(self, value):
        if value in ('', None):
            return value
        return self.choice_strings_to_values.get(str(value), value)


class MultipleChoiceField(ChoiceField):
    """
    多选
    """
    default_error_messages = {
        'invalid_choice': '"{input}" is not a valid choice.',
        'not_a_list': 'Expected a list of items but got type "{input_type}".',
        'empty': 'This selection may not be empty.'
    }

    def __init__(self, *args, **kwargs):
        self.allow_empty = kwargs.pop('allow_empty', True)
        super(MultipleChoiceField, self).__init__(*args, **kwargs)

    # def get_value(self, dictionary):
    #     # if self.field_name not in dictionary:
    #     #     if getattr(self.root, 'partial', False):
    #     #         return empty
    #     return dictionary.get(self.field_name, empty)

    def to_internal_value(self, data):
        if isinstance(data, type('')) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')

        return {
            super(MultipleChoiceField, self).to_internal_value(item)
            for item in data
        }

    def to_representation(self, value):
        return {
            self.choice_strings_to_values.get(str(item), item) for item in value
        }


class _UnvalidatedField(Field):
    def __init__(self, *args, **kwargs):
        super(_UnvalidatedField, self).__init__(*args, **kwargs)
        self.allow_blank = True
        self.allow_null = True

    def to_internal_value(self, data):
        return data

    def to_representation(self, value):
        return value


class ListField(Field):

    child = _UnvalidatedField()
    default_error_messages = {
        'not_a_list': 'Expected a list of items but got type "{input_type}".',
        'empty': 'This list may not be empty.',
        'min_length': 'Ensure this field has at least {min_length} elements.',
        'max_length': 'Ensure this field has no more than {max_length} elements.'
    }

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        self.allow_empty = kwargs.pop('allow_empty', True)
        self.max_length = kwargs.pop('max_length', None)
        self.min_length = kwargs.pop('min_length', None)

        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        assert self.child.source is None, (
            "The `source` argument is not meaningful when applied to a `child=` field. "
            "Remove `source=` from the field declaration."
        )

        super(ListField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)
        if self.max_length is not None:
            message = self.error_messages['max_length'].format(max_length=self.max_length)
            self.validators.append(MaxLengthValidator(self.max_length, message=message))
        if self.min_length is not None:
            message = self.error_messages['min_length'].format(min_length=self.min_length)
            self.validators.append(MinLengthValidator(self.min_length, message=message))

    def get_value(self, dictionary):
        if self.field_name not in dictionary:
            if getattr(self.root, 'partial', False):
                return empty

        return dictionary.get(self.field_name, empty)

    def to_internal_value(self, data):
        """
        List of dicts of native values <- List of dicts of primitive datatypes.
        """
        if isinstance(data, type('')) or isinstance(data, collections.Mapping) or not hasattr(data, '__iter__'):
            self.fail('not_a_list', input_type=type(data).__name__)
        if not self.allow_empty and len(data) == 0:
            self.fail('empty')
        return [self.child.run_validation(item) for item in data]

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        return [self.child.to_representation(item) if item is not None else None for item in data]


class JSONField(Field):
    """
    JSON字段类型
    """
    default_error_messages = {
        'invalid': 'Value must be valid JSON.'
    }

    def __init__(self, *args, **kwargs):
        # 二进制的
        self.binary = kwargs.pop('binary', False)
        super(JSONField, self).__init__(*args, **kwargs)

    def get_value(self, dictionary):
        return dictionary.get(self.field_name, empty)

    def to_internal_value(self, data):
        try:
            if self.binary or getattr(data, 'is_json_string', False):
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                return json.loads(data)
            else:
                json.dumps(data)
        except (TypeError, ValueError):
            self.fail('invalid')

        return data

    def to_representation(self, value):
        if self.binary:
            value = json.dumps(value)
            if isinstance(value, str):
                value = bytes(value.encode('utf-8'))
        return value
