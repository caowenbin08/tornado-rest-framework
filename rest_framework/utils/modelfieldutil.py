# -*- coding: utf-8 -*-
import inspect
from collections import OrderedDict, namedtuple

from rest_framework.core.db import models
from rest_framework.utils.constants import LOOKUP_SEP
from rest_framework.forms.validators import UniqueValidator

NUMERIC_FIELD_TYPES = (models.IntegerField, models.FloatField, models.DecimalField)


class ClassLookupDict(object):
    """
    Takes a dictionary with classes as keys.
    Lookups against this object will traverses the object's inheritance
    hierarchy in method resolution order, and returns the first matching value
    from the dictionary or raises a KeyError if nothing matches.
    """
    def __init__(self, mapping):
        self.mapping = mapping

    def __getitem__(self, key):
        if hasattr(key, '_proxy_class'):
            # Deal with proxy classes. Ie. BoundField behaves as if it
            # is a Field instance when using ClassLookupDict.
            base_class = key._proxy_class
        else:
            base_class = key.__class__

        for cls in inspect.getmro(base_class):
            if cls in self.mapping:
                return self.mapping[cls]
        raise KeyError('Class %s not found in lookup.' % base_class.__name__)

    def __setitem__(self, key, value):
        self.mapping[key] = value


def get_field_kwargs(field_name, model_field):
    """
    Creates a default instance of a basic non-relational field.
    """
    kwargs = {}
    validator_kwarg = []

    # 是否必须，False代表非必选项
    if model_field.default is not None or model_field.null:
        kwargs['required'] = False

    kwargs["default"] = model_field.default

    if model_field.null:
        kwargs['null'] = True

    if model_field.choices:
        kwargs['choices'] = model_field.choices

    if isinstance(model_field, models.PrimaryKeyField):
        kwargs['read_only'] = True
        return kwargs

    # rather than as a validator.
    max_length = getattr(model_field, 'max_length', None)
    if max_length is not None and isinstance(model_field, (models.CharField, models.TextField)):
        kwargs['max_length'] = max_length
        # validator_kwarg = [
        #     validator for validator in validator_kwarg
        #     if not isinstance(validator, validators.MaxLengthValidator)
        # ]

    if getattr(model_field, 'unique', False):
        # unique_error_message = model_field.error_messages.get('unique', None)
        # if unique_error_message:
        #     unique_error_message = unique_error_message % {
        #         'model_name': model_field.model._meta.verbose_name,
        #         'field_label': model_field.verbose_name
        #     }
        validator = UniqueValidator(
            queryset=model_field.model._default_manager,
            message="不能重复")
        validator_kwarg.append(validator)

    if validator_kwarg:
        kwargs['validators'] = validator_kwarg

    return kwargs

FieldInfo = namedtuple('FieldResult', [
    'pk',  # Model field instance
    'fields',  # Dict of field name -> model field instance
    'fields_and_pk',  # Shortcut for 'pk' + 'fields'
])


def get_field_info(model):
    opts = model._meta
    pk = opts.primary_key
    fields = opts.fields
    fields_and_pk = _merge_fields_and_pk(pk, fields)

    return FieldInfo(pk, fields, fields_and_pk)


def _merge_fields_and_pk(pk, fields):
    fields_and_pk = OrderedDict()
    fields_and_pk['pk'] = pk
    fields_and_pk[pk.name] = pk
    fields_and_pk.update(fields)

    return fields_and_pk


def get_model_field(model, field_name):
    """
    字段名获得`model`或外键model的字段， 如果不存在返回None
    例：
    f = get_model_field(Book, 'author.first_name')
    f 为author的first_name字段
    :param model:
    :param field_name:
    :return:
    """

    fields = get_field_parts(model, field_name)
    return fields[-1] if fields else None


def get_field_parts(model, field_name):
    """
    遍历model的字段获得对应的字段， 如果不存在返回None
    例
        >>> parts = get_field_parts(Book, 'author.first_name')
        >>> [p.name for p in parts]
        ['author', 'first_name']

    :param model:
    :param field_name:
    :return:
    """
    parts = field_name.split(LOOKUP_SEP)
    opts = getattr(model, "_meta")
    fields = []

    for name in parts:
        field = opts.fields.get(name, None)
        if field is None:
            return None

        fields.append(field)
        # if isinstance(field, RelatedField):
        #     opts = field.remote_field.model._meta
        # elif isinstance(field, ForeignObjectRel):
        #     opts = field.related_model._meta

    return fields


def try_dbfield(fn, field_class):
    """
    试着`fn`与`field_class`的MRO（方法解析顺序）寻找`field_class`的数据在`fn`中并返回
    例：
      try_dbfield(field_dict.get, models.CharField)
    :param fn:
    :param field_class:
    :return:
    """

    for cls in field_class.mro():
        if cls is models.Field:
            continue

        data = fn(cls)
        if data:
            return data


def get_all_model_fields(model):
    """
    获得model所有的字段
    :param model:
    :return:
    """

    opts = model._meta

    return [
        f.name for f in sorted(opts.fields + opts.many_to_many)
        if not isinstance(f, models.AutoField) and
        not (getattr(f.remote_field, 'parent_link', False))
    ]