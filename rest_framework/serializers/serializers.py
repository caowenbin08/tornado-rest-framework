# -*- coding: utf-8 -*-
import copy
import inspect

from rest_framework.core.db import models
from rest_framework.serializers.fields import (
    Field, CharField, DateTimeField, IntegerField, BooleanField, FloatField, DateField,
    TimeField, UUIDField
)
from rest_framework.utils import functional, modelfieldutil
from rest_framework.utils.cached_property import cached_property
from rest_framework.utils.functional import OrderedDictStorage
from rest_framework.utils.constants import ALL_FIELDS

__author__ = 'caowenbin'

__all__ = ['Serializer', 'ModelSerializer']
LIST_SERIALIZER_KWARGS = ('default', 'initial', 'source', 'instance', 'data')


class BaseSerializer(object):

    def __init__(self, serializer_data, **kwargs):
        """
        :param serializer_data: 待序列化的对象，可以model的对象或字典
        :param kwargs:
        """
        self.serializer_data = serializer_data
        # self._context = kwargs.pop('context', {})
        self._data = None
        kwargs.pop('many', None)
        # super(BaseSerializer, self).__init__(**kwargs)

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

    def to_representation(self, instance):
        raise NotImplementedError('`to_representation()` must be implemented.')

    @property
    def data(self):
        if self._data is None:
            self._data = self.to_representation(self.serializer_data)
        return self._data


class SerializerMetaclass(type):
    """
    处理公开宣布（自定义）的字段及根据字段的计数排序
    """
    def __new__(mcs, name, bases, attributes):
        attributes['_declared_fields'] = mcs._get_declared_fields(bases, attributes)
        return super(SerializerMetaclass, mcs).__new__(mcs, name, bases, attributes)

    @staticmethod
    def _get_declared_fields(bases, attributes):
        fields = [(field_name, attributes.pop(field_name))
                  for field_name, obj in list(attributes.items())
                  if isinstance(obj, Field)]

        fields.sort(key=lambda x: getattr(x[1], "_creation_counter"))

        for base in reversed(bases):
            if hasattr(base, '_declared_fields'):
                fields = [
                    (field_name, obj) for field_name, obj
                    in getattr(base, "_declared_fields").items()
                    if field_name not in attributes
                ] + fields

        return OrderedDictStorage(fields)


@functional.add_metaclass(SerializerMetaclass)
class Serializer(BaseSerializer):

    @cached_property
    def fields(self):
        """
        返回字典结构
        类似：{field_name: field_instance}
        """
        _fields = functional.BindingDict(self)
        for key, value in self.get_fields().items():
            _fields[key] = value
        return _fields.values()

    def get_fields(self):
        """
        获得所有需要序列化的字段
        类似：{field_name: field_instance}
        """
        return copy.deepcopy(self._declared_fields)

    def to_representation(self, serializer_data):
        """
        查询对象转为字典结构
        :param serializer_data: 数据库结果集（模型实例）
        :return:
        """
        ret = OrderedDictStorage()
        for field in self.fields:
            attribute = field.get_attribute(serializer_data)
            if attribute is None:
                ret[field.field_name] = None
            else:
                ret[field.field_name] = field.to_representation(attribute)

        return ret

    def __iter__(self):
        for field in self.fields.values():
            yield self[field.field_name]

    @property
    def data(self):
        ret = super(Serializer, self).data
        return ret
        # return functional.ReturnDict(ret, serializer=self)


