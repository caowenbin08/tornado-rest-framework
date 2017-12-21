# -*- coding: utf-8 -*-
import copy
from collections import OrderedDict

from rest_framework import forms
from rest_framework.constants import LOOKUP_SEP, ALL_FIELDS
from rest_framework.core.db import models
from rest_framework.filters import filters
from rest_framework.helpers import modelfieldutil


def remote_queryset(field):
    model = field.remote_field.model
    limit_choices_to = field.get_limit_choices_to()

    return model._default_manager.complex_filter(limit_choices_to)


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

    models.SmallIntegerField:           {'filter_class': filters.NumberFilter},
}


class BaseFilterSet(object):
    FILTER_DEFAULTS = FILTER_FOR_DBFIELD_DEFAULTS

    def __init__(self, data=None, queryset=None):
        if queryset is None:
            queryset = self._meta.model.select().all()

        model = queryset.model_class

        self.is_bound = data is not None
        self.data = data or {}
        self.queryset = queryset
        # self.request = request
        # self.form_prefix = prefix

        self.filters = copy.deepcopy(self.base_filters)

        # propagate the model and filterset to the filters
        for filter_ in self.filters.values():
            filter_.model = model
            filter_.parent = self

    def is_valid(self):
        """
        Return True if the underlying form has no errors, or False otherwise.
        """
        # return self.is_bound and self.form.is_valid()
        return self.form.is_valid()

    @property
    def errors(self):
        """
        Return an ErrorDict for the data provided for the underlying form.
        """
        return self.form.errors

    def filter_queryset(self, queryset):
        """
        必须先调用`is_valid()`方法，如果需要附加其他过滤，则重写此方法
        :param queryset:
        :return:
        """
        for name, value in self.form.data.items():
            queryset = self.filters[name].filter(queryset, value)
        return queryset

    @property
    def qs(self):
        if not hasattr(self, '_qs'):
            qs = self.queryset
            qs = self.filter_queryset(qs)
            # if self.is_bound:
            #     qs = self.filter_queryset(qs)
            self._qs = qs
        return self._qs

    def get_form_class(self):
        """
        Returns a django Form suitable of validating the filterset data.

        This method should be overridden if the form class needs to be
        customized relative to the filterset instance.
        """
        fields = OrderedDict([(name, filter_.field) for name, filter_ in self.filters.items()])

        return type(str('%sForm' % self.__class__.__name__), (self._meta.form,), fields)

    @property
    def form(self):
        if not hasattr(self, '_form'):
            Form = self.get_form_class()
            self._form = Form(self.data)
            # else:
            #     self._form = Form(prefix=self.form_prefix)
        return self._form

    @classmethod
    def get_fields(cls):
        """
        解析应该用于生成筛选器的'fields'参数在filterset中，
        主要包'Meta.fields'并在不'Meta.exclude'中的字段
        :return:
        """
        meta_class = getattr(cls, "_meta")
        model = meta_class.model
        fields = meta_class.fields
        exclude = meta_class.exclude

        assert not (fields is None and exclude is None), (
            "类（cls_name）必须设置`Meta.fields`或`Meta.exclude`属性值".format(cls_name=cls.__name__)
        )

        # 无字段设置排除意味着所有其他字段.
        if exclude is not None and fields is None:
            fields = ALL_FIELDS

        if fields == ALL_FIELDS:
            fields = modelfieldutil.get_all_model_fields(model)

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

        filters = OrderedDict()
        fields = cls.get_fields()
        undefined = []

        for field_name, lookups in fields.items():
            field = modelfieldutil.get_model_field(model_class, field_name)

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
                    filters[filter_name] = cls.declared_filters[filter_name]
                    continue

                if field is not None:
                    filters[filter_name] = cls.filter_for_field(field, field_name, lookup_expr)

        # 过滤已声明的过滤器
        undefined = [f for f in undefined if f not in cls.declared_filters]
        if undefined:
            raise TypeError(
                "'Meta.fields' contains fields that are not defined on this FilterSet: "
                "%s" % ', '.join(undefined)
            )

        # Add in declared filters. This is necessary since we don't enforce adding
        # declared filters to the 'Meta.fields' option
        filters.update(cls.declared_filters)
        return filters

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

        # assert filter_class is not None, (
        #     "%s resolved field '%s' with '%s' lookup to an unrecognized field "
        #     "type %s. Try adding an override to 'Meta.filter_overrides'. See: "
        #     "https://django-filter.readthedocs.io/en/master/ref/filterset.html#customise-filter-generation-with-filter-overrides"
        # ) % (cls.__name__, field_name, lookup_expr, field.__class__.__name__)

        return filter_class(**default)

    @classmethod
    def filter_for_reverse_field(cls, field, field_name):
        rel = field.field.remote_field
        queryset = field.field.model._default_manager.all()
        default = {
            'field_name': field_name,
            'queryset': queryset,
        }
        if rel.multiple:
            return ModelMultipleChoiceFilter(**default)
        else:
            return ModelChoiceFilter(**default)

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

        data = modelfieldutil.try_dbfield(default_filters.get, field.__class__) or {}
        filter_class = data.get('filter_class')
        params = data.get('extra', lambda f: {})(field)

        # if there is no filter class, exit early
        if not filter_class:
            return None, {}

        # perform lookup specific checks
        if lookup_expr == 'exact' and field.choices:
            return filters.ChoiceFilter, {'choices': field.choices}

        if lookup_expr == 'isnull':
            data = try_dbfield(DEFAULTS.get, models.BooleanField)

            filter_class = data.get('filter_class')
            params = data.get('extra', lambda field: {})(field)
            return filter_class, params

        if lookup_expr == 'in':
            class ConcreteInFilter(BaseInFilter, filter_class):
                pass
            ConcreteInFilter.__name__ = cls._csv_filter_class_name(
                filter_class, lookup_expr
            )

            return ConcreteInFilter, params

        if lookup_expr == 'range':
            class ConcreteRangeFilter(BaseRangeFilter, filter_class):
                pass
            ConcreteRangeFilter.__name__ = cls._csv_filter_class_name(
                filter_class, lookup_expr
            )

            return ConcreteRangeFilter, params

        return filter_class, params

    @classmethod
    def _csv_filter_class_name(cls, filter_class, lookup_type):
        """
        Generate a suitable class name for a concrete filter class. This is not
        completely reliable, as not all filter class names are of the format
        <Type>Filter.

        ex::

            FilterSet._csv_filter_class_name(DateTimeFilter, 'in')

            returns 'DateTimeInFilter'

        """
        # DateTimeFilter => DateTime
        type_name = filter_class.__name__
        if type_name.endswith('Filter'):
            type_name = type_name[:-6]

        # in => In
        lookup_name = lookup_type.capitalize()

        # DateTimeInFilter
        return str('%s%sFilter' % (type_name, lookup_name))


class FilterSet(BaseFilterSet, metaclass=FilterSetMetaclass):
    pass


def filterset_factory(model, fields=ALL_FIELDS):
    meta = type(str('Meta'), (object,), {'model': model, 'fields': fields})
    filterset = type(str('%sFilterSet' % model._meta.object_name),
                     (FilterSet,), {'Meta': meta})
    return filterset
