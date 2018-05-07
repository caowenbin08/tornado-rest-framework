# -*- coding: utf-8 -*-
import asyncio
import copy
import inspect
from collections import OrderedDict
from rest_framework.core.db import models
from rest_framework.core.exceptions import ImproperlyConfigured, FieldError
from rest_framework.lib.orm.query import AsyncSelectQuery
from rest_framework.serializers.fields import (
    Field,
    CharField,
    DateTimeField,
    IntegerField,
    BooleanField,
    FloatField,
    DateField,
    TimeField,
    UUIDField,
    PKOnlyObject,
    PrimaryKeyRelatedField,
)
from rest_framework.utils.constants import ALL_FIELDS


LIST_SERIALIZER_KWARGS = ('default', 'initial', 'source', 'instance')


class BaseSerializer(Field):

    def __init__(self, instance=None, **kwargs):
        self.instance = instance
        self._context = kwargs.pop('context', {})
        kwargs.pop('many', None)
        self._fields = None
        self._serializer_data = None
        super(BaseSerializer, self).__init__(**kwargs)

    def __new__(cls, *args, **kwargs):
        if kwargs.pop('many', False):
            return cls.many_init(*args, **kwargs)
        return super(BaseSerializer, cls).__new__(cls, *args, **kwargs)

    @classmethod
    def many_init(cls, *args, **kwargs):
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
    async def data(self):
        if self._serializer_data is None:
            self._serializer_data = await self.to_representation(self.instance)
        return self._serializer_data

    @property
    def fields(self):
        if self._fields is None:
            self._fields = OrderedDict()
            fields = copy.deepcopy(self.base_fields)
            for key, field in fields.items():
                field.bind(field_name=key, parent=self)
                self._fields[key] = field
        return self._fields

    async def to_representation(self, instance):
        ret = OrderedDict()
        for field_name, field in self.fields.items():
            attribute = field.get_attribute(instance)
            check_for_none = attribute.pk if isinstance(attribute, PKOnlyObject) else attribute
            attr_data = None if check_for_none is None else field.to_representation(attribute)
            if asyncio.iscoroutine(attr_data):
                attr_data = await attr_data

            attr_data = await self.clean_data(instance, field_name, attr_data)
            ret[field_name] = attr_data

        cleaned_data = await self.clean(ret)
        if cleaned_data is not None:
            ret = cleaned_data

        return ret

    async def clean_data(self, instance, field_name, value):
        """
        处理用户自定义的clean_**函数（**为字段名）
        """
        clean_method = 'clean_%s' % field_name
        if hasattr(self, clean_method):
            customize_method = getattr(self, clean_method)
            value = customize_method(instance, value)
            if asyncio.iscoroutine(value):
                value = await value

        return value

    async def clean(self, ret):
        return ret


class DeclarativeFieldsMetaclass(type):
    @classmethod
    def _get_declared_fields(cls, bases, attrs):
        fields = [(field_name, attrs.pop(field_name))
                  for field_name, obj in list(attrs.items())
                  if isinstance(obj, Field)]
        fields.sort(key=lambda x: x[1]._creation_counter)

        for base in reversed(bases):
            if hasattr(base, 'declared_fields'):
                fields = [
                    (field_name, obj) for field_name, obj
                    in base.declared_fields.items()
                    if field_name not in attrs
                ] + fields

        return OrderedDict(fields)

    def __new__(mcs, name, bases, attrs):
        declared_fields = mcs._get_declared_fields(bases, attrs)
        attrs['declared_fields'] = declared_fields
        new_class = super(DeclarativeFieldsMetaclass, mcs).__new__(mcs, name, bases, attrs)
        new_class.base_fields = declared_fields
        new_class.declared_fields = declared_fields

        return new_class


class Serializer(BaseSerializer, metaclass=DeclarativeFieldsMetaclass):
    pass


class ListSerializer(BaseSerializer):
    child = None
    many = True

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert self.child is not None, '`child` is a required argument.'
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        super(ListSerializer, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    async def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        if asyncio.iscoroutine(data) or isinstance(data, AsyncSelectQuery):
            return [await self.child.to_representation(item) async for item in data]
        else:
            return [await self.child.to_representation(item) for item in data]

    @property
    async def data(self):
        ret = await super(ListSerializer, self).data
        return ret


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
    models.ForeignKeyField: PrimaryKeyRelatedField,
    models.DateField: DateField,
    models.TimeField: TimeField,
    models.TimestampField: DateTimeField,
    models.UUIDField: UUIDField,
}


def fields_for_model(model, fields=None, exclude=None):
    opts = model._meta
    model_fields = opts.fields
    field_dict = OrderedDict()

    for field_name, field in model_fields.items():
        if fields is not None and field_name not in fields:
            continue
        if exclude and field_name in exclude:
            continue

        form_class = MODEL_SERIALIZER_FIELD_MAPPINGS.get(field.__class__, CharField)
        field_dict[field_name] = form_class(verbose_name=field.verbose_name)
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
            if opts.fields is None and opts.exclude is None:
                raise ImproperlyConfigured(
                    "Creating a ModelSerializer without either the 'fields' attribute "
                    "or the 'exclude' attribute is prohibited; ModelSerializer %s "
                    "needs updating." % name
                )

            if isinstance(opts.fields, str) and opts.fields.lower() == ALL_FIELDS:
                opts.fields = None

            fields = fields_for_model(
                model=opts.model,
                fields=opts.fields,
                exclude=opts.exclude
            )

            none_model_fields = [k for k, v in fields.items() if not v]
            missing_fields = (set(none_model_fields) - set(new_class.declared_fields.keys()))
            if missing_fields:
                message = 'Unknown field(s) (%s) specified for %s'
                message = message % ', '.join(missing_fields), opts.model.__name__
                raise FieldError(message)
            fields.update(new_class.declared_fields)
        else:
            fields = new_class.declared_fields

        new_class.base_fields = fields

        return new_class


class ModelSerializer(BaseSerializer, metaclass=ModelSerializerMetaclass):
    pass
