# -*- coding: utf-8 -*-
import logging
import traceback
import asyncio

from rest_framework.core import codecs
from rest_framework.core.response import Response
from rest_framework.utils import status
from rest_framework.core.request import Request
from rest_framework.core.translation import lazy_translate as _
from rest_framework.core.exceptions import APIException, HTTPError

SUPPORTED_METHODS = ('get', 'post', 'head', 'options', 'delete', 'put', 'patch')
logger = logging.getLogger(__name__)


class HandlerMethodType(type):

    def __new__(mcs, name, bases, d):
        rv = type.__new__(mcs, name, bases, d)
        if 'methods' not in d:
            methods = set(rv.methods or [])
            for key in d:
                if key in SUPPORTED_METHODS:
                    methods.add(key.upper())
            if methods:
                rv.methods = sorted(methods)
        return rv


class BaseRequestHandler:
    methods = None

    def dispatch_request(self):
        raise NotImplementedError()

    @classmethod
    def as_view(cls, name, application, **class_kwargs):
        async def view(request: Request, *args, **kwargs):
            self = view.view_class(application, request, **class_kwargs)
            return await self.dispatch_request(*args, **kwargs)

        view.view_class = cls
        view.__name__ = name
        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.methods = cls.methods

        return view


class RequestHandler(BaseRequestHandler, metaclass=HandlerMethodType):

    def __init__(self, application, request, **kwargs):
        self.application = application
        self.request = request
        self.initialize(**kwargs)
        self.request_data = None
        self.path_args = None
        self.path_kwargs = None

    def initialize(self, **kwargs):
        pass

    def _parse_query_arguments(self):
        query_arguments = self.request.query_params
        return {k: v for k, v in query_arguments if v}

    @staticmethod
    def __select_parser(content_type):
        for parser in codecs.PARSER_MEDIA_TYPE:
            if parser.media_type in content_type:
                return parser
        return None

    async def prepare(self):
        method = self.request.method.lower()
        content_type = self.request.headers.get("Content-Type", "").lower()
        if not content_type or method == b"get":
            self.request_data = self._parse_query_arguments()
            if self.path_kwargs:
                self.request_data.update(self.path_kwargs)
            self.request.data = self.request_data
            return

        parser = self.__select_parser(content_type)
        if not parser:
            error_detail = _('Unsupported media type `%s` in request') % content_type
            raise APIException(
                detail=error_detail,
                code="MediaTypeError",
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )

        self.request_data = await parser.parse(self.request)
        self.request.data = self.request_data

    def write_error(self, content, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR):
        return Response(content, status_code=status_code)

    async def finalize_response(self, response):
        return response

    async def dispatch_request(self, *args, **kwargs):
        method = self.request.method.lower().decode("utf8")
        self.path_args = args
        self.path_kwargs = kwargs
        handler = getattr(self, method, None)
        try:
            await self.prepare()
            result = await handler(*args, **kwargs)
            response = self.finalize_response(result)
            if asyncio.iscoroutine(response):
                response = await response
            return response

        except Exception as e:
            try:
                return self._handle_request_exception(e)
            except:
                logger.error("Exception in exception handler", exc_info=True)
                error_content = {
                    "message": _("Internal Server Error"),
                    "code": "Error"
                }
                return self.write_error(error_content, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_request_exception(self, e):
        logger.error("request exception", exc_info=True)
        if isinstance(e, HTTPError):
            status_code = e.status_code
            http_code_detail = status.HTTP_CODES.get(status_code, None)
            error_content = {
                "message": http_code_detail.description
                if http_code_detail else _("Internal Server Error"),
                "code": "Error"
            }
            return self.write_error(error_content, status_code)
        else:
            error_content = {
                "message": traceback.format_exc(),
                "code": "Error"
            }
            return self.write_error(error_content, 500)


class ErrorHandler(RequestHandler):
    def initialize(self, status_code):
        self._status_code = status_code

    def prepare(self):
        raise HTTPError(self._status_code)
