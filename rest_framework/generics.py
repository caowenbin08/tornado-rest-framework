# -*- coding: utf-8 -*-
import traceback

import peewee
from tornado import gen
from tornado import iostream
from tornado.escape import json_decode
from tornado.log import app_log
from tornado.web import RequestHandler, HTTPError

from rest_framework import mixins
from rest_framework.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.helpers import status
from rest_framework.helpers.functional import load_object
from rest_framework.response import Response


__author__ = 'caowenbin'


def _has_stream_request_body(cls):
    if not issubclass(cls, RequestHandler):
        raise TypeError("expected subclass of RequestHandler, got %r", cls)
    return getattr(cls, '_stream_request_body', False)


class BaseAPIHandler(RequestHandler):
    """
    基础接口处理类
    """
    # 不需要检查xsrf的请求方法
    NOT_CHECK_XSRF_METHOD = ("GET", "HEAD", "OPTIONS")

    def __init__(self, application, request, **kwargs):
        self.json_data = dict()
        super(BaseAPIHandler, self).__init__(application, request, **kwargs)

    def data_received(self, chunk):
        pass

    def prepare(self):

        self._load_data_and_files()
        print("-------prepareprepareprepare-----", self.json_data)
        return super(BaseAPIHandler, self).prepare()

    def _load_data_and_files(self):
        """
        解析请求参数
        :return:
        """
        content_type = self.request.headers.get("Content-Type", "")
        if content_type == "application/json":
            self.json_data = json_decode(self.request.body) if self.request.body else {}
        elif content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
            self.json_data = self.request.body_arguments

    @gen.coroutine
    def _execute(self, transforms, *args, **kwargs):
        """

        :param transforms:
        :param args:
        :param kwargs:
        :return:
        """

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
            result = handler(*self.path_args, **self.path_kwargs)
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

            if self._prepared_future is not None and not self._prepared_future.done():
                self._prepared_future.set_result(None)

    def write_error(self, status_code, **kwargs):
        """
        输出异常信息
        :param status_code: http状态码
        :param kwargs:
        :return:
        """
        if self.settings.get("serve_traceback") and "exc_info" in kwargs:
            exception = kwargs['exc_info'][1]
            response_detail = getattr(exception, "response_detail", None)
            if isinstance(response_detail, Response):
                self.set_header('Content-Type', response_detail.content_type)
                self.write(response_detail.data)
            else:
                self.set_header('Content-Type', 'text/plain')
                for line in traceback.format_exception(*kwargs["exc_info"]):
                    self.write(line)
            self.finish()
        else:
            self.finish("<html><title>%(code)d: %(message)s</title>"
                        "<body>%(code)d: %(message)s</body></html>" % {
                            "code": status_code,
                            "message": self._reason,
                        })

    def finalize_response(self, response, *args, **kwargs):
        if not isinstance(response, Response):
            raise TypeError("Request return value types must be the Response")

        self.set_status(response.status_code)
        self.set_header('Content-Type', response.content_type)
        return self.write(response.data)


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
    # 查询过滤处理类，主要是搜索、过滤
    filter_backend_list = []
    # 分页处理类
    pagination_class = "rest_framework.pagination.PageNumberPagination"
    # 页面模板名
    template_name = ""
    # 修改或创建是否序列化实例对象返回, False代表只返回主键值，True代表返回实例对象
    need_obj_serializer = False
    # 检查参数不正确是否抛出异常， False代表为抛出 True代表直接抛出ValidationError
    form_valid_raise_except = False
    # 定义抛出404的错误信息，可以是字典或字符串，桔子：{"return_code": "资源不存在", "return_msg": "资源不存在"}
    error_msg_404 = None

    def get_queryset(self, queryset=None):
        """
        生成查询操作对象，即SelectQuery
        :param queryset:
        :return:
        """
        queryset = queryset if queryset is not None else self.queryset
        assert queryset is not None, (
            "'%s' should either include a `queryset` attribute, "
            "or override the `get_queryset()` method."
            % self.__class__.__name__
        )

        if not isinstance(queryset, peewee.SelectQuery) and issubclass(queryset, peewee.Model):
            queryset = queryset.select()
        return queryset

    def filter_queryset(self, queryset):
        """
        Given a queryset, filter it with whichever filter backend is in use.

        You are unlikely to want to override this method, although you may need
        to call it either from a list view, or from a custom `get_object`
        method if you want to apply the configured filtering backend to the
        default queryset.
        """
        for backend in list(self.filter_backend_list):
            queryset = backend().filter_queryset(self.request, queryset, self)
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
            raise APIException(
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

    def get_form(self, *args, **kwargs):
        """
        实例化表单处理类返回
        :param args:
        :param kwargs:
        :return:
        """
        form_class = self.get_form_class()
        # kwargs['context'] = self.get_serializer_context()
        return form_class(*args, **kwargs)

    def get_form_class(self):
        """
        返回定义的表单处理类，这个子类可以根据需要重构
        """
        assert self.form_class is not None, (
            "'%s' should either include a `form_class` attribute, "
            "or override the `get_form_class()` method."
            % self.__class__.__name__
        )

        return self.form_class

    @property
    def paginator(self):
        """
        分页处理实例对象，如没配置返回None,反之对应的实例
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = load_object(self.pagination_class)()

        return self._paginator

    def paginate_queryset(self, queryset):
        """
        生成分页页对象
        """
        if self.paginator is None:
            return None

        return self.paginator.paginate_queryset(queryset=queryset, request=self.request)

    def write_response(self, data, status_code=status.HTTP_200_OK, headers=None, content_type="application/json"):
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
        assert self.paginator is not None
        return self.paginator.get_paginated_response(data)


class ListAPIHandler(mixins.ListModelMixin, GenericAPIHandler):
    """
    列表
    """
    def get(self, *args, **kwargs):
        return self.list(*args, **kwargs)


class CreateAPIHandler(mixins.CreateModelMixin, GenericAPIHandler):
    """
    创建对象
    """
    def post(self, *args, **kwargs):
        return self.create(*args, **kwargs)


class RetrieveUpdateAPIHandler(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericAPIHandler):
    """
    查看详情及修改
    """
    def get(self, *args, **kwargs):
        return self.retrieve(*args, **kwargs)

    def put(self, *args, **kwargs):
        return self.update(*args, **kwargs)


class DestroyAPIHandler(mixins.DestroyModelMixin, GenericAPIHandler):
    """
    删除对象
    """
    def delete(self, *args, **kwargs):
        return self.destroy(*args, **kwargs)
