# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import collections
import copy
import datetime
import decimal
import inspect
import json
import re
import uuid
from collections import OrderedDict

from rest_framework.conf import settings
from rest_framework.exceptions import ValidationError, ObjectDoesNotExist
from rest_framework.helpers import six
from rest_framework.validators import MaxLengthValidator, MinLengthValidator

__author__ = 'caowenbin'

__all__ = [
    'Field', 'BooleanField', 'NullBooleanField', 'CharField', 'UUIDField',
    'IntegerField', 'FloatField', 'DateTimeField', 'DateField', 'TimeField',
    # 'DurationField', 'ChoiceField', 'MultipleChoiceField', 'FilePathField',
    # 'FileField', 'ImageField', '_UnvalidatedField', 'ListField', 'DictField', 'JSONField',
    'ReadOnlyField', 'HiddenField', 'SerializerMethodField', 'ModelField'
]

empty = object()


# if six.PY3:
#     def is_simple_callable(obj):
#         """
#         True if the object is a callable that takes no arguments.
#         """
#         if not (inspect.isfunction(obj) or inspect.ismethod(obj)):
#             return False
#
#         sig = inspect.signature(obj)
#         params = sig.parameters.values()
#         return all(
#             param.kind == param.VAR_POSITIONAL or
#             param.kind == param.VAR_KEYWORD or
#             param.default != param.empty
#             for param in params
#         )
#
# else:
#     def is_simple_callable(obj):
#         function = inspect.isfunction(obj)
#         method = inspect.ismethod(obj)
#
#         if not (function or method):
#             return False
#
#         if method:
#             is_unbound = obj.im_self is None
#
#         args, _, _, defaults = inspect.getargspec(obj)
#
#         len_args = len(args) if function or is_unbound else len(args) - 1
#         len_defaults = len(defaults) if defaults else 0
#         return len_args <= len_defaults


def get_attribute(instance, attrs):
    """
    Similar to Python's built in `getattr(instance, attr)`,
    but takes a list of nested attributes, instead of a single attribute.

    Also accepts either attribute lookup on objects or dictionary lookups.
    """
    for attr in attrs:
        if instance is None:
            # Break out early if we get `None` at any point in a nested lookup.
            return None
        try:
            if isinstance(instance, collections.Mapping):
                instance = instance[attr]
            else:
                instance = getattr(instance, attr)
        except ObjectDoesNotExist:
            return None
        # if is_simple_callable(instance):
        #     try:
        #         instance = instance()
        #     except (AttributeError, KeyError) as exc:
        #         # If we raised an Attribute or KeyError here it'd get treated
        #         # as an omitted field in `Field.get_attribute()`. Instead we
        #         # raise a ValueError to ensure the exception is not masked.
        #         raise ValueError('Exception raised in callable attribute "{0}"; original exception was: {1}'.format(attr, exc))

    return instance


# def set_value(dictionary, keys, value):
#     """
#     Similar to Python's built in `dictionary[key] = value`,
#     but takes a list of nested keys instead of a single key.
#
#     set_value({'a': 1}, [], {'b': 2}) -> {'a': 1, 'b': 2}
#     set_value({'a': 1}, ['x'], 2) -> {'a': 1, 'x': 2}
#     set_value({'a': 1}, ['x', 'y'], 2) -> {'a': 1, 'x': {'y': 2}}
#     """
#     if not keys:
#         dictionary.update(value)
#         return
#
#     for key in keys[:-1]:
#         if key not in dictionary:
#             dictionary[key] = {}
#         dictionary = dictionary[key]
#
#     dictionary[keys[-1]] = value
#

# def to_choices_dict(choices):
#     """
#     Convert choices into key/value dicts.
#
#     to_choices_dict([1]) -> {1: 1}
#     to_choices_dict([(1, '1st'), (2, '2nd')]) -> {1: '1st', 2: '2nd'}
#     to_choices_dict([('Group', ((1, '1st'), 2))]) -> {'Group': {1: '1st', 2: '2'}}
#     """
#     # Allow single, paired or grouped choices style:
#     # choices = [1, 2, 3]
#     # choices = [(1, 'First'), (2, 'Second'), (3, 'Third')]
#     # choices = [('Category', ((1, 'First'), (2, 'Second'))), (3, 'Third')]
#     ret = OrderedDict()
#     for choice in choices:
#         if not isinstance(choice, (list, tuple)):
#             # single choice
#             ret[choice] = choice
#         else:
#             key, value = choice
#             if isinstance(value, (list, tuple)):
#                 # grouped choices (category, sub choices)
#                 ret[key] = to_choices_dict(value)
#             else:
#                 # paired choice (key, display value)
#                 ret[key] = value
#     return ret

