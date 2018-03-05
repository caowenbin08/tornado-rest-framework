# -*- coding: utf-8 -*-
from rest_framework.forms import fields
from rest_framework.utils.constants import QUERY_TERMS, EMPTY_VALUES
from rest_framework.filters.fields import Lookup

__all__ = [
    'Filter',
    'CharFilter',
    'BooleanFilter',
    'DateFilter',
    'TimeFilter',
    'DateTimeFilter',
    'NumberFilter',
    "ChoiceFilter"
]


LOOKUP_TYPES = sorted(QUERY_TERMS)


class FilterMethod(object):
    """
     当一个'method'的参数传递时，它用来覆盖Filter.filter()。
     它代理对过滤器的父进程上的实际方法的调用。
    """
    def __init__(self, filter_instance):
        self.f = filter_instance

    def __call__(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        return self.method(qs, self.f.field_name, value)

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
                 exclude=False, **kwargs):
        """

        :param field_name: 对应model的字段名
        :param lookup_expr:
        :param method:
        :param distinct:
        :param exclude:
        :param kwargs:
        """
        self.field_name = field_name
        self.lookup_expr = lookup_expr
        self._method = None
        self.method = method
        self.distinct = distinct
        self.exclude = exclude

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
        qs = self.get_method(qs)(**{'%s__%s' % (self.field_name, lookup): value})
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

        qs = self.get_method(qs)(**{'%s__%s' % (self.field_name, self.lookup_expr): None})
        return qs.distinct() if self.distinct else qs