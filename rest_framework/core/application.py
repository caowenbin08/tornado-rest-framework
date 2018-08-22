import logging
import traceback
from functools import partial
from multiprocessing import cpu_count
from typing import Callable, Type, Optional

import uvicorn

from rest_framework.conf import settings
from rest_framework.core import urls
from rest_framework.core.request import Request
from rest_framework.core.responses import Response
from rest_framework.core.blueprints import Blueprint
from rest_framework.core.router import Route
from rest_framework.core.router import Router, RouterStrategy, RouteLimits
from rest_framework.core.protocol import Connection
from rest_framework.core.components import ComponentsEngine
from rest_framework.core.exceptions import ReverseNotFound, DuplicatedBlueprint
from rest_framework.core.exceptions import NotFound, MethodNotAllowed, MissingComponent
from rest_framework.core.parsers.errors import BodyLimitError, HeadersLimitError
from rest_framework.core.workers.handler import RequestHandler
from rest_framework.core.workers.necromancer import Necromancer
from rest_framework.core.limits import ServerLimits
from rest_framework.utils.server import wait_server_available, pause

logger = logging.getLogger(__name__)


class Application:

    def __init__(self, router_strategy=RouterStrategy.CLONE, server_name: str = None,
                 url_scheme: str = 'http', log_handler: Callable=None, access_logs: bool=None,
                 server_limits: ServerLimits=None, route_limits: RouteLimits=None,
                 request_class: Type[Request]=Request):
        self.debug_mode = False
        # self.server_name = server_name
        # self.url_scheme = url_scheme
        self.handler = Connection
        self.router = Router(strategy=router_strategy)
        # self.connections = set()
        # self.workers = []
        # self.components = ComponentsEngine()
        # self.loop = None
        # self.access_logs = access_logs
        # self.log_handler = log_handler
        # self.initialized = False
        # self.server_limits = server_limits or ServerLimits()
        # self.running = False
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
    pass


def get_application(interface=b"asgi"):
    if interface == b"asgi":
        return ASyncApplication()

    else:
        return Application()

