import logging
from typing import Type
import uvicorn

from rest_framework.conf import settings
from rest_framework.core import urls
from rest_framework.core.request import Request
from rest_framework.core.router import Route
from rest_framework.core.router.router import Router, RouterStrategy
from rest_framework.log import configure_logging

logger = logging.getLogger(__name__)


class Application:

    def __init__(self, router_strategy=RouterStrategy.CLONE, request_class: Type[Request]=Request):
        self.router = Router(strategy=router_strategy)
        if not issubclass(request_class, Request):
            raise ValueError(
                'class_obj must be a child of the Vibora Request class. '
                '(from binhua.request import Request)'
            )
        self.request_class = request_class
        self.initialize()

    def _load_route(self):
        urlpatterns = urls.url_patterns(settings.ROOT_URLCONF)
        for pattern, handler, handler_kwargs, name in urlpatterns:
            pattern = pattern.strip("^").strip("$")
            self.register_route(pattern, handler=handler, name=name, **handler_kwargs)

    def initialize(self):
        configure_logging(settings.LOGGING)
        self._load_route()

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

