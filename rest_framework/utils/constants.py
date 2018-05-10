# -*- coding: utf-8 -*-
import re


QUERY_TERMS = {
    'exact', 'iexact', 'contains', 'icontains', 'gt', 'gte', 'lt', 'lte', 'in',
    'startswith', 'istartswith', 'endswith', 'iendswith', 'range', 'year',
    'month', 'day', 'week_day', 'hour', 'minute', 'second', 'isnull', 'search',
    'regex', 'iregex',
}
EMPTY_VALUES = (None, '', [], (), {})
LOOKUP_SEP = "__"
ALL_FIELDS = "__all__"

FILE_INPUT_CONTRADICTION = object()

REGEX_TYPE = type(re.compile(''))
empty = object()
