# -*- coding: utf-8 -*-
import asyncio
import operator
from functools import reduce

from rest_framework.core.exceptions import ImproperlyConfigured
from rest_framework.forms import fields
from rest_framework.core.db import models
from rest_framework.utils.constants import QUERY_TERMS, EMPTY_VALUES
from rest_framework.filters.fields import Lookup, RangeField, DateRangeField, DateTimeRangeField, \
    TimeRangeField

__all__ = [
    'Filter',
    'CharFilter',
    'BooleanFilter',
    'DateFilter',
    'TimeFilter',
    'DateTimeFilter',
    'NumberFilter',
    "ChoiceFilter",
    "DateRangeFilter",
    "DateTimeRangeFilter",
    "TimeRangeFilter"
]


LOOKUP_TYPES = sorted(QUERY_TERMS)


class FilterMethod(object):
    """
     当一个'method'的参数传递时，它用来覆盖Filter.filter()。
     它代理对过滤器的父进程上的实际方法的调用。
    """
    def __init__(self, filter_instance):
        self.f = filter_instance

    async def __call__(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        qs = self.method(qs, self.f.field_name, value)
        if asyncio.iscoroutine(qs):
            return await qs
        return qs

    @property
    def method(self):
        """
        Resolve the method on the parent filterset.
        """
        instance = self.f

        # 'method'是否一个对象方法
        if callable(instance.method):
            return instance.method

        # otherwise, method is the name of a method on the parent FilterSet.
        assert hasattr(instance, 'parent'), \
            "Filter '%s' must have a parent FilterSet to find '.%s()'" %  \
            (instance.field_name, instance.method)

        parent = instance.parent
        method = getattr(parent, instance.method, None)

        assert callable(method), \
            "Expected parent FilterSet '%s.%s' to have a '.%s()' method." % \
            (parent.__class__.__module__, parent.__class__.__name__, instance.method)

        return method


class Filter(object):
    creation_counter = 0
    field_class = fields.Field

    def __init__(self, field_name=None, lookup_expr='exact', method=None, distinct=False,
                 exclude=False, source=None, **kwargs):
        """

        :param field_name: 对应model的字段名
        :param lookup_expr: 匹配标识
        :param method: 自定义过滤方法
        :param distinct: 是否过滤重复
        :param exclude: 是否启动否查询
        :param kwargs:
        """
        self.field_name = field_name
        self.lookup_expr = lookup_expr
        self._method = None
        self.method = method
        self.distinct = distinct
        self.exclude = exclude
        self.source = source

        self.extra = kwargs
        self.extra.setdefault('required', False)
        self.extra.setdefault('null', True)

        self.creation_counter = Filter.creation_counter
        Filter.creation_counter += 1

    def get_method(self, qs):
        """Return filter method based on whether we're excluding
           or simply filtering.
        """
        return qs.exclude if self.exclude else qs.filter

    @property
    def method(self):
        return self._method

    @method.setter
    def method(self, value):
        self._method = value
        if isinstance(self.filter, FilterMethod):
            del self.filter

        if value is not None:
            self.filter = FilterMethod(self)

    @property
    def field(self):
        if not hasattr(self, '_field'):
            field_kwargs = self.extra.copy()
            self._field = self.field_class(**field_kwargs)

        return self._field

    @staticmethod
    def get_join_fields(qs):
        """
        获得进行查询的model对象的join对象字段
        :return:
        """
        join_model_fields = {}
        for join_models in qs._joins.values():
            for jm in join_models:
                dest_meta = jm.dest._meta
                dest_name = dest_meta.name  # model名
                for f in dest_meta.sorted_fields:
                    join_model_fields["%s.%s" % (dest_name, f.name)] = f

        return join_model_fields

    @staticmethod
    def gen_qs_expression(field_name, lookup, value):
        op_group = models.DJANGO_MAP[lookup]
        op, value = (op_group[0], op_group[1] % value) \
            if len(op_group) == 2 else (op_group[0], value)
        expression = [models.Expression(field_name, op, value)]
        return reduce(operator.and_, expression)

    def filter(self, qs, value):
        if isinstance(value, Lookup):
            lookup = str(value.lookup_type)
            value = value.value
        else:
            lookup = self.lookup_expr

        if value in EMPTY_VALUES:
            return qs

        if self.distinct:
            qs = qs.distinct()

        if self.source is None:
            field_name = self.field_name
        else:
            field_name = self.source

        if isinstance(field_name, models.Field):
            expression = self.gen_qs_expression(field_name, lookup, value)
            qs = self.get_method(qs)(expression)
        elif isinstance(field_name, str) and "." in field_name:
            join_fields = self.get_join_fields(qs)
            field_name = join_fields[field_name.lower()]
            expression = self.gen_qs_expression(field_name, lookup, value)
            qs = self.get_method(qs)(expression)
        else:
            qs = self.get_method(qs)(**{'%s__%s' % (field_name, lookup): value})

        return qs


class CharFilter(Filter):
    field_class = fields.CharField


class BooleanFilter(Filter):
    field_class = fields.NullBooleanField


class DateFilter(Filter):
    field_class = fields.DateField


class DateTimeFilter(Filter):
    field_class = fields.DateTimeField


class TimeFilter(Filter):
    field_class = fields.TimeField


class NumberFilter(Filter):
    """
    数字过滤
    """

    field_class = fields.DecimalField


class ChoiceFilter(Filter):
    """
    下拉框过滤
    """
    field_class = fields.ChoiceField

    def __init__(self, *args, **kwargs):
        self.null_value = kwargs.get('null_value', "null")
        super(ChoiceFilter, self).__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value != self.null_value:
            return super(ChoiceFilter, self).filter(qs, value)

        if isinstance(value, Lookup):
            lookup = str(value.lookup_type)
            value = value.value
        else:
            lookup = self.lookup_expr

        if self.source is None:
            field_name = self.field_name
        else:
            field_name = self.source

        if isinstance(field_name, models.Field):
            expression = self.gen_qs_expression(field_name, lookup, value)
            qs = self.get_method(qs)(expression)
        elif isinstance(field_name, str) and "." in field_name:
            join_fields = self.get_join_fields(qs)
            field_name = join_fields[field_name.lower()]
            expression = self.gen_qs_expression(field_name, lookup, value)
            qs = self.get_method(qs)(expression)
        else:
            qs = self.get_method(qs)(**{'%s__%s' % (field_name, lookup): None})

        return qs.distinct() if self.distinct else qs


class RangeFilter(Filter):
    field_class = RangeField

    def filter(self, qs, value):
        if self.distinct:
            qs = qs.distinct()

        if not value or (value.start is None and value.stop is None):
            return qs

        if self.source is None:
            field_name = self.field_name
        else:
            field_name = self.source

        if isinstance(field_name, models.Field):
            field = field_name
        elif isinstance(field_name, str) and "." in field_name:
            join_fields = self.get_join_fields(qs)
            field = join_fields[field_name.lower()]
        else:
            field = getattr(qs.model_class, field_name)

        if field is None:
            error_msg = "字段{field_name}无法在queryset.model_class或queryset.join的model找到".format(
                field_name=field_name
            )
            raise ImproperlyConfigured(error_msg)

        expressions = None
        if value.start is not None and value.stop is not None:
            expressions = [models.Expression(
                field,
                models.OP.BETWEEN,
                models.Clause(value.start,  models.R('AND'), value.stop)
            )]
        else:
            if value.start is not None:
                expressions = [models.Expression(field, models.OP.GTE, value.start)]
            if value.stop is not None:
                expressions = [models.Expression(field, models.OP.LTE, value.stop)]

        if expressions is None:
            return qs

        qs_expressions = reduce(operator.and_, expressions)
        qs = self.get_method(qs)(qs_expressions)
        return qs


class DateRangeFilter(RangeFilter):
    field_class = DateRangeField


class DateTimeRangeFilter(RangeFilter):
    field_class = DateTimeRangeField


class TimeRangeFilter(RangeFilter):
    field_class = TimeRangeField

