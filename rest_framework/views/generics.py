# -*- coding: utf-8 -*-
import asyncio
import traceback
import logging

from tornado import gen
from tornado import httputil
from tornado import iostream
from tornado.log import app_log, gen_log
from tornado.web import RequestHandler, HTTPError

from rest_framework.core import exceptions
from rest_framework.core.exceptions import APIException
from rest_framework.core.translation import locale
from rest_framework.views import mixins
from rest_framework.conf import settings
from rest_framework.core.db import models
from rest_framework.utils.transcoder import force_text
from rest_framework.utils import status
from rest_framework.utils.cached_property import cached_property
from rest_framework.utils.functional import import_object
from rest_framework.core.parsers import get_parsers
from rest_framework.core.response import Response
from rest_framework.views.mixins import BabelTranslatorMixin
from rest_framework.core.translation import gettext as _

__author__ = 'caowenbin'

__all__ = [
    'GenericAPIHandler',
    'ListAPIHandler',
    'CreateAPIHandler',
    'RetrieveUpdateAPIHandler',
    'DestroyAPIHandler'
]

view_log = logging.getLogger("rest_framework.views")


def _has_stream_request_body(cls):
    if not issubclass(cls, RequestHandler):
        raise TypeError("expected subclass of RequestHandler, got %r", cls)
    return getattr(cls, '_stream_request_body', False)


