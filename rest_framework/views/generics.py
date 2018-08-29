# -*- coding: utf-8 -*-
import re
import sys
import asyncio

from rest_framework.core.response import Response
from rest_framework.core.views import RequestHandler
from rest_framework.core import exceptions
from rest_framework.core.exceptions import ErrorDetail, SkipFilterError, HTTPError
from rest_framework.lib.orm import IntegrityError
from rest_framework.log import app_logger
from rest_framework.utils import timezone
from rest_framework.utils.escape import json_encode
from rest_framework.utils.transcoder import force_text
from rest_framework.views import mixins
from rest_framework.conf import settings
from rest_framework.core.db import models
from rest_framework.utils import status
from rest_framework.utils.cached_property import cached_property
from rest_framework.utils.functional import import_object
from rest_framework.core.translation import lazy_translate as _

__all__ = [
    'GenericAPIHandler',
    'ListAPIHandler',
    'CreateAPIHandler',
    'RetrieveAPIHandler',
    'RetrieveUpdateAPIHandler',
    'DestroyAPIHandler',
    'UpdateAPIHandler'
]


def _clean_credentials(credentials):
    """
    屏蔽密码或密钥等重要信息
    :param credentials:
    :return:
    """
    if isinstance(credentials, (type(None), list)):
        return credentials

    sensitive_credentials = re.compile('api|token|key|secret|password|signature|pwd', re.I)
    cleansed_substitute = '********************'
    result = {}
    for key, value in credentials.items():
        key = force_text(key)
        if sensitive_credentials.search(key):
            result[key] = cleansed_substitute
        else:
            result[key] = value
    return result


