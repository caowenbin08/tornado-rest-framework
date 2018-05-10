# -*- coding: utf-8 -*-
from rest_framework.core.db import models
from rest_framework.utils.constants import LOOKUP_SEP


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
