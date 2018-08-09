# -*- coding: utf-8 -*-
import operator
from functools import reduce

from rest_framework.conf import settings
from rest_framework.core.db import models
from rest_framework.core.exceptions import ImproperlyConfigured, ValidationError
from rest_framework.filters import filterset


class BaseFilterBackend(object):
    """
    过滤处理基类
    """

    async def filter_queryset(self, request, queryset, view):
        """
        组拼生成对应的过滤queryset，此方法必须子类继承实现
        :param request: 请求对象
        :param queryset: 查询对象
        :param view: 请求view处理对象
        :return:
        """
        raise NotImplementedError(".filter_queryset()方法子类必须实现")

    @staticmethod
    def get_query_model_fields(queryset):
        """
        获得进行查询的model对象及所有join对象
        :param queryset:
        :return:
        """
        query_model_fields = {f.name: f for f in queryset.model_class._meta.sorted_fields}
        for join_models in queryset._joins.values():
            for jm in join_models:
                dest_meta = jm.dest._meta
                dest_name = dest_meta.name  # model名
                for f in dest_meta.sorted_fields:
                    query_model_fields["%s.%s" % (dest_name, f.name)] = f

        return query_model_fields


class SearchFilter(BaseFilterBackend):
    """
    搜索框的过滤
    """
    # 接收搜索值的参数变量名
    search_param = settings.SEARCH_PARAM
    lookup_prefixes = {
        '^': (models.OP.LIKE, '%s%%'),  # 前缀匹配
        '=': (models.OP.EQ, '%s'),      # 完整匹配
        '@': (models.OP.ILIKE, '%%%s%%'),  #模糊匹配
        '$': (models.OP.LIKE, '%%%s'),    # 后缀匹配
    }

    def get_search_terms(self, request_handler):
        """
        从请求的参数取出`self.search_param`标识的参数值，
        例：?search=cao
        :param request_handler:
        :return:
        """
        search_param = request_handler.request_data.get(self.search_param, "")
        return search_param.replace(',', ' ').split()

    def construct_search(self, query_model_fields, field_name):
        """
        根据搜索字段的配置，构建搜索匹配模式进行返回
        :param query_model_fields:
        :param field_name:
        :return:
        """
        lookup = self.lookup_prefixes.get(field_name[0])

        if lookup:
            field_name = field_name[1:]
        else:
            lookup = (models.OP.ILIKE, '%%%s%%')

        field = query_model_fields.get(field_name.lower(), None)
        if field is None:
            error_msg = "搜索字段{field_name}无法在queryset.model_class或queryset.join的model找到".format(
                field_name=field_name
            )
            raise ImproperlyConfigured(error_msg)

        return field, lookup[0], lookup[1]

    async def filter_queryset(self, request_handler, queryset):
        search_fields = request_handler.search_fields
        search_terms = self.get_search_terms(request_handler)

        if not search_fields or not search_terms:
            return queryset

        query_model_fields = self.get_query_model_fields(queryset)
        orm_lookups = [self.construct_search(query_model_fields, str(search_field))
                       for search_field in search_fields]

        for search_term in search_terms:
            queries = [models.Expression(lhs, op, rhs % search_term) for lhs, op, rhs in orm_lookups]
            queryset = queryset.filter(reduce(operator.or_, queries))

        return queryset