#
# def flatten_choices_dict(choices):
#     """
#     Convert a group choices dict into a flat dict of choices.
#
#     flatten_choices_dict({1: '1st', 2: '2nd'}) -> {1: '1st', 2: '2nd'}
#     flatten_choices_dict({'Group': {1: '1st', 2: '2nd'}}) -> {1: '1st', 2: '2nd'}
#     """
#     ret = OrderedDict()
#     for key, value in choices.items():
#         if isinstance(value, dict):
#             # grouped choices (category, sub choices)
#             for sub_key, sub_value in value.items():
#                 ret[sub_key] = sub_value
#         else:
#             # choice (key, display value)
#             ret[key] = value
#     return ret




# class CreateOnlyDefault(object):
#     """
#     This class may be used to provide default values that are only used
#     for create operations, but that do not return any value for update
#     operations.
#     """
#     def __init__(self, default):
#         self.default = default
#
#     def set_context(self, serializer_field):
#         self.is_update = serializer_field.parent.instance is not None
#         if callable(self.default) and hasattr(self.default, 'set_context') and not self.is_update:
#             self.default.set_context(serializer_field)
#
#     def __call__(self):
#         if self.is_update:
#             raise SkipField()
#         if callable(self.default):
#             return self.default()
#         return self.default
#
#     def __repr__(self):
#         return unicode_to_repr(
#             '%s(%s)' % (self.__class__.__name__, unicode_repr(self.default))
#         )


# class CurrentUserDefault(object):
#     def set_context(self, serializer_field):
#         self.user = serializer_field.context['request'].user
#
#     def __call__(self):
#         return self.user
#
#     def __repr__(self):
#         return unicode_to_repr('%s()' % self.__class__.__name__)


# class SkipField(Exception):
#     pass


# REGEX_TYPE = type(re.compile(''))



class Field(object):
    _creation_counter = 0
    initial = None

    def __init__(self, default=empty, initial=empty, source=None):
        """

        :param default: 默认值
        :param initial: 初始化值
        :param source: 数据来源
        """

        self._creation_counter = Field._creation_counter
        Field._creation_counter += 1
        self.default = default
        self.source = source
        self.initial = self.initial if (initial is empty) else initial
        # These are set up by `.bind()` when the field is added to a serializer.
        self.field_name = None
        self.parent = None

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

    # @property
    # def validators(self):
    #     if not hasattr(self, '_validators'):
    #         self._validators = self.get_validators()
    #     return self._validators
    #
    # @validators.setter
    # def validators(self, validators):
    #     self._validators = validators
    #
    # def get_validators(self):
    #     return self.default_validators[:]

    def get_initial(self):
        """
        Return a value to use when the field is being returned as a primitive
        value, without any object instance.
        """
        if callable(self.initial):
            return self.initial()
        return self.initial

    def get_value(self, dictionary):
        """
        Given the *incoming* primitive data, return the value for this field
        that should be validated and transformed to a native value.
        """
        return dictionary.get(self.field_name, empty)

    def get_attribute(self, instance):
        """
        Given the *outgoing* object instance, return the primitive value
        that should be used for this field.
        """
        try:
            return get_attribute(instance, self.source_attrs)
        except (KeyError, AttributeError) as exc:
            if self.default is not empty:
                return self.get_default()
            msg = (
                'Got {exc_type} when attempting to get a value for field '
                '`{field}` on serializer `{serializer}`.\nThe serializer '
                'field might be named incorrectly and not match '
                'any attribute or key on the `{instance}` instance.\n'
                'Original exception text was: {exc}.'.format(
                    exc_type=type(exc).__name__,
                    field=self.field_name,
                    serializer=self.parent.__class__.__name__,
                    instance=instance.__class__.__name__,
                    exc=exc
                )
            )
            raise type(exc)(msg)

    def get_default(self):
        """
        Return the default value to use when validating data if no input
        is provided for this field.

        If a default has not been set for this field then this will simply
        raise `SkipField`, indicating that no value should be set in the
        validated data for this field.
        """
        # if self.default is empty or getattr(self.root, 'partial', False):
        #     # No default, or this is a partial update.
        #     raise SkipField()
        if callable(self.default):
            if hasattr(self.default, 'set_context'):
                self.default.set_context(self)
            return self.default()
        return self.default

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


    # @property
    # def root(self):
    #     """
    #     Returns the top-level serializer for this field.
    #     """
    #     root = self
    #     while root.parent is not None:
    #         root = root.parent
    #     return root
    #
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
        # Treat regexes and validators as immutable.
        # See https://github.com/encode/django-rest-framework/issues/1954
        # and https://github.com/encode/django-rest-framework/pull/4489
        args = [
            copy.deepcopy(item) if not isinstance(item, REGEX_TYPE) else item
            for item in self._args
        ]
        kwargs = {
            key: (copy.deepcopy(value) if (key not in ('validators', 'regex')) else value)
            for key, value in self._kwargs.items()
        }
        return self.__class__(*args, **kwargs)