class BaseAPIHandler(RequestHandler):
    """
    基础接口处理类
    """

    def _handle_request_exception(self, e):
        status_code = getattr(e, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        exc_info = sys.exc_info()
        if status_code >= 500:
            self._record_log(status_code, exc_info)
        error_response = self.pre_handle_exception(exc_info[1])
        return self.write_error(error_response)

    def get_log_extend(self):
        """
        用于扩展日志记录消息
        可重写，返回结构为字典
        :return:
        """
        pass

    def _record_log(self, status_code, exc_info, **kwargs):
        def _record():
            params = _clean_credentials(self.request_data)
            exc = exc_info[1]
            if hasattr(exc, "message"):
                error_info = exc.message
            elif hasattr(exc, "messages"):
                error_info = exc.messages
            elif hasattr(exc, "detail"):
                error_info = exc.detail
            else:
                error_info = ""

            log_context = {
                "url": self.request.url,
                "method": self.request.method,
                "host": self.request.headers.get("Host", ""),
                "client_ip": self.request.client_ip(),
                "request_data": params,
                "http_status_code": status_code,
                "headers": {
                    "user-agent": self.request.headers.get("User-Agent", ""),
                    "content-type": self.request.headers.get("Content-Type", "")
                },
                "time_zone": settings.TIME_ZONE,
                "time": timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                "error_info": error_info,
            }
            if kwargs:
                log_context.update(**kwargs)

            log_extend = self.get_log_extend()
            if log_extend and isinstance(log_extend, dict):
                log_context.update(**log_extend)
            log_context = json_encode(log_context)
            app_logger.error(log_context, exc_info=exc_info)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, _record)

    def write_response(self, data, status_code=status.HTTP_200_OK, headers=None,
                       content_type="application/json", **kwargs):
        if isinstance(data, Response):
            return data

        return Response(data, status_code=status_code, headers=headers, content_type=content_type)

    def write_error(self, content, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR):
        if isinstance(content, Response):
            return content

        return Response(content, status_code=status_code)

    def pre_handle_exception(self, exc):
        """
        预处理各种异常返回结构
        返回Result对象
        :param exc:
        :return:Result
        """
        if isinstance(exc, (exceptions.APIException, exceptions.ValidationError)):
            error_response = self.write_response(
                data={settings.NON_FIELD_ERRORS: {"message": exc.detail, "code": exc.code}},
                status_code=exc.status_code
            )

        elif isinstance(exc, HTTPError):
            status_code = exc.status_code
            http_code_detail = status.HTTP_CODES.get(status_code, None)
            error_response = self.write_response(
                data={settings.NON_FIELD_ERRORS: {
                    "message": http_code_detail.description
                    if http_code_detail else _("Internal Server Error"),
                    "code": "Error"
                }},
                status_code=exc.status_code
            )

        elif isinstance(exc, IntegrityError):
            error_detail = ErrorDetail(
                _('Insert failed, the reason may be foreign key constraints'),
                code="ForeignError"
            )
            error_response = self.write_response(
                data={settings.NON_FIELD_ERRORS: error_detail},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        else:
            error_response = self.write_response(
                data={settings.NON_FIELD_ERRORS: {
                    "message": _("Internal Server Error"),
                    "code": "Error"
                }},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return error_response

    def finalize_response(self, response, *args, **kwargs):
        return response


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
    # 修改或创建是否序列化实例对象返回, False代表只返回主键值，True代表返回实例对象
    need_obj_serializer = False
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
    filter_class = None
    filter_fields = ()

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

        if not isinstance(queryset, models.AsyncSelectQuery) and issubclass(queryset, models.Model):
            queryset = queryset.select()
        return queryset

    @cached_property
    def load_filter_class(self):
        """
        :return:
        """
        return [import_object(backend) for backend in self.filter_backend_list if backend is not None]

    async def filter_queryset(self, queryset):
        for backend in self.load_filter_class:
            filter_cls = backend()
            queryset = await filter_cls.filter_queryset(self, queryset)

        return queryset

    async def get_object_or_404(self, queryset, *args, **kwargs):
        """
         查询对象，如果对象不存在则抛出404
        :param queryset:
        :param args:
        :param kwargs:
        :return:
        """
        try:
            return await self.get_queryset(queryset).filter(*args, **kwargs).get()
        except AttributeError:
            queryset_name = queryset.__name__ if isinstance(queryset, type) \
                else queryset.__class__.__name__
            raise ValueError("First argument to get_object_or_404() must be a Model or SelectQuery,"
                             " not '%s'." % queryset_name)
        except queryset.model_class.DoesNotExist:
            error_msg = self.error_msg_404 if self.error_msg_404 else {}
            raise exceptions.APIException(
                status_code=404,
                detail=error_msg.get("message", _("Resource data does not exist")),
                code=error_msg.get("code", "ResourceNotExist")
            )

    async def get_object(self):
        """
        查询单一对象，如果为空抛出404
        """
        try:
            queryset = await self.filter_queryset(self.get_queryset())
        except SkipFilterError:
            error_msg = self.error_msg_404 if self.error_msg_404 else {}
            raise exceptions.APIException(
                status_code=404,
                detail=error_msg.get("message", _("Resource data does not exist")),
                code=error_msg.get("code", "ResourceNotExist")
            )

        queryset = queryset.naive()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        path_kwargs = self.path_kwargs or self.request_data
        assert lookup_url_kwarg in path_kwargs, (
            'Expected view %s to be called with a URL keyword argument '
            'named "%s". Fix your URL conf, or set the `.lookup_field` '
            'attribute on the view correctly.' %
            (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: path_kwargs[lookup_url_kwarg]}
        obj = await self.get_object_or_404(queryset, **filter_kwargs)

        return obj

    def get_serializer(self, *args, **kwargs):
        """
        实例化序列处理类返回
        :param args:
        :param kwargs:
        :return:
        """
        serializer_class = self.get_serializer_class()
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

    def get_form(self, form_class=None, **kwargs):
        """
        Returns an instance of the form to be used in this view
        :param form_class:
        :return:
        """
        if form_class is None:
            form_class = self.get_form_class()

        form_kwargs = self.get_form_kwargs()
        form_kwargs.update(kwargs)
        return form_class(**form_kwargs)

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
            'data': self.request_data,
        }

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

    async def paginate_queryset(self, queryset):
        """
        生成分页页对象
        """
        if self.paginator is None:
            return None

        return await self.paginator.paginate_queryset(self, queryset)

    async def write_paginated_response(self, data):
        """
        生成分页返回结构
        :param data: 已序列化之后的数据
        :return:
        """
        return await self.paginator.get_paginated_response(data)

    @cached_property
    def error_msg_404(self):
        """
        定义抛出404的错误信息，格式如下：
        {"code": "编码", "message": "提示消息"}
        比如{"code": -1, "message": "资源不存在"}
        :return:
        """
        pass


class ListAPIHandler(mixins.ListModelMixin, GenericAPIHandler):
    """
    列表
    """
    async def get(self, *args, **kwargs):
        return await self.list(*args, **kwargs)


class CreateAPIHandler(mixins.CreateModelMixin, GenericAPIHandler):
    """
    创建对象
    """
    async def post(self, *args, **kwargs):
        return await self.create(*args, **kwargs)


class RetrieveAPIHandler(mixins.RetrieveModelMixin, GenericAPIHandler):
    """
    查看详情
    """
    async def get(self, *args, **kwargs):
        return await self.retrieve(*args, **kwargs)


class UpdateAPIHandler(mixins.UpdateModelMixin, GenericAPIHandler):
    """
    修改
    """
    async def put(self, *args, **kwargs):
        return await self.update(*args, **kwargs)


class DestroyAPIHandler(mixins.DestroyModelMixin, GenericAPIHandler):
    """
    删除对象
    """
    async def delete(self, *args, **kwargs):
        return await self.destroy(*args, **kwargs)


class RetrieveUpdateAPIHandler(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericAPIHandler):
    """
    查看详情及修改
    """
    async def get(self, *args, **kwargs):
        return await self.retrieve(*args, **kwargs)

    async def put(self, *args, **kwargs):
        return await self.update(*args, **kwargs)