class OrderingFilter(BaseFilterBackend):
    """
    排序处理类
    """
    # 接收排序参数的参数变量名
    ordering_param = settings.ORDERING_PARAM
    # 用于排序的字段集合
    ordering_fields = None

    def get_ordering(self, request_handler, queryset):
        ordering_fields = request_handler.request_data.get(self.ordering_param)
        if ordering_fields:
            ordering = self.remove_invalid_fields(request_handler, queryset, ordering_fields)
            if ordering:
                return ordering

        return self.get_default_ordering(request_handler)

    @staticmethod
    def get_default_ordering(request_handler):
        ordering = getattr(request_handler, 'ordering', None)
        if isinstance(ordering, str):
            return ordering,

        return ordering

    def get_valid_fields(self, request_handler, queryset):
        valid_fields = getattr(request_handler, 'ordering_fields', self.ordering_fields)

        if valid_fields is None or valid_fields == "__all__":
            return self.get_query_model_fields(queryset).keys()

        return valid_fields

    def remove_invalid_fields(self, request_handler, queryset, ordering_fields):
        valid_fields = self.get_valid_fields(request_handler, queryset)
        return [field for field in ordering_fields if field.lstrip('-').lower() in valid_fields]

    def construct_ordering(self, ordering, queryset):
        query_model_fields = self.get_query_model_fields(queryset)
        norm_order_by = []
        query_model_name = queryset.model_class.__name__
        for item in ordering:
            if isinstance(item, models.Field):
                prefix = '-' if item._ordering.lower() == 'desc' else ''
                if query_model_name == item.model_class.__name__:
                    item = "{prefix}{field_name}".format(prefix=prefix, field_name=item.name)
                else:
                    item = "{prefix}{model_name}.{field_name}".format(
                        prefix=prefix,
                        model_name=item.model_class._meta.name,
                        field_name=item.name
                    )

            prefix = "-" if "-" in item else "+"
            field_name = item.lstrip(prefix)
            field = query_model_fields.get(field_name, None)
            if field is None:
                error_msg = "排序字段{field_name}无法在queryset.model_class或queryset.join的model找到".format(
                    field_name=field_name
                )
                raise ImproperlyConfigured(error_msg)

            norm_order_by.append(field.desc() if item.startswith('-') else field.asc())

        return norm_order_by

    async def filter_queryset(self, request_handler, queryset):
        ordering = self.get_ordering(request_handler, queryset)

        if ordering:
            norm_order_by = self.construct_ordering(ordering, queryset)
            return queryset.order_by(*norm_order_by)

        return queryset


class FilterBackend(BaseFilterBackend):
    """
    过滤搜索处理类
    """
    default_filter_set = filterset.FilterSet
    raise_exception = True

    lookup_prefixes = {
        '^': 'istartswith',  # 前缀匹配
        '=': "exact",      # 完整匹配
        '@': 'icontains',  #模糊匹配
        '$': 'iendswith',    # 后缀匹配
    }

    def get_filter_class(self, request_handler, queryset=None):
        filter_class = getattr(request_handler, 'filter_class', None)
        filter_fields = getattr(request_handler, 'filter_fields', ())
        filter_field_lookup_map = {}
        for filter_field in filter_fields:
            lookup = self.lookup_prefixes.get(filter_field[0])
            if lookup:
                filter_field = filter_field[1:]
            else:
                lookup = "exact"

            filter_field_lookup_map[filter_field] = [lookup]

        if filter_class:
            filter_model = getattr(filter_class, "_meta").model

            # FilterSets不需要指定一个元类
            if filter_model and queryset is not None:
                assert issubclass(queryset.model_class, filter_model), \
                    'FilterSet model %s does not match queryset model %s' % \
                    (filter_model, queryset.model_class)

            return filter_class

        if filter_field_lookup_map and queryset is not None:
            MetaBase = getattr(self.default_filter_set, 'Meta', object)

            class AutoFilterSet(self.default_filter_set):
                class Meta(MetaBase):
                    model = queryset.model_class
                    fields = filter_field_lookup_map

            return AutoFilterSet

        return None

    async def filter_queryset(self, request_handler, queryset):
        filter_class = self.get_filter_class(request_handler, queryset)

        if filter_class:
            filterset = filter_class(request_handler.request_data, queryset)
            if not await filterset.is_valid() and self.raise_exception:
                raise ValidationError(await filterset.errors)
            return await filterset.qs
        return queryset

