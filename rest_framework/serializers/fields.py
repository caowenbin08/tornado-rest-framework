# -*- coding: utf-8 -*-
import pytz
import copy
import inspect
import datetime

from rest_framework.conf import settings
from rest_framework.lib.orm import SelectQuery
from rest_framework.utils.escape import json_encode
from rest_framework.utils.constants import empty, REGEX_TYPE
from rest_framework.utils.functional import get_attribute


__all__ = [
    'Field', 'BooleanField', 'NullBooleanField', 'CharField', 'UUIDField',
    'IntegerField', 'FloatField', 'DateTimeField', 'DateField', 'TimeField',
    'ListField', 'DictField', 'JSONField', 'SerializerMethodField',
    'PrimaryKeyRelatedField', 'SlugRelatedField'
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

        if isinstance(value, datetime.datetime):
            to_zone = pytz.timezone(settings.SHOW_TIME_ZONE)
            from_zone = pytz.timezone(settings.TIME_ZONE)
            value = value.replace(tzinfo=from_zone)
            value = value.astimezone(to_zone)
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
            value = json_encode(value)
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

MANY_RELATION_KWARGS = ('verbose_name', 'source')


class PKOnlyObject(object):
    """
    This is a mock object, used for when we only need the pk of the object
    instance, but still want to return an object with a .pk attribute,
    in order to keep the same interface as a regular model instance.
    """
    def __init__(self, pk):
        self.pk = pk

    def get_id(self):
        return self.pk

    def __str__(self):
        return "%s" % self.pk


class RelatedField(Field):

    def __init__(self, **kwargs):
        kwargs.pop('many', None)
        super(RelatedField, self).__init__(**kwargs)

    def __new__(cls, *args, **kwargs):
        # We override this method in order to automagically create
        # `ManyRelatedField` classes instead when `many=True` is set.
        if kwargs.pop('many', False):
            return cls.many_init(*args, **kwargs)
        return super(RelatedField, cls).__new__(cls, *args, **kwargs)

    @classmethod
    def many_init(cls, *args, **kwargs):
        """
        This method handles creating a parent `ManyRelatedField` instance
        when the `many=True` keyword argument is passed.

        Typically you won't need to override this method.

        Note that we're over-cautious in passing most arguments to both parent
        and child classes in order to try to cover the general case. If you're
        overriding this method you'll probably want something much simpler, eg:

        @classmethod
        def many_init(cls, *args, **kwargs):
            kwargs['child'] = cls()
            return CustomManyRelatedField(*args, **kwargs)
        """
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs.keys():
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return ManyRelatedField(**list_kwargs)

    def use_pk_only_optimization(self):
        return False

    def get_attribute(self, instance):
        if self.use_pk_only_optimization() and self.source_attrs:
            try:
                instance = get_attribute(instance, self.source_attrs[:-1])
                value = instance.serializable_value(self.source_attrs[-1])
                if isinstance(value, SelectQuery):
                    value = value.get().get_id()

                if hasattr(value, "get_id"):
                    value = value.get_id()

                return PKOnlyObject(pk=value)
            except AttributeError:
                pass

        # Standard case, return the object instance.
        return get_attribute(instance, self.source_attrs)


class PrimaryKeyRelatedField(RelatedField):
    def __init__(self, **kwargs):
        self.pk_field = kwargs.pop('pk_field', None)
        super(PrimaryKeyRelatedField, self).__init__(**kwargs)

    def use_pk_only_optimization(self):
        return True

    def to_representation(self, value):
        pk_value = value.get_id()

        if self.pk_field is not None:
            return self.pk_field.to_representation(pk_value)
        return pk_value


class SlugRelatedField(RelatedField):

    def __init__(self, slug_field, **kwargs):
        self.slug_field = slug_field
        super(SlugRelatedField, self).__init__(**kwargs)

    def to_representation(self, obj):
        return getattr(obj, self.slug_field)


class ManyRelatedField(Field):
    initial = []

    def __init__(self, child_relation=None, *args, **kwargs):
        self.child_relation = child_relation

        assert child_relation is not None, '`child_relation` is a required argument.'
        super(ManyRelatedField, self).__init__(*args, **kwargs)
        self.child_relation.bind(field_name='', parent=self)

    def get_attribute(self, instance):
        if hasattr(instance, 'get_id') and instance.get_id() is None:
            return []

        relationship = get_attribute(instance, self.source_attrs)
        return relationship.select() if hasattr(relationship, 'select') else relationship

    async def to_representation(self, iterable):
        if hasattr(iterable, "__aiter__"):
            return [self.child_relation.to_representation(value)  async for value in iterable]

        return [self.child_relation.to_representation(value) for value in iterable]
