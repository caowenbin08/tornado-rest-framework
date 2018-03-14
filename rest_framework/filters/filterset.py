# -*- coding: utf-8 -*-
import asyncio
import copy
from collections import OrderedDict

from rest_framework import forms
from rest_framework.core.exceptions import ImproperlyConfigured
from rest_framework.filters.utils import get_model_field, try_dbfield
from rest_framework.utils.constants import LOOKUP_SEP, ALL_FIELDS
from rest_framework.core.db import models
from rest_framework.filters import filters
from rest_framework.utils.constants import EMPTY_VALUES


class FilterSetOptions(object):
    def __init__(self, options=None):
        self.model = getattr(options, 'model', None)
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)

        self.filter_overrides = getattr(options, 'filter_overrides', {})
        self.form = getattr(options, 'form', forms.Form)


class FilterSetMetaclass(type):
    """
    过滤器元类
    """
    def __new__(mcs, name, bases, attributes):
        attributes['declared_filters'] = mcs.get_declared_filters(bases, attributes)

        new_class = super(FilterSetMetaclass, mcs).__new__(mcs, name, bases, attributes)
        new_class._meta = FilterSetOptions(getattr(new_class, 'Meta', None))
        new_class.base_filters = new_class.get_filters()

        return new_class

    @staticmethod
    def get_declared_filters(bases, attributes):
        """
        获得公开或自定义的过滤器字段
        :param bases:
        :param attributes:
        :return:
        """
        filter_list = [
            (filter_name, attributes.pop(filter_name))
            for filter_name, obj in list(attributes.items())
            if isinstance(obj, filters.Filter)
        ]

        for filter_name, f in filter_list:
            if getattr(f, 'field_name', None) is None:
                f.field_name = filter_name

        filter_list.sort(key=lambda x: x[1].creation_counter)

        # 从基类合并已声明的筛选器
        for base in reversed(bases):
            if hasattr(base, 'declared_filters'):
                filter_list = [
                    (name, f) for name, f
                    in base.declared_filters.items()
                    if name not in attributes
                ] + filter_list

        return OrderedDict(filter_list)


FILTER_FOR_DBFIELD_DEFAULTS = {
    models.CharField:                   {'filter_class': filters.CharFilter},
    models.TextField:                   {'filter_class': filters.CharFilter},
    models.BooleanField:                {'filter_class': filters.BooleanFilter},
    models.DateField:                   {'filter_class': filters.DateFilter},
    models.DateTimeField:               {'filter_class': filters.DateTimeFilter},
    models.TimeField:                   {'filter_class': filters.TimeFilter},
    models.ForeignKeyField:             {'filter_class': filters.NumberFilter},
    models.IntegerField:                {'filter_class': filters.NumberFilter},
    models.SmallIntegerField:           {'filter_class': filters.NumberFilter},
    models.TimestampField:              {'filter_class': filters.NumberFilter},
}


