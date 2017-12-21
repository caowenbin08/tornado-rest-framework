# -*- coding: utf-8 -*-

__author__ = 'caowenbin'

QUERY_TERMS = {
    'exact', 'iexact', 'contains', 'icontains', 'gt', 'gte', 'lt', 'lte', 'in',
    'startswith', 'istartswith', 'endswith', 'iendswith', 'range', 'year',
    'month', 'day', 'week_day', 'hour', 'minute', 'second', 'isnull', 'search',
    'regex', 'iregex',
}
EMPTY_VALUES = ([], (), {}, '', None)
LOOKUP_SEP = "."
ALL_FIELDS = "__all__"