class BooleanField(Field):
    initial = False
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

    # def __init__(self, **kwargs):
    #     super(BooleanField, self).__init__(**kwargs)

    def to_representation(self, value):
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        return bool(value)


class NullBooleanField(Field):
    initial = None
    TRUE_VALUES = {'t', 'T', 'true', 'True', 'TRUE', '1', 1, True}
    FALSE_VALUES = {'f', 'F', 'false', 'False', 'FALSE', '0', 0, 0.0, False}
    NULL_VALUES = {'n', 'N', 'null', 'Null', 'NULL', '', None}

    # def __init__(self, **kwargs):
    #     super(NullBooleanField, self).__init__(**kwargs)

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
    initial = ''

    # def __init__(self, **kwargs):
    #     super(CharField, self).__init__(**kwargs)

    def to_representation(self, value):
        return str(value)


class UUIDField(Field):
    valid_formats = ('hex_verbose', 'hex', 'int', 'urn')

    def __init__(self, **kwargs):
        self.uuid_format = kwargs.pop('format', 'hex_verbose')
        if self.uuid_format not in self.valid_formats:
            raise ValueError(
                'Invalid format for uuid representation. '
                'Must be one of "{0}"'.format('", "'.join(self.valid_formats))
            )
        super(UUIDField, self).__init__(**kwargs)

    def to_representation(self, value):
        if self.uuid_format == 'hex_verbose':
            return str(value)
        else:
            return getattr(value, self.uuid_format)


class IntegerField(Field):
    def to_representation(self, value):
        return int(value)


class FloatField(Field):
    def to_representation(self, value):
        return float(value)


