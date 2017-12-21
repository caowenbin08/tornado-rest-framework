# coding: utf-8
"""
分页处理
"""
from math import ceil
from collections import OrderedDict
from rest_framework.conf import settings
from rest_framework.core.exceptions import APIException
from rest_framework.utils.urls import replace_query_param, remove_query_param
from rest_framework.core.response import Response
from rest_framework.utils.cached_property import cached_property


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

    def paginate_queryset(self, queryset, request, view=None):
        raise NotImplementedError('paginate_queryset() must be implemented.')

    def get_paginated_response(self, data):
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

    def page_data(self, page_number):
        """
        :param page_number: 页码
        :return:
        """
        self._page_number = page_number
        bottom = (self._page_number - 1) * self.page_size
        if bottom + self.orphans >= self.count:
            bottom = self.count

        return self.queryset.limit(self.page_size).offset(bottom)

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
        # if self.count == 0:
        #     return 0
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
    page_size = settings.PAGINATION["page_number"]["page_size"]
    # 页码查询参数变量名
    page_query_param = settings.PAGINATION["page_number"]["page_query_param"]
    # 自定义每页条数的查询参数名，主要作用于在请求参数中自定义每页条数大小,比如定义为page_size,则请求url参数?page_size=2
    page_size_query_param = settings.PAGINATION["page_number"]["page_size_query_param"]
    # 每页条数最大值
    max_page_size = settings.PAGINATION["page_number"]["max_page_size"]
    last_page_strings = settings.PAGINATION["page_number"]["last_page_strings"]
    first_page_strings = settings.PAGINATION["page_number"]["first_page_strings"]
    paginator_class = Paginator
    orphans = 0
    # 当页码超过总页码时，是否允许返回空列表，True代表可以，False代表抛出APIException异常
    allow_empty_page = settings.PAGINATION["page_number"]["allow_empty_page"]
    # 当页码值小于1时，是否允许直接转为1返回第一页的数据，反之抛出APIException异常；True可以，False不可以
    allow_first_page = settings.PAGINATION["page_number"]["allow_first_page"]
    # 当页码超过总页码时，是否允许返回最后一页的数据列表 True代表可以，False代表不处理
    allow_last_page = settings.PAGINATION["page_number"]["allow_last_page"]

    def get_page_number(self):
        """
        获得页码
        :return:
        """
        page_number = self.request_handler.get_query_argument(self.page_query_param, 1)
        num_pages = self.paginator.num_pages

        if page_number in self.first_page_strings:
            page_number = 1

        if page_number in self.last_page_strings:
            page_number = num_pages

        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            raise APIException(
                status_code=500,
                response_detail="页码必须为数字或对应的标识"
            )

        if page_number < 1:
            if self.allow_first_page:
                page_number = 1
            else:
                raise APIException(
                    status_code=500,
                    response_detail="页码必须大于1"
                )

        if page_number > num_pages:
            if self.allow_last_page:
                page_number = num_pages

            if not self.allow_empty_page:
                raise APIException(
                    status_code=500,
                    response_detail="页码超过总页码，导致空列表"
                )

        return page_number

    def load_paginate_settings(self):
        """
        加载分页相关的配置
        :return:
        """
        if hasattr(self.request_handler, "get_paginate_settings"):
            paginate_settings = getattr(self.request_handler, "get_paginate_settings")()
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
        page_size = self.get_page_size()
        if not page_size:
            return None

        paginator = self.paginator_class(queryset, page_size, self.orphans)
        setattr(self, "paginator", paginator)
        page_number = self.get_page_number()

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
                page_size = self.request_handler.get_query_argument(self.page_size_query_param, self.page_size)
                return _positive_int(page_size, strict=True, cutoff=self.max_page_size)
            except (TypeError, KeyError, ValueError):
                pass

        return self.page_size

    def get_next_link(self):
        """
        下一页url
        :return:
        """
        if not self.paginator.has_next():
            return None

        url = self.request_handler.request.full_url()
        page_number = self.paginator.next_page_number()

        return replace_query_param(url, self.page_query_param, page_number)

    def get_previous_link(self):
        """
        上一页url
        :return:
        """

        if not self.paginator.has_previous():
            return None

        url = self.request_handler.request.full_url()
        page_number = self.paginator.previous_page_number()

        if page_number == 1:
            return remove_query_param(url, self.page_query_param)

        return replace_query_param(url, self.page_query_param, page_number)


class LimitOffsetPagination(BasePagination):
    """
    记录位置分页
    """
    default_limit = settings.PAGINATION["limit_offset"]["default_limit"]
    limit_query_param = settings.PAGINATION["limit_offset"]["limit_query_param"]
    offset_query_param = settings.PAGINATION["limit_offset"]["offset_query_param"]
    max_limit = settings.PAGINATION["limit_offset"]["max_limit"]

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
        if hasattr(self.request_handler, "get_paginate_settings"):
            paginate_settings = getattr(self.request_handler, "get_paginate_settings")()
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
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))

    @property
    def limit(self):
        if self.limit_query_param:
            try:
                limit = self.request_handler.get_query_argument(self.limit_query_param, self.default_limit)
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

    def get_next_link(self):

        if self.offset + self.limit >= self.count:
            return None

        url = self.request_handler.request.full_url()
        url = replace_query_param(url, self.limit_query_param, self.limit)

        offset = self.offset + self.limit

        return replace_query_param(url, self.offset_query_param, offset)

    def get_previous_link(self):
        if self.offset <= 0:
            return None

        url = self.request_handler.request.full_url()
        url = replace_query_param(url, self.limit_query_param, self.limit)

        if self.offset - self.limit <= 0:
            return remove_query_param(url, self.offset_query_param)

        offset = self.offset - self.limit

        return replace_query_param(url, self.offset_query_param, offset)
