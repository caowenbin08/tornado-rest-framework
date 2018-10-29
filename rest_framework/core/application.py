import logging
import uvicorn

from rest_framework.conf import settings
from rest_framework.core import urls
from rest_framework.core.exceptions import NotFound
from rest_framework.core.request import Request
from rest_framework.core.websockets import WebSocket
from rest_framework.core.router import Router, Route
from rest_framework.core.translation import babel
from rest_framework.core.views import ErrorHandler
from rest_framework.log import configure_logging
from rest_framework.core.types import ASGIApp, ASGIInstance, Receive, Scope, Send

logger = logging.getLogger(__name__)


class Application:

    def __init__(self):
        self.router = Router()
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

    def process_http(self, scope: Scope) -> ASGIInstance:
        async def process_callable(receive: Receive, send: Send) -> None:
            request = Request(scope, receive=receive)
            route = self.router.get_route(request)
            response = await route.call_handler(request)
            await response(receive, send)

        return process_callable

    def process_websocket(self, scope: Scope) -> ASGIInstance:
        async def process_callable(receive: Receive, send: Send) -> None:
            session = WebSocket(scope, receive=receive, send=send)
            try:
                route = self.router.get_route(session)
            except NotFound:
                await send({"type": "websocket.close", "code": 1000})
            except Exception:
                logger.error("websocket request process error", exc_info=True)
                await send({"type": "websocket.close", "code": 1000})
            else:
                await route.call_handler(session)

        return process_callable


class ProtocolRouter:
    def __init__(self, protocols):
        self.protocols = protocols

    def __call__(self, scope):
        app = self.protocols[scope["type"]]
        return app(scope)

    def run(self, host: str='127.0.0.1', port: int=5000):
        uvicorn.run(self, host=host, port=port)


def get_application():
    app = Application()
    protocol_router = ProtocolRouter({"http": app.process_http, "websocket": app.process_websocket})

    return protocol_router