class BaseFilterSet(object):
    FILTER_DEFAULTS = FILTER_FOR_DBFIELD_DEFAULTS

    def __init__(self, data=None, queryset=None):
        if queryset is None:
            queryset = self._meta.model.select().all()

        model = queryset.model_class

        self.data = data or {}
        self.queryset = queryset
        # self.request = request

        self.filters = copy.deepcopy(self.base_filters)
        # model字段对应的过滤处理类的映射
        self.form_field_filter_map = {}

        # propagate the model and filterset to the filters
        for filter_ in self.filters.values():
            filter_.model = model
            filter_.parent = self

    async def is_valid(self):
        """
        Return True if the underlying form has no errors, or False otherwise.
        """
        return await self.form.is_valid()

    @property
    async def errors(self):
        """
        Return an ErrorDict for the data provided for the underlying form.
        """
        return await self.form.errors

    async def filter_queryset(self, queryset):
        """
        必须先调用`is_valid()`方法，如果需要附加其他过滤，则重写此方法
        :param queryset:
        :return:
        """
        for name, value in (await self.form.cleaned_data).items():
            if value in EMPTY_VALUES:
                continue

            for filter_cls in self.form_field_filter_map[name]:
                queryset = filter_cls.filter(queryset, value)
                if asyncio.iscoroutine(queryset):
                    queryset = await queryset
        return queryset

    @property
    async def qs(self):
        if not hasattr(self, '_qs'):
            qs = self.queryset
            qs = await self.filter_queryset(qs)
            self._qs = qs
        return self._qs

    def get_form_class(self):
        """
        Returns a django Form suitable of validating the filterset data.

        This method should be overridden if the form class needs to be
        customized relative to the filterset instance.
        """
        from_fields = OrderedDict()
        for filter_cls in self.filters.values():
            field_name = filter_cls.field_name
            self.form_field_filter_map.setdefault(field_name, []).append(filter_cls)
            from_fields[field_name] = filter_cls.field
        return type(str('%sForm' % self.__class__.__name__), (self._meta.form,), from_fields)

    @property
    def form(self):
        if not hasattr(self, '_form'):
            form_cls = self.get_form_class()
            self._form = form_cls(data=self.data)
        return self._form

    @classmethod
    def get_fields(cls):
        """
        主要包括'Meta.fields'且不在'Meta.exclude'中的字段
        :return:
        """
        meta_class = getattr(cls, "_meta")
        model = meta_class.model
        fields = meta_class.fields
        exclude = meta_class.exclude

        if fields is None and exclude is None:
            raise ImproperlyConfigured(
                "Creating a FilterSet without either the 'fields' attribute "
                "or the 'exclude' attribute is prohibited; filter %s "
                "needs updating." % cls.__name__
            )

        # 无字段设置排除意味着所有其他字段.
        if exclude is not None and fields is None:
            fields = ALL_FIELDS

        if fields == ALL_FIELDS:
            fields = model._meta.sorted_field_names

        # 移除`Meta.exclude`中的字段
        exclude = exclude or []
        if not isinstance(fields, dict):
            fields = [(f, ['exact']) for f in fields if f not in exclude]
        else:
            fields = [(f, lookups) for f, lookups in fields.items() if f not in exclude]

        return OrderedDict(fields)

    @classmethod
    def get_filter_name(cls, field_name, lookup_expr):
        """
        获处过滤字段的字段名
        :param field_name:
        :param lookup_expr:
        :return:
        """

        filter_name = LOOKUP_SEP.join([field_name, lookup_expr])
        _exact = LOOKUP_SEP + 'exact'
        if filter_name.endswith(_exact):
            filter_name = filter_name[:-len(_exact)]

        return filter_name

    @classmethod
    def get_filters(cls):
        """
        为filterset得到所有的过滤器
        这是声明和生成的滤波器
        :return:
        """
        model_class = getattr(cls, "_meta").model
        if not model_class:
            return cls.declared_filters.copy()

        filter_list = OrderedDict()
        fields = cls.get_fields()
        undefined = []

        for field_name, lookups in fields.items():
            field = get_model_field(model_class, field_name)

            if field is None:
                undefined.append(field_name)

            # 外键、多对多关系等
            # if isinstance(field, ForeignObjectRel):
            #     filters[field_name] = cls.filter_for_reverse_field(field, field_name)
            #     continue

            for lookup_expr in lookups:
                filter_name = cls.get_filter_name(field_name, lookup_expr)

                # 如果在类上显式声明筛选器，则跳过生成
                if filter_name in cls.declared_filters:
                    # filters[filter_name] = cls.declared_filters[filter_name]
                    continue

                if field is not None:
                    filter_list[filter_name] = cls.filter_for_field(field, field_name, lookup_expr)

        # 过滤已声明的过滤器
        undefined = [f for f in undefined if f not in cls.declared_filters]
        if undefined:
            raise TypeError(
                "'Meta.fields' contains fields that are not defined on this FilterSet: "
                "%s" % ', '.join(undefined)
            )

        # Add in declared filters. This is necessary since we don't enforce adding
        # declared filters to the 'Meta.fields' option
        filter_list.update(cls.declared_filters)
        return filter_list

    @classmethod
    def filter_for_field(cls, field, field_name, lookup_expr='exact'):
        """
        为过滤字段生成对应的过滤字段处理类
        :param field: 字段对象
        :param field_name: 字段名
        :param lookup_expr:查找表达式
        :return:
        """
        default = {
            'field_name': field_name,
            'lookup_expr': lookup_expr,
        }

        filter_class, params = cls.filter_for_lookup(field, lookup_expr)
        default.update(params)

        return filter_class(**default)

    @classmethod
    def filter_for_lookup(cls, field, lookup_expr):
        """
        生成过滤查找处理类
        :param field:
        :param lookup_expr:
        :return:
        """

        default_filters = cls.FILTER_DEFAULTS.copy()
        if hasattr(cls, '_meta'):
            default_filters.update(cls._meta.filter_overrides)

        data = try_dbfield(default_filters.get, field.__class__) or {}
        filter_class = data.get('filter_class')
        params = data.get('extra', lambda f: {})(field)

        # if there is no filter class, exit early
        if not filter_class:
            return None, {}

        # perform lookup specific checks
        if lookup_expr == 'exact' and field.choices:
            return filters.ChoiceFilter, {'choices': field.choices}

        return filter_class, params


class FilterSet(BaseFilterSet, metaclass=FilterSetMetaclass):
    pass
