# coding: utf-8
"""
分页处理
"""
from math import ceil
from collections import OrderedDict
from rest_framework.core.response import Response
from rest_framework.core.translation import lazy_translate as _
from rest_framework.core.exceptions import PaginationError
from rest_framework.lib.orm.query import AsyncEmptyQuery
from rest_framework.utils.cached_property import cached_property, async_cached_property


def _positive_int(integer_string, strict=False, cutoff=None):
    """
    整数字符串转为严格的整正数
    :param integer_string:
    :param strict:
    :param cutoff:
    :return:
    """

    ret = int(integer_string)
    if ret < 0 or (ret == 0 and strict):
        raise ValueError()
    if cutoff:
        ret = min(ret, cutoff)
    return ret


class BasePagination(object):
    display_page_controls = False

    async def paginate_queryset(self, queryset, request, view=None):
        raise NotImplementedError('paginate_queryset() must be implemented.')

    async def get_paginated_response(self, data):
        raise NotImplementedError('get_paginated_response() must be implemented.')

    @staticmethod
    def get_results(data):
        return data['results']


class Paginator(object):

    def __init__(self, queryset, page_size, orphans=0):
        """
        :param queryset:
        :param page_size:
        :param orphans:
        """
        self.queryset = queryset
        self.page_size = page_size
        self._page_number = 0
        self.orphans = orphans

    async def page_data(self, page_number):
        """
        :param page_number: 页码
        :return:
        """
        self._page_number = page_number
        bottom = (self._page_number - 1) * self.page_size
        count = self.count
        if bottom + self.orphans >= count:
            bottom = self.count

        return self.queryset.limit(self.page_size).offset(bottom)

    @async_cached_property
    async def count(self):
        """
        总记录大小
        """
        try:
            count = await self.queryset.count()
            return count
        except (AttributeError, TypeError):
            return len(await self.queryset)

    @cached_property
    def num_pages(self):
        """
        总页数
        """
        if self.count == 0:
            return 0
        hits = max(1, self.count - self.orphans)
        return int(ceil(hits / float(self.page_size)))

    def has_next(self):
        """
        判断是否有下一页
        :return:
        """
        return self._page_number < self.num_pages

    def has_previous(self):
        """
        是否有上一页
        :return:
        """
        return self._page_number > 1

    def next_page_number(self):
        """
        下一次页码
        :return:
        """
        return self._page_number + 1

    def previous_page_number(self):
        """
        上一次的页码
        :return:
        """
        return self._page_number - 1


class PageNumberPagination(BasePagination):
    """
    采用分页码的方式分页
    """
    # 每页条数
    page_size = 10
    # 页码查询参数变量名
    page_query_param = b"page"
    # 自定义每页条数的查询参数名，主要作用于在请求参数中自定义每页条数大小,比如定义为page_size,则请求url参数?page_size=2
    page_size_query_param = b"page_size"
    # 每页条数最大值
    max_page_size = None
    # 默认可以作为最后页码的字符串集合
    last_page_strings = (b'last',)
    # 默认可以作为第一页码的字符串集合
    first_page_strings = (b'first',)
    paginator_class = Paginator
    orphans = 0
    # 当页码超过总页码时，是否允许返回空列表，True代表可以，False代表抛出APIException异常
    allow_empty_page = True
    # 当页码值小于1时，是否允许直接转为1返回第一页的数据，反之抛出APIException异常；True可以，False不可以
    allow_first_page = True
    # 当页码超过总页码时，是否允许返回最后一页的数据列表 True代表可以，False代表不处理
    allow_last_page = True

    def get_page_number(self):
        """
        获得页码
        :return:
        """
        page_number = self.request_handler.request_data.get(self.page_query_param, 1)
        num_pages = self.paginator.num_pages

        if page_number in self.first_page_strings:
            page_number = 1

        if page_number in self.last_page_strings:
            page_number = num_pages

        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            raise PaginationError(detail=_("The page number must be a number or page string"))

        if page_number < 1:
            if self.allow_first_page:
                page_number = 1
            else:
                raise PaginationError(detail=_("The page number must be greater than 1"))

        if page_number > num_pages:
            if self.allow_last_page:
                page_number = num_pages

            if not self.allow_empty_page:
                raise PaginationError(detail=_("The page number exceeds the total page number"))

        return page_number

    def load_paginate_settings(self):
        """
        加载分页相关的配置
        :return:
        """
        if hasattr(self.request_handler, "overload_paginate_settings"):
            paginate_settings = getattr(self.request_handler, "overload_paginate_settings")()
            if paginate_settings:
                for k, v in paginate_settings.items():
                    setattr(self, k, v)

    async def paginate_queryset(self, request_handler, queryset):
        """
        :param request_handler: 请求处理类对象本身，即view
        :param queryset:
        :return:
        """
        setattr(self, "request_handler", request_handler)
        self.load_paginate_settings()
        page_size = self.get_page_size()
        if not page_size:
            return AsyncEmptyQuery()

        paginator = self.paginator_class(queryset, page_size, self.orphans)
        setattr(self, "paginator", paginator)
        if await self.paginator.count == 0:
            return AsyncEmptyQuery()

        page_number = self.get_page_number()

        return await self.paginator.page_data(page_number)

    async def get_paginated_response(self, data):
        count = self.paginator.count
        return Response(OrderedDict([
            ('count', count),
            ('num_pages', self.paginator.num_pages),
            ('results', data)
        ]))

    def get_page_size(self):
        """
        每页条数
        如果用户自定义了page_size_query_param变量并在请求参数中传了过来，则为其反之为page_size
        :return:
        """
        if self.page_size_query_param:
            try:
                page_size = self.request_handler.request_data.get(
                    self.page_size_query_param, self.page_size
                )
                return _positive_int(page_size, strict=True, cutoff=self.max_page_size)
            except (TypeError, KeyError, ValueError):
                pass

        return self.page_size


class LimitOffsetPagination(BasePagination):
    """
    记录位置分页
    """
    # 默认分页列表条目数
    default_limit = 10
    limit_query_param = b'limit'
    offset_query_param = b'offset'
    # 默认最大的列表条目数, 默认不限制
    max_limit = None

    @staticmethod
    def get_count(queryset):
        try:
            return queryset.count()
        except (AttributeError, TypeError):
            return len(queryset)

    def load_paginate_settings(self):
        """
        加载分页相关的配置
        :return:
        """
        if hasattr(self.request_handler, "overload_paginate_settings"):
            paginate_settings = getattr(self.request_handler, "overload_paginate_settings")()
            if paginate_settings:
                for k, v in paginate_settings.items():
                    setattr(self, k, v)

    def paginate_queryset(self, request_handler, queryset):
        """
        :param request_handler: 请求处理类对象本身，即view
        :param queryset:
        :return:
        """
        setattr(self, "request_handler", request_handler)
        self.load_paginate_settings()

        if self.limit is None:
            return None

        count = self.get_count(queryset)
        setattr(self, "count", count)

        if self.count == 0 or self.offset > self.count:
            return []

        return list(queryset[self.offset:self.offset + self.limit])

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.count),
            ('results', data)
        ]))

    @property
    def limit(self):
        if self.limit_query_param:
            try:
                limit = self.request_handler.request_data.get(
                    self.limit_query_param, self.default_limit
                )
                return _positive_int(limit, strict=True, cutoff=self.max_limit)
            except (TypeError, KeyError, ValueError):
                pass

        return self.default_limit

    @property
    def offset(self):
        try:
            offset = self.request_handler.get_query_argument(self.offset_query_param, 0)
            return _positive_int(offset)
        except (TypeError, KeyError, ValueError):
            return 0
