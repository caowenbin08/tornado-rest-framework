# -*- coding: utf-8 -*-
import copy
import inspect
import json
from rest_framework.utils.constants import empty, REGEX_TYPE
from rest_framework.utils.functional import get_attribute

__author__ = 'caowenbin'

__all__ = [
    'Field', 'BooleanField', 'NullBooleanField', 'CharField', 'UUIDField',
    'IntegerField', 'FloatField', 'DateTimeField', 'DateField', 'TimeField',
    'ListField', 'DictField', 'JSONField', 'SerializerMethodField'
]


class Field(object):
    _creation_counter = 0
    initial = None

    def __init__(self, verbose_name=None, default=empty, initial=empty, source=None):
        self._creation_counter = Field._creation_counter
        Field._creation_counter += 1
        self.verbose_name = verbose_name
        self.default = default
        self.source = source
        self.initial = self.initial if (initial is empty) else initial
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

    def get_default(self):
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


# Boolean types...

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

    def to_representation(self, value):
        if value in self.NULL_VALUES:
            return None
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        return bool(value)


# String types...

class CharField(Field):

    initial = ''

    def __init__(self, **kwargs):
        self.allow_blank = kwargs.pop('allow_blank', False)
        self.trim_whitespace = kwargs.pop('trim_whitespace', True)
        super(CharField, self).__init__(**kwargs)

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


# Number types...

class IntegerField(Field):

    def to_representation(self, value):
        return int(value)


class FloatField(Field):

    def to_representation(self, value):
        return float(value)


# Date & time fields...

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


# Composite field types...

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
    initial = []

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        self.child.source = None
        super(ListField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        return [self.child.to_representation(item) if item is not None else None for item in data]


class DictField(Field):
    child = _UnvalidatedField()
    initial = {}

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        self.child.source = None
        super(DictField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    def to_representation(self, value):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        return {
            str(key): self.child.to_representation(val) if val is not None else None
            for key, val in value.items()
        }


class JSONField(Field):
    def __init__(self, *args, **kwargs):
        self.binary = kwargs.pop('binary', False)
        super(JSONField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if self.binary:
            value = json.dumps(value)
            if isinstance(value, str):
                value = bytes(value.encode('utf-8'))
        return value


# Miscellaneous field types...

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

