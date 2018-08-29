import logging
from typing import Type
import uvicorn

from rest_framework.conf import settings
from rest_framework.core import urls
from rest_framework.core.request import Request
from rest_framework.core.router import Router, Route
from rest_framework.core.translation import babel
from rest_framework.core.views import ErrorHandler
from rest_framework.log import configure_logging

logger = logging.getLogger(__name__)


class Application:

    def __init__(self, request_class: Type[Request]=Request):
        self.router = Router()
        self.request_class = request_class
        self.initialize()

    def _add_error_routes(self):
        route_name = ErrorHandler.__name__
        for status_code in (404, 405, 500):
            kw = {"status_code": status_code}
            view_func = ErrorHandler.as_view(name=route_name, application=self, **kw)
            route = Route(b"", view_func, parent=self, name=route_name)
            self.router.default_handlers[status_code] = route

    def _load_route(self):
        urlpatterns = urls.url_patterns(settings.ROOT_URLCONF)
        for url in urlpatterns:
            pattern = url.pattern.strip("^").strip("$")
            self.register_route(pattern, handler=url.handler, name=url.name, **url.kwargs)

    def initialize(self):
        configure_logging(settings.LOGGING)
        self._load_route()
        self._add_error_routes()
        babel.load_translations()
        self.router.check_integrity()

    def register_route(self, pattern, handler, name=None, **kwargs):
        route_name = handler.__name__ if name is None else name
        view_func = handler.as_view(name=route_name, application=self, **kwargs)
        methods = getattr(view_func, 'methods', None) or ('GET',)
        methods = set(item.upper() for item in methods)

        if isinstance(pattern, str):
            encoded_pattern = pattern.encode()
        else:
            encoded_pattern = pattern

        route = Route(encoded_pattern, view_func, methods, parent=self, name=route_name)
        self.router.add_route(route)
        return handler

    def run(self, host: str='127.0.0.1', port: int=5000):
        uvicorn.run(self, host=host, port=port)


class ASyncApplication(Application):
    def __call__(self, scope):
        async def asgi_callable(receive, send):
            request = self.request_class(scope, receive)
            route = self.router.get_route(request)
            response = await route.call_handler(request)
            await response(receive, send)

        return asgi_callable


def get_application(interface=b"asgi"):
    if interface == b"asgi":
        return ASyncApplication()

    else:
        return Application()