class ModelSerializer(Serializer):

    serializer_field_mapping = {
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

    def get_fields(self):
        """
        Return the dict of field names -> field instances that should be
        used for `self.fields` when instantiating the serializer.
        """
        assert hasattr(self, 'Meta'), (
            'Class {serializer_class} missing "Meta" attribute'.format(
                serializer_class=self.__class__.__name__
            )
        )
        assert hasattr(self.Meta, 'model'), (
            'Class {serializer_class} missing "Meta.model" attribute'.format(
                serializer_class=self.__class__.__name__
            )
        )

        declared_fields = copy.deepcopy(self._declared_fields)
        model = getattr(self.Meta, 'model')
        depth = getattr(self.Meta, 'depth', 0)

        if depth is not None:
            assert depth >= 0, "'depth' may not be negative."
            assert depth <= 10, "'depth' may not be greater than 10."

        info = modelfieldutil.get_field_info(model)
        field_names = self.get_field_names(declared_fields, info)

        fields = OrderedDictStorage()

        for field_name in field_names:
            if field_name in declared_fields:
                fields[field_name] = declared_fields[field_name]
                continue

            field_class = self.build_field(field_name, info)
            fields[field_name] = field_class()

        return fields

    def get_field_names(self, declared_fields, info):
        """
        返回所有指定的字段名字列表
        返回的列表由自定义的字段（declared_fields）、Meta.exclude、Meta.fields三个拼成的
        :param declared_fields: 自定义的字段列表
        :param info:
        :return:
        """
        fields = getattr(self.Meta, 'fields', None)
        exclude = getattr(self.Meta, 'exclude', None)

        if fields and fields != ALL_FIELDS and not isinstance(fields, (list, tuple)):
            raise TypeError(
                'The `fields` option must be a list or tuple or "__all__". '
                'Got %s.' % type(fields).__name__
            )

        if exclude and not isinstance(exclude, (list, tuple)):
            raise TypeError(
                'The `exclude` option must be a list or tuple. Got %s.' %
                type(exclude).__name__
            )

        assert not (fields and exclude), (
            "Cannot set both 'fields' and 'exclude' options on "
            "serializer {serializer_class}.".format(
                serializer_class=self.__class__.__name__
            )
        )

        assert not (fields is None and exclude is None), (
            "Creating a ModelSerializer without either the 'fields' attribute "
            "or the 'exclude' attribute has been deprecated since 3.3.0, "
            "and is now disallowed. Add an explicit fields = '__all__' to the "
            "{serializer_class} serializer.".format(
                serializer_class=self.__class__.__name__
            ),
        )

        if fields == ALL_FIELDS:
            fields = None

        if fields is not None:
            # Ensure that all declared fields have also been included in the
            # `Meta.fields` option.

            # Do not require any fields that are declared a parent class,
            # in order to allow serializer subclasses to only include
            # a subset of fields.
            required_field_names = set(declared_fields)
            for cls in self.__class__.__bases__:
                required_field_names -= set(getattr(cls, '_declared_fields', []))

            for field_name in required_field_names:
                assert field_name in fields, (
                    "The field '{field_name}' was declared on serializer "
                    "{serializer_class}, but has not been included in the "
                    "'fields' option.".format(
                        field_name=field_name,
                        serializer_class=self.__class__.__name__
                    )
                )
            return fields

        fields = self.get_default_field_names(declared_fields, info)
        return set(fields) - set(exclude) if exclude is not None else set(fields)

    @staticmethod
    def get_default_field_names(declared_fields, model_info):
        return [model_info.pk.name] + list(declared_fields.keys()) + list(model_info.fields.keys())

    def build_field(self, field_name, info):
        """
        Return a two tuple of (cls, kwargs) to build a serializer field with.
        """
        if field_name in info.fields_and_pk:
            model_field = info.fields_and_pk[field_name]
            return self.build_standard_field(model_field)

    def build_standard_field(self, model_field):
        """
        Create regular model fields.
        """
        field_mapping = modelfieldutil.ClassLookupDict(self.serializer_field_mapping)
        field_class = field_mapping[model_field]

        return field_class


class ListSerializer(BaseSerializer):
    child = None
    many = True

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert self.child is not None, '`child` is a required argument.'
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        super(ListSerializer, self).__init__(*args, **kwargs)
        # self.child.bind(field_name='', parent=self)

    # def bind(self, field_name, parent):
    #     super(ListSerializer, self).bind(field_name, parent)

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