class BaseAPIHandler(RequestHandler, BabelTranslatorMixin):
    """
    基础接口处理类
    """
    # 不需要检查xsrf的请求方法
    NOT_CHECK_XSRF_METHOD = ("GET", "HEAD", "OPTIONS")

    def __init__(self, application, request, **kwargs):
        self.request_data = None
        super(BaseAPIHandler, self).__init__(application, request, **kwargs)

    def data_received(self, chunk):
        pass

    def prepare(self):
        """
        继承重写，主要解析json数据，请求可以直接self.json_data获取请求数据
        :return:
        """
        self._load_data_and_files()
        return super(BaseAPIHandler, self).prepare()

    def select_parser(self):
        parsers = get_parsers()
        content_type = self.request.headers.get("Content-Type", "")
        print("========content_type===", content_type)
        for parser in parsers:
            if parser.media_type == content_type:
                return parser
        return None

    def _parse_query_arguments(self):
        """
        解析查询参数，比如排序、过滤、搜索等参数值
        :return:
        """
        query_arguments = self.request.query_arguments
        return {k: force_text(v) if len(v) > 1 else force_text(v[-1])
                for k, v in query_arguments.items() if v}

    def _load_data_and_files(self):
        """
        解析请求参数
        :return:
        """
        content_type = self.request.headers.get("Content-Type", "")
        if not content_type:
            self.request_data = self._parse_query_arguments()
            self.request.data = self.request_data
            return

        parser = self.select_parser()
        if not parser:
            error_detail = 'Unsupported media type "%s" in request' % content_type
            raise APIException(error_detail, status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        self.request_data = parser.parse(self.request)
        # content_type = self.request.headers.get("Content-Type", "")
        #
        # if content_type == "application/json":
        #     self.json_data = json_decode(self.request.body) if self.request.body else {}
        #
        # elif content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
        #     self.json_data = self.request.body_arguments

        self.request.data = self.request_data

    @gen.coroutine
    def _execute(self, transforms, *args, **kwargs):

        self._transforms = transforms
        method = self.request.method

        try:
            if method not in self.SUPPORTED_METHODS:
                raise HTTPError(405)

            self.path_args = [self.decode_argument(arg) for arg in args]
            self.path_kwargs = dict((k, self.decode_argument(v, name=k)) for (k, v) in kwargs.items())

            if method not in self.NOT_CHECK_XSRF_METHOD and settings.XSRF_COOKIES:
                self.check_xsrf_cookie()

            result = self.prepare()

            if result is not None:
                yield result
            if self._prepared_future is not None:
                self._prepared_future.set_result(None)

            if self._finished:
                return

            if _has_stream_request_body(self.__class__):
                try:
                    yield self.request.body
                except iostream.StreamClosedError:
                    return

            handler = getattr(self, method.lower())
            handler_result = handler(*self.path_args, **self.path_kwargs)
            # 如果 handler_result 是 协同对象，则返回 True，其可以基于生成器或 async def 协同程序
            if asyncio.iscoroutine(handler_result):
                result = yield from handler_result
            else:
                result = handler_result
            result = self.finalize_response(result)

            if result is not None:
                yield result

            if self._auto_finish and not self._finished:
                self.finish()

        except Exception as e:
            try:
                self._handle_request_exception(e)
            except Exception:
                app_log.error("Exception in exception handler", exc_info=True)
                data = {'error_detail': "Internal Server Error"}
                error_response = Response(data, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
                self.write_error(error_response)

            if self._prepared_future is not None and not self._prepared_future.done():
                self._prepared_future.set_result(None)

    def send_error(self, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, **kwargs):
        if self._headers_written:
            gen_log.error("Cannot send error response after headers written")
            if not self._finished:
                try:
                    self.finish()
                except Exception:
                    gen_log.error("Failed to flush partial response", exc_info=True)
            return
        self.clear()
        exc = kwargs['exc_info'][1] if 'exc_info' in kwargs else None
        error_response = self.handle_exception(exc)

        if error_response is None:
            try:
                data = {'error_detail': httputil.responses[status_code]}
            except KeyError:
                raise ValueError("unknown status code %d" % status_code)

            error_response = Response(data, status_code=status_code)

        try:
            self.write_error(error_response)
        except Exception as exc:
            self.set_status(status.HTTP_500_INTERNAL_SERVER_ERROR)
            app_log.error("Uncaught exception in write_error", exc_info=True)

        if not self._finished:
            self.finish()

    def write_error(self, response):
        self.finalize_response(response)
        self.finish()

    def handle_exception(self, exc):
        """
        统一异常处理
        :param exc:
        :return:
        """
        error_response = None

        if isinstance(exc, exceptions.APIException):
            headers = {}

            if isinstance(exc.detail, (list, dict)):
                data = exc.detail
            else:
                data = {'error_detail': exc.detail}

            error_response = Response(data, status_code=exc.status_code, headers=headers)

        elif isinstance(exc, HTTPError):
            data = {'error_detail': _('Not found')}

            error_response = Response(data, status_code=exc.status_code)

        return error_response

    def finalize_response(self, response, *args, **kwargs):
        if not isinstance(response, Response):
            raise TypeError("Request return value types must be the Response")
        self.set_status(response.status_code)
        self.set_header('Content-Type', response.content_type)
        return self.write(response.data)

    def get_user_locale(self):
        if self.current_user:
            return locale.get(self.current_user.locale)

        # Fallback to browser based locale detection
        return self.get_browser_locale()


class GenericAPIHandler(BaseAPIHandler):
    # 查询处理对象
    queryset = None
    # 序列化类
    serializer_class = None
    # 提交表单类
    form_class = None
    # 作用于get_object()方法的字段名（一般都是id），查询一条记录
    lookup_field = 'id'
    # url与view的关键参数名称
    lookup_url_kwarg = None
    # 分页处理类
    pagination_class = "rest_framework.core.pagination.PageNumberPagination"
    # 页面模板名
    template_name = ""
    # 修改或创建是否序列化实例对象返回, False代表只返回主键值，True代表返回实例对象
    need_obj_serializer = False
    # 检查参数不正确是否抛出异常， False代表为抛出 True代表直接抛出ValidationError
    form_valid_raise_except = False
    # 查询过滤处理类，主要是搜索、过滤
    filter_backend_list = (
        "rest_framework.filters.FilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter"
    )
    # 搜索字段列表
    search_fields = ()
    # '__all__'或 model.field的字符串或+/-field（不匹配join的model字段）的元组/列表
    ordering_fields = None
    # 用户没有传入排序参数数据或传入的排序参数字段不在`ordering_fields`或model中时，此设置就作为默认的排序生效
    # 属性值可以是model.field.desc/asc()、+/-model.field的字符串或+/-field（不匹配join的model字段）的元组/列表
    ordering = None
    initial = {}

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        return self.initial.copy()

    def get_queryset(self, queryset=None):
        """
        生成查询操作对象，即SelectQuery
        :param queryset:
        :return:
        """
        queryset = queryset if queryset is not None else self.queryset
        if queryset is None:
            if self.form_class is not None:
                queryset = getattr(self.form_class.Meta, "model")
            elif self.serializer_class is not None:
                queryset = getattr(self.serializer_class.Meta, "model")

        assert queryset is not None, (
            "'%s' should either include a `queryset` attribute, "
            "or override the `get_queryset()` method."
            % self.__class__.__name__
        )

        if not isinstance(queryset, models.SelectQuery) and issubclass(queryset, models.Model):
            queryset = queryset.select()
        return queryset

    @cached_property
    def load_filter_class(self):
        """
        :return:
        """
        return [import_object(backend) for backend in self.filter_backend_list if backend is not None]

    def filter_queryset(self, queryset):
        for backend in self.load_filter_class:
            queryset = backend().filter_queryset(self, queryset)
        return queryset

    def get_object_or_404(self, queryset, *args, **kwargs):
        """
         查询对象，如果对象不存在则抛出404
        :param queryset:
        :param args:
        :param kwargs:
        :return:
        """
        try:
            return self.get_queryset(queryset).filter(*args, **kwargs).get()
        except AttributeError:
            queryset_name = queryset.__name__ if isinstance(queryset, type) else queryset.__class__.__name__
            raise ValueError(
                "First argument to get_object_or_404() must be a Model or SelectQuery, not '%s'." % queryset_name
            )
        except queryset.model_class.DoesNotExist:
            raise exceptions.APIException(
                status_code=404,
                response_detail=Response(data=self.error_msg_404) if self.error_msg_404 else None
            )

    def get_object(self):
        """
        查询单一对象，如果为空抛出404
        """
        queryset = self.filter_queryset(self.get_queryset()).naive()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        assert lookup_url_kwarg in self.path_kwargs, (
            'Expected view %s to be called with a URL keyword argument '
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            'attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.path_kwargs[lookup_url_kwarg]}
        obj = self.get_object_or_404(queryset, **filter_kwargs)

        # 检查操作权限
        # self.check_object_permissions(self.request, obj)

        return obj

    def get_serializer(self, *args, **kwargs):
        """
        实例化序列处理类返回
        :param args:
        :param kwargs:
        :return:
        """
        serializer_class = self.get_serializer_class()
        # kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def get_serializer_class(self):
        """
        返回定义的序列处理类，这个子类可以根据需要重构
        """
        assert self.serializer_class is not None, (
            "'%s' should either include a `serializer_class` attribute, "
            "or override the `get_serializer_class()` method."
            % self.__class__.__name__
        )

        return self.serializer_class

    def get_form(self, form_class=None):
        """
        Returns an instance of the form to be used in this view
        :param form_class:
        :return:
        """
        if form_class is None:
            form_class = self.get_form_class()

        return form_class(**self.get_form_kwargs())

    def get_form_class(self):
        """
        Returns the form class to use in this view
        :return:
        """
        return self.form_class

    def get_form_kwargs(self):
        """
        Returns the keyword arguments for instantiating the form.
        """
        kwargs = {
            'request': self.request,
            'initial': self.get_initial(),
            'data': self.request.data,
        }

        if self.request.method in ('POST', 'PUT'):
            kwargs.update({
                'files': self.request.files,
            })
        return kwargs

    def overload_paginate_settings(self):
        """
        自定义分页的参数，在`self.paginator.paginate_queryset`中调用
        :return:
        """
        pass

    @cached_property
    def paginator(self):
        """
        分页处理实例对象，如没配置返回None,反之对应的实例
        """
        if not hasattr(self, '_paginator'):
            paginator = None if self.pagination_class is None else import_object(self.pagination_class)()
            setattr(self, "_paginator", paginator)

        return self._paginator

    def paginate_queryset(self, queryset):
        """
        生成分页页对象
        """
        if self.paginator is None:
            return None

        return self.paginator.paginate_queryset(self, queryset)

    def write_response(self, data, status_code=status.HTTP_200_OK, headers=None, content_type="application/json", **kwargs):
        return Response(
            data=data,
            status_code=status_code,
            template_name=self.template_name,
            headers=headers,
            content_type=content_type
        )

    def write_paginated_response(self, data):
        """
        生成分页返回结构
        :param data: 已序列化之后的数据
        :return:
        """
        return self.paginator.get_paginated_response(data)

    @cached_property
    def error_msg_404(self):
        """
        定义抛出404的错误信息，可以是字典或字符串，桔子：{"return_code": -1, "return_msg": "资源不存在"}
        :return:
        """
        pass


class ListAPIHandler(mixins.ListModelMixin, GenericAPIHandler):
    """
    列表
    """
    async def get(self, *args, **kwargs):
        return self.list(*args, **kwargs)


class CreateAPIHandler(mixins.CreateModelMixin, GenericAPIHandler):
    """
    创建对象
    """
    async def post(self, *args, **kwargs):
        return self.create(*args, **kwargs)


class RetrieveUpdateAPIHandler(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericAPIHandler):
    """
    查看详情及修改
    """
    async def get(self, *args, **kwargs):
        return self.retrieve(*args, **kwargs)

    async def put(self, *args, **kwargs):
        return self.update(*args, **kwargs)


class DestroyAPIHandler(mixins.DestroyModelMixin, GenericAPIHandler):
    """
    删除对象
    """
    async def delete(self, *args, **kwargs):
        return self.destroy(*args, **kwargs)
