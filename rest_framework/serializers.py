# -*- coding: utf-8 -*-
import copy
import inspect
from collections import OrderedDict

from rest_framework.db import models
from rest_framework.fields import (
    Field, CharField, DateTimeField, IntegerField, BooleanField, FloatField,
    DateField,  TimeField, UUIDField
)

from rest_framework.helpers import functional, model_meta
from rest_framework.helpers.cached_property import cached_property
from rest_framework.helpers.field_mapping import ClassLookupDict
from rest_framework.helpers.serializer_utils import BindingDict, ReturnDict, ReturnList
from rest_framework.fields import __all__ as fields_all

__all__ = ['Serializer', 'ModelSerializer'] + fields_all

__author__ = 'caowenbin'

ALL_FIELDS = '__all__'
LIST_SERIALIZER_KWARGS = ('default', 'initial', 'source', 'instance', 'data')


class BaseSerializer(Field):

    def __init__(self, instance, **kwargs):
        self.instance = instance
        # self._context = kwargs.pop('context', {})
        self._data = None
        kwargs.pop('many', None)
        super(BaseSerializer, self).__init__(**kwargs)

    def __new__(cls, *args, **kwargs):
        if kwargs.pop('many', False):
            return cls.many_init(*args, **kwargs)
        return super(BaseSerializer, cls).__new__(cls, *args, **kwargs)

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

    def to_internal_value(self, data):
        pass

    def to_representation(self, instance):
        raise NotImplementedError('`to_representation()` must be implemented.')

    @property
    def data(self):
        if self._data is None:
            self._data = self.to_representation(self.instance)
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

        return OrderedDict(fields)


@functional.add_metaclass(SerializerMetaclass)
class Serializer(BaseSerializer):

    @cached_property
    def fields(self):
        """
        返回字典结构
        类似：{field_name: field_instance}
        """
        _fields = BindingDict(self)
        for key, value in self.get_fields().items():
            _fields[key] = value
        return _fields.values()

    def get_fields(self):
        """
        获得所有需要序列化的字段
        类似：{field_name: field_instance}
        """
        return copy.deepcopy(self._declared_fields)

    def to_representation(self, instance):
        """
        查询对象转为字典结构
        :param instance: 数据库结果集（模型实例）
        :return:
        """
        ret = OrderedDict()
        for field in self.fields:
            attribute = field.get_attribute(instance)
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
        return ReturnDict(ret, serializer=self)


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
        models.TimestampField: IntegerField,
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

        info = model_meta.get_field_info(model)
        field_names = self.get_field_names(declared_fields, info)

        fields = OrderedDict()

        for field_name in field_names:
            if field_name in declared_fields:
                fields[field_name] = declared_fields[field_name]
                continue

            field_class = self.build_field(field_name, info, model, depth)
            fields[field_name] = field_class()

        return fields

    # Methods for determining the set of field names to include...

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

        # Use the default set of field names if `Meta.fields` is not specified.
        fields = self.get_default_field_names(declared_fields, info)
        return set(fields) - set(exclude) if exclude is not None else set(fields)

    @staticmethod
    def get_default_field_names(declared_fields, model_info):
        """
        Return the default list of field names that will be used if the
        `Meta.fields` option is not specified.
        """
        return (
            [model_info.pk.name] +
            list(declared_fields.keys()) +
            list(model_info.fields.keys()) +
            list(model_info.forward_relations.keys())
        )

    # Methods for constructing serializer fields...

    def build_field(self, field_name, info, model_class, nested_depth):
        """
        Return a two tuple of (cls, kwargs) to build a serializer field with.
        """
        if field_name in info.fields_and_pk:
            model_field = info.fields_and_pk[field_name]
            return self.build_standard_field(field_name, model_field)

        # elif field_name in info.relations:
        #     relation_info = info.relations[field_name]
        #     if not nested_depth:
        #         return self.build_relational_field(field_name, relation_info)
        #     else:
        #         return self.build_nested_field(field_name, relation_info, nested_depth)
        #
        # elif hasattr(model_class, field_name):
        #     return self.build_property_field(field_name, model_class)
        #
        # elif field_name == self.url_field_name:
        #     return self.build_url_field(field_name, model_class)
        #
        # return self.build_unknown_field(field_name, model_class)

    def build_standard_field(self, field_name, model_field):
        """
        Create regular model fields.
        """
        field_mapping = ClassLookupDict(self.serializer_field_mapping)

        field_class = field_mapping[model_field]
        # field_kwargs = get_field_kwargs(field_name, model_field)
        #
        # if 'choices' in field_kwargs:
        #     # Fields with choices get coerced into `ChoiceField`
        #     # instead of using their regular typed field.
        #     field_class = self.serializer_choice_field
        #     # Some model fields may introduce kwargs that would not be valid
        #     # for the choice field. We need to strip these out.
        #     # Eg. models.DecimalField(max_digits=3, decimal_places=1, choices=DECIMAL_CHOICES)
        #     valid_kwargs = set(('default', 'initial', 'source', 'choices'))
        #     for key in list(field_kwargs.keys()):
        #         if key not in valid_kwargs:
        #             field_kwargs.pop(key)
        #
        # if not issubclass(field_class, ModelField):
        #     # `model_field` is only valid for the fallback case of
        #     # `ModelField`, which is used when no other typed field
        #     # matched to the model field.
        #     field_kwargs.pop('model_field', None)
        #
        # if not issubclass(field_class, CharField) and not issubclass(field_class, ChoiceField):
        #     # `allow_blank` is only valid for textual fields.
        #     field_kwargs.pop('allow_blank', None)

        return field_class

    # def build_relational_field(self, field_name, relation_info):
    #     """
    #     Create fields for forward and reverse relationships.
    #     """
    #     field_class = self.serializer_related_field
    #     field_kwargs = get_relation_kwargs(field_name, relation_info)
    #
    #     to_field = field_kwargs.pop('to_field', None)
    #     if to_field and not relation_info.reverse and not relation_info.related_model._meta.get_field(to_field).primary_key:
    #         field_kwargs['slug_field'] = to_field
    #         field_class = self.serializer_related_to_field
    #
    #     # `view_name` is only valid for hyperlinked relationships.
    #     if not issubclass(field_class, HyperlinkedRelatedField):
    #         field_kwargs.pop('view_name', None)
    #
    #     return field_class, field_kwargs
    #
    # def build_nested_field(self, field_name, relation_info, nested_depth):
    #     """
    #     Create nested fields for forward and reverse relationships.
    #     """
    #     class NestedSerializer(ModelSerializer):
    #         class Meta:
    #             model = relation_info.related_model
    #             depth = nested_depth - 1
    #             fields = '__all__'
    #
    #     field_class = NestedSerializer
    #     field_kwargs = get_nested_relation_kwargs(relation_info)
    #
    #     return field_class, field_kwargs


class ListSerializer(BaseSerializer):
    child = None
    many = True

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert self.child is not None, '`child` is a required argument.'
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        super(ListSerializer, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    def bind(self, field_name, parent):
        super(ListSerializer, self).bind(field_name, parent)

    def get_initial(self):
        if hasattr(self, 'initial_data'):
            return self.to_representation(self.initial_data)
        return []

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        iterable = data

        return [self.child.to_representation(item) for item in iterable]

    @property
    def data(self):
        ret = super(ListSerializer, self).data
        return ReturnList(ret, serializer=self)


