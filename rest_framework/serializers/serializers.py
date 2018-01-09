# -*- coding: utf-8 -*-
import inspect
import copy
from collections import OrderedDict
from rest_framework.conf import settings
from rest_framework.core.exceptions import ValidationError, ErrorDict, ErrorList, \
    ImproperlyConfigured, FieldError
from rest_framework.forms.fields import Field, FileField
from rest_framework.core.db import models
from rest_framework.serializers.fields import (
    Field, CharField, DateTimeField, IntegerField, BooleanField, FloatField, DateField,
    TimeField, UUIDField
)
from rest_framework.utils.cached_property import cached_property
from rest_framework.utils.functional import OrderedDictStorage
from rest_framework.utils.constants import ALL_FIELDS

__author__ = 'caowenbin'

__all__ = ['Serializer', 'ModelSerializer']
LIST_SERIALIZER_KWARGS = ('default', 'initial', 'source', 'instance', 'data')

MODEL_SERIALIZER_FIELD_MAPPINGS = {
    models.CharField: CharField,
    models.FixedCharField: CharField,
    models.TextField: CharField,
    models.DateTimeField: DateTimeField,
    models.IntegerField: IntegerField,
    models.BooleanField: BooleanField,
    models.FloatField: FloatField,
    models.DoubleField: FloatField,
    models.BigIntegerField: IntegerField,
    models.SmallIntegerField: IntegerField,
    models.PrimaryKeyField: IntegerField,
    models.ForeignKeyField: IntegerField,
    models.DateField: DateField,
    models.TimeField: TimeField,
    models.TimestampField: DateTimeField,
    models.UUIDField: UUIDField,
}


class DeclarativeFieldsMetaclass(type):
    """
    Metaclass that collects Fields declared on the base classes.
    """
    def __new__(mcs, name, bases, attrs):
        current_fields = []
        for key, value in list(attrs.items()):
            if isinstance(value, Field):
                current_fields.append((key, value))
                attrs.pop(key)
        current_fields.sort(key=lambda x: x[1].creation_counter)
        attrs['declared_fields'] = OrderedDict(current_fields)

        new_class = super(DeclarativeFieldsMetaclass, mcs).__new__(mcs, name, bases, attrs)

        # Walk through the MRO.
        declared_fields = OrderedDict()
        for base in reversed(new_class.__mro__):
            # Collect fields from base class.
            if hasattr(base, 'declared_fields') and base.declared_fields:
                declared_fields.update(base.declared_fields)

            # Field shadowing.
            for attr, value in base.__dict__.items():
                if value is None and attr in declared_fields:
                    declared_fields.pop(attr)

        new_class.base_fields = declared_fields
        new_class.declared_fields = declared_fields

        return new_class


class BaseSerializer(object):

    def __init__(self, serializer_data, **kwargs):
        """
        :param serializer_data: 待序列化的对象，可以model的对象或字典
        :param kwargs:
        """
        self.serializer_data = serializer_data
        self._data = None
        self._fields = None

    def __new__(cls, *args, **kwargs):
        if kwargs.pop('many', False):
            return cls.many_init(*args, **kwargs)
        return super(BaseSerializer, cls).__new__(cls)

    @classmethod
    def many_init(cls, *args, **kwargs):
        """
        @classmethod
        def many_init(cls, *args, **kwargs):
            kwargs['child'] = cls()
            return CustomListSerializer(*args, **kwargs)
        """
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {'child': child_serializer}
        list_kwargs.update({
            key: value for key, value in kwargs.items()
            if key in LIST_SERIALIZER_KWARGS
        })
        meta = getattr(cls, 'Meta', None)
        list_serializer_class = getattr(meta, 'list_serializer_class', ListSerializer)
        return list_serializer_class(*args, **list_kwargs)

    @property
    def fields(self):
        if self._fields is None:
            self._fields = OrderedDict()
            fields = copy.deepcopy(self.base_fields)
            for key, field in fields.items():
                field.bind(field_name=key, parent=self)
                self._fields[key] = field
        return self._fields

    def to_representation(self, serializer_data):
        """
        查询对象转为字典结构
        :param serializer_data: 数据库结果集（模型实例）
        :return:
        """
        ret = OrderedDictStorage()
        for field_name, field in self.fields.items():
            attribute = field.get_attribute(serializer_data)
            if attribute is None:
                ret[field_name] = None
            else:
                ret[field_name] = field.to_representation(attribute)

        return ret

    @property
    def data(self):
        if self._data is None:
            self._data = self.to_representation(self.serializer_data)
        return self._data


class Serializer(BaseSerializer, metaclass=DeclarativeFieldsMetaclass):
    pass


def fields_for_model(model, fields=None, exclude=None):
    """
    根据model字段转化为form字段
    :param model:
    :param fields:
    :param exclude:
    :return:
    """
    opts = model._meta
    model_fields = opts.fields
    field_dict = OrderedDict()
    for field_name, field in model_fields.items():
        if fields is not None and field_name not in fields:
            continue
        if exclude and field_name in exclude:
            continue

        form_class = MODEL_SERIALIZER_FIELD_MAPPINGS.get(field.__class__, CharField)
        field_dict[field_name] = form_class()
    return field_dict


class ModelSerializerOptions(object):
    def __init__(self, options=None):
        self.model = getattr(options, 'model', None)
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)


class ModelSerializerMetaclass(DeclarativeFieldsMetaclass):

    def __new__(mcs, name, bases, attrs):
        new_class = super(ModelSerializerMetaclass, mcs).__new__(mcs, name, bases, attrs)
        opts = new_class._meta = ModelSerializerOptions(getattr(new_class, 'Meta', None))

        if opts.model:
            # If a model is defined, extract form fields from it.
            if opts.fields is None and opts.exclude is None:
                raise ImproperlyConfigured(
                    "Creating a ModelForm without either the 'fields' attribute "
                    "or the 'exclude' attribute is prohibited; form %s "
                    "needs updating." % name
                )

            if opts.fields == ALL_FIELDS:
                opts.fields = None

            fields = fields_for_model(
                model=opts.model,
                fields=opts.fields,
                exclude=opts.exclude
            )

            # make sure opts.fields doesn't specify an invalid field
            none_model_fields = [k for k, v in fields.items() if not v]
            missing_fields = (set(none_model_fields) - set(new_class.declared_fields.keys()))
            if missing_fields:
                message = 'Unknown field(s) (%s) specified for %s'
                message = message % ', '.join(missing_fields), opts.model.__name__
                raise FieldError(message)
            # Override default model fields with any custom declared ones
            # (plus, include all the other declared fields).
            fields.update(new_class.declared_fields)
        else:
            fields = new_class.declared_fields

        new_class.base_fields = fields

        return new_class


class ModelSerializer(BaseSerializer, metaclass=ModelSerializerMetaclass):
    pass


class ListSerializer(BaseSerializer):
    child = None
    many = True

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert self.child is not None, '`child` is a required argument.'
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        super(ListSerializer, self).__init__(*args, **kwargs)
        # self.child.bind(field_name='', parent=self)

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        iterable = data

        return [self.child.to_representation(item) for item in iterable]

    @property
    def data(self):
        ret = super(ListSerializer, self).data
        return ret