class DateTimeField(Field):
    def __init__(self, output_format="%Y-%m-%d %H:%M:%S", *args, **kwargs):
        self.output_format = output_format
        super(DateTimeField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        """
        序列化表示
        :param value:
        :return:
        """
        if not value:
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        return value.strftime(self.output_format)


class DateField(Field):
    def __init__(self, output_format="%Y-%m-%d", *args, **kwargs):
        self.output_format = output_format
        super(DateField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if not value:
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        assert not isinstance(value, datetime.datetime), (
            'Expected a `date`, but got a `datetime`. Refusing to coerce, '
            'as this may mean losing timezone information. Use a custom '
            'read-only field and deal with timezone issues explicitly.'
        )

        return value.strftime(self.output_format)


class TimeField(Field):

    def __init__(self, output_format="%H:%M:%S", *args, **kwargs):
        self.output_format = output_format
        super(TimeField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if value in (None, ''):
            return None

        if self.output_format is None or isinstance(value, str):
            return value

        assert not isinstance(value, datetime.datetime), (
            'Expected a `time`, but got a `datetime`. Refusing to coerce, '
            'as this may mean losing timezone information. Use a custom '
            'read-only field and deal with timezone issues explicitly.'
        )

        return value.strftime(self.output_format)


class ListField(Field):
    # child = _UnvalidatedField()

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        assert self.child.source is None, (
            "The `source` argument is not meaningful when applied to a `child=` field. "
            "Remove `source=` from the field declaration."
        )

        super(ListField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        return [self.child.to_representation(item) if item is not None else None for item in data]


class DictField(Field):
    # child = _UnvalidatedField()
    initial = {}
    default_error_messages = {
        'not_a_dict': 'Expected a dictionary of items but got type "{input_type}".'
    }

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))

        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        assert self.child.source is None, (
            "The `source` argument is not meaningful when applied to a `child=` field. "
            "Remove `source=` from the field declaration."
        )

        super(DictField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    def get_value(self, dictionary):
        # We override the default field access in order to support
        # dictionaries in HTML forms.
        if html.is_html_input(dictionary):
            return html.parse_html_dict(dictionary, prefix=self.field_name)
        return dictionary.get(self.field_name, empty)

    def to_internal_value(self, data):
        """
        Dicts of native values <- Dicts of primitive datatypes.
        """
        if html.is_html_input(data):
            data = html.parse_html_dict(data)
        if not isinstance(data, dict):
            self.fail('not_a_dict', input_type=type(data).__name__)
        return {
            six.text_type(key): self.child.run_validation(value)
            for key, value in data.items()
        }

    def to_representation(self, value):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        return {
            six.text_type(key): self.child.to_representation(val) if val is not None else None
            for key, val in value.items()
        }


class JSONField(Field):
    default_error_messages = {
        'invalid': 'Value must be valid JSON.'
    }

    def __init__(self, *args, **kwargs):
        self.binary = kwargs.pop('binary', False)
        super(JSONField, self).__init__(*args, **kwargs)

    def get_value(self, dictionary):
        if html.is_html_input(dictionary) and self.field_name in dictionary:
            # When HTML form input is used, mark up the input
            # as being a JSON string, rather than a JSON primitive.
            class JSONString(six.text_type):
                def __new__(self, value):
                    ret = six.text_type.__new__(self, value)
                    ret.is_json_string = True
                    return ret
            return JSONString(dictionary[self.field_name])
        return dictionary.get(self.field_name, empty)

    def to_internal_value(self, data):
        try:
            if self.binary or getattr(data, 'is_json_string', False):
                if isinstance(data, six.binary_type):
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
            # On python 2.x the return type for json.dumps() is underspecified.
            # On python 3.x json.dumps() returns unicode strings.
            if isinstance(value, six.text_type):
                value = bytes(value.encode('utf-8'))
        return value


# Miscellaneous field types...

class ReadOnlyField(Field):
    """
    A read-only field that simply returns the field value.

    If the field is a method with no parameters, the method will be called
    and its return value used as the representation.

    For example, the following would call `get_expiry_date()` on the object:

    class ExampleSerializer(Serializer):
        expiry_date = ReadOnlyField(source='get_expiry_date')
    """

    def __init__(self, **kwargs):
        kwargs['read_only'] = True
        super(ReadOnlyField, self).__init__(**kwargs)

    def to_representation(self, value):
        return value


class HiddenField(Field):
    """
    A hidden field does not take input from the user, or present any output,
    but it does populate a field in `validated_data`, based on its default
    value. This is particularly useful when we have a `unique_for_date`
    constraint on a pair of fields, as we need some way to include the date in
    the validated data.
    """
    def __init__(self, **kwargs):
        assert 'default' in kwargs, 'default is a required argument.'
        kwargs['write_only'] = True
        super(HiddenField, self).__init__(**kwargs)

    def get_value(self, dictionary):
        # We always use the default value for `HiddenField`.
        # User input is never provided or accepted.
        return empty

    def to_internal_value(self, data):
        return data


class SerializerMethodField(Field):
    """
    A read-only field that get its representation from calling a method on the
    parent serializer class. The method called will be of the form
    "get_{field_name}", and should take a single argument, which is the
    object being serialized.

    For example:

    class ExampleSerializer(self):
        extra_info = SerializerMethodField()

        def get_extra_info(self, obj):
            return ...  # Calculate some data to return.
    """
    def __init__(self, method_name=None, **kwargs):
        self.method_name = method_name
        kwargs['source'] = '*'
        kwargs['read_only'] = True
        super(SerializerMethodField, self).__init__(**kwargs)

    def bind(self, field_name, parent):
        # In order to enforce a consistent style, we error if a redundant
        # 'method_name' argument has been used. For example:
        # my_field = serializer.SerializerMethodField(method_name='get_my_field')
        default_method_name = 'get_{field_name}'.format(field_name=field_name)
        assert self.method_name != default_method_name, (
            "It is redundant to specify `%s` on SerializerMethodField '%s' in "
            "serializer '%s', because it is the same as the default method name. "
            "Remove the `method_name` argument." %
            (self.method_name, field_name, parent.__class__.__name__)
        )

        # The method name should default to `get_{field_name}`.
        if self.method_name is None:
            self.method_name = default_method_name

        super(SerializerMethodField, self).bind(field_name, parent)

    def to_representation(self, value):
        method = getattr(self.parent, self.method_name)
        return method(value)


class ModelField(Field):
    """
    A generic field that can be used against an arbitrary model field.

    This is used by `ModelSerializer` when dealing with custom model fields,
    that do not have a serializer field to be mapped to.
    """
    default_error_messages = {
        'max_length': 'Ensure this field has no more than {max_length} characters.'
    }

    def __init__(self, model_field, **kwargs):
        self.model_field = model_field
        # The `max_length` option is supported by Django's base `Field` class,
        # so we'd better support it here.
        max_length = kwargs.pop('max_length', None)
        super(ModelField, self).__init__(**kwargs)
        if max_length is not None:
            message = self.error_messages['max_length'].format(max_length=max_length)
            self.validators.append(MaxLengthValidator(max_length, message=message))

    def to_internal_value(self, data):
        rel = get_remote_field(self.model_field, default=None)
        if rel is not None:
            return rel.to._meta.get_field(rel.field_name).to_python(data)
        return self.model_field.to_python(data)

    def get_attribute(self, obj):
        # We pass the object instance onto `to_representation`,
        # not just the field attribute.
        return obj

    def to_representation(self, obj):
        value = value_from_object(self.model_field, obj)
        if is_protected_type(value):
            return value
        return self.model_field.value_to_string(obj)
