# coding: utf-8
"""
分页处理
"""
from math import ceil
from collections import OrderedDict
from rest_framework.conf import settings
from rest_framework.helpers.urls import replace_query_param, remove_query_param
from rest_framework.response import Response
from rest_framework.helpers.cached_property import cached_property


class InvalidPage(Exception):
    pass


class PageNotAnInteger(InvalidPage):
    pass


class EmptyPage(InvalidPage):
    pass


def _positive_int(integer_string, strict=False, cutoff=None):
    """
    Cast a string to a strictly positive integer.
    """
    ret = int(integer_string)
    if ret < 0 or (ret == 0 and strict):
        raise ValueError()
    if cutoff:
        ret = min(ret, cutoff)
    return ret


class BasePagination(object):
    display_page_controls = False

    def paginate_queryset(self, queryset, request, view=None):
        raise NotImplementedError('paginate_queryset() must be implemented.')

    def get_paginated_response(self, data):
        raise NotImplementedError('get_paginated_response() must be implemented.')

    @staticmethod
    def get_results(data):
        return data['results']


class Paginator(object):

    def __init__(self, queryset, page_size, orphans=0, allow_empty_first_page=True):
        """
        :param queryset:
        :param page_size:
        :param orphans:
        :param allow_empty_first_page:
        """
        self.queryset = queryset
        self.page_size = page_size
        self._page_number = 0
        self.orphans = orphans
        self.allow_empty_first_page = allow_empty_first_page

    def validate_number(self, page_number):
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            raise PageNotAnInteger('That page number is not an integer')

        if page_number < 1:
            raise EmptyPage('That page number is less than 1')

        if page_number > self.num_pages:
            if self._page_number == 1 and self.allow_empty_first_page:
                pass
            else:
                raise EmptyPage('That page contains no results')

        return page_number

    def page_data(self, page_number):
        """
        :param page_number: 页码
        :return:
        """
        self._page_number = self.validate_number(page_number)
        bottom = (self._page_number - 1) * self.page_size
        top = bottom + self.page_size
        if top + self.orphans >= self.count:
            top = self.count

        return self.queryset.limit(top).offset(bottom)

    @cached_property
    def count(self):
        """
        总记录大小
        """
        try:
            return self.queryset.count()
        except (AttributeError, TypeError):
            return len(self.queryset)

    @cached_property
    def num_pages(self):
        """
        总页数
        """
        if self.count == 0 and not self.allow_empty_first_page:
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
        return self.validate_number(self._page_number + 1)

    def previous_page_number(self):
        """
        上一次的页码
        :return:
        """
        return self.validate_number(self._page_number - 1)


class PageNumberPagination(BasePagination):
    """
    采用分页码的方式分页
    """
    # 每页条数
    page_size = settings.PAGE_SIZE
    # 页码查询参数变量名
    page_query_param = 'page'
    # 自定义每页条数的查询参数名，主要作用于在请求参数中自定义每页条数大小
    page_size_query_param = None
    # 每页条数最大值
    max_page_size = None
    last_page_strings = ('last',)
    paginator_class = Paginator
    orphans = 0
    allow_empty_first_page = True

    def paginate_queryset(self, queryset, request):
        """
        分页查询
        :param queryset:
        :param request:
        :return:
        """
        self.request = request
        page_size = self.get_page_size()
        if not page_size:
            return None

        self.paginator = self.paginator_class(queryset, page_size, self.orphans, self.allow_empty_first_page)
        page_number = self.request.query_arguments.get(self.page_query_param, [1])[-1]
        if page_number in self.last_page_strings:
            page_number = self.paginator.num_pages

        return self.paginator.page_data(page_number)

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.paginator.count),
            ('num_pages', self.paginator.num_pages),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
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
                return _positive_int(
                    self.request.query_arguments[self.page_size_query_param][-1],
                    strict=True,
                    cutoff=self.max_page_size
                )
            except (KeyError, ValueError):
                pass

        return self.page_size

    def get_next_link(self):
        """
        下一页url
        :return:
        """
        if not self.paginator.has_next():
            return None

        url = self.request.full_url()
        page_number = self.paginator.next_page_number()

        return replace_query_param(url, self.page_query_param, page_number)

    def get_previous_link(self):
        """
        上一页url
        :return:
        """

        if not self.paginator.has_previous():
            return None

        url = self.request.full_url()
        page_number = self.paginator.previous_page_number()

        if page_number == 1:
            return remove_query_param(url, self.page_query_param)

        return replace_query_param(url, self.page_query_param, page_number)


class LimitOffsetPagination(BasePagination):
    """
    记录位置分页
    """
    default_limit = settings.PAGE_SIZE
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = None

    @staticmethod
    def get_count(queryset):
        try:
            return queryset.count()
        except (AttributeError, TypeError):
            return len(queryset)

    def paginate_queryset(self, queryset, request):
        self.request = request

        if self.limit is None:
            return None

        self.count = self.get_count(queryset)

        if self.count == 0 or self.offset > self.count:
            return []

        return list(queryset[self.offset:self.offset + self.limit])

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))

    @property
    def limit(self):
        if self.limit_query_param:
            try:
                return _positive_int(
                    self.request.query_arguments[self.limit_query_param][-1],
                    strict=True,
                    cutoff=self.max_limit
                )
            except (KeyError, ValueError):
                pass

        return self.default_limit

    @property
    def offset(self):
        try:
            return _positive_int(
                self.request.query_arguments[self.offset_query_param][-1],
            )
        except (KeyError, ValueError):
            return 0

    def get_next_link(self):

        if self.offset + self.limit >= self.count:
            return None

        url = self.request.full_url()
        url = replace_query_param(url, self.limit_query_param, self.limit)

        offset = self.offset + self.limit

        return replace_query_param(url, self.offset_query_param, offset)

    def get_previous_link(self):
        if self.offset <= 0:
            return None

        url = self.request.full_url()
        url = replace_query_param(url, self.limit_query_param, self.limit)

        if self.offset - self.limit <= 0:
            return remove_query_param(url, self.offset_query_param)

        offset = self.offset - self.limit

        return replace_query_param(url, self.offset_query_param, offset)
