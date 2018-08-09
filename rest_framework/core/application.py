import logging
import traceback
from functools import partial
from multiprocessing import cpu_count
from typing import Callable, Type, Optional
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


class Application(Blueprint):

    def __init__(self, router_strategy=RouterStrategy.CLONE, server_name: str = None,
                 url_scheme: str = 'http', log_handler: Callable=None, access_logs: bool=None,
                 server_limits: ServerLimits=None, route_limits: RouteLimits=None,
                 request_class: Type[Request]=Request):
        """

        :param router_strategy:
        :param server_name:
        :param url_scheme:
        :param log_handler:
        :param server_limits:
        :param route_limits:
        """
        super().__init__(limits=route_limits)
        self.debug_mode = False
        self.server_name = server_name
        self.url_scheme = url_scheme
        self.handler = Connection
        self.router = Router(strategy=router_strategy)
        self.connections = set()
        self.workers = []
        self.components = ComponentsEngine()
        self.loop = None
        self.access_logs = access_logs
        self.log_handler = log_handler
        self.initialized = False
        self.server_limits = server_limits or ServerLimits()
        self.running = False
        if not issubclass(request_class, Request):
            raise ValueError(
                'class_obj must be a child of the Vibora Request class. '
                '(from binhua.request import Request)'
            )
        self.request_class = request_class

    def exists_hook(self, type_id: int) -> bool:
        """

        :param type_id:
        :return:
        """

        for blueprint in self.blueprints.keys():
            if bool(blueprint.hooks.get(type_id)):
                return True
            if bool(blueprint.async_hooks.get(type_id)):
                return True
        return bool(self.hooks.get(type_id) or self.async_hooks.get(type_id))

    async def call_hooks(self, type_id: int, components, route=None) -> Optional[Response]:
        """

        :param route:
        :param type_id:
        :param components:
        :return:
        """
        targets = (route.parent, self) if route and route.parent != self else (self, )
        for target in targets:
            for listener in target.hooks.get(type_id, ()):
                response = listener.call_handler(components)
                if response:
                    return response
            for listener in target.async_hooks.get(type_id, ()):
                response = await listener.call_handler(components)
                if response:
                    return response

    def __register_blueprint_routes(self, blueprint: Blueprint, prefixes: dict = None):
        """

        :param blueprint:
        :param prefixes:
        :return:
        """
        for name, pattern in prefixes.items():
            for nested_blueprint, nested_prefixes in blueprint.blueprints.items():
                for nested_name, nested_pattern in nested_prefixes.items():
                    if name and nested_name:
                        merged_prefixes = {name + ':' + nested_name: pattern + nested_pattern}
                    else:
                        merged_prefixes = {name or nested_name: pattern + nested_pattern}
                    self.__register_blueprint_routes(nested_blueprint, prefixes=merged_prefixes)
        blueprint.app = self
        for route in blueprint.routes:
            route.app = self.app
            route.limits = route.limits or self.limits
            self.router.add_route(route, prefixes=prefixes)

    def add_blueprint(self, blueprint, prefixes: dict = None):
        """

        :param blueprint:
        :param prefixes:
        :return:
        """
        if blueprint.parent:
            raise DuplicatedBlueprint(
                'You cannot add blueprint twice. Use more prefixes or a different hierarchy.'
            )

        if blueprint != self:
            blueprint.parent = self

        if prefixes is None:
            prefixes = {'': ''}

        self.__register_blueprint_routes(blueprint, prefixes)

        self.blueprints[blueprint] = prefixes

        # Non-Local listeners are removed from the blueprint because they are actually global hooks.
        if blueprint != self:
            for collection, name in ((blueprint.hooks, 'hooks'), (blueprint.async_hooks, 'async_hooks')):
                local_listeners = {}
                for listener_type, listeners in collection.items():
                    for listener in listeners:
                        if not listener.local:
                            self.add_hook(listener)
                        else:
                            local_listeners.setdefault(listener.event_type, []).append(listener)
                setattr(blueprint, name, local_listeners)

    def clean_up(self):
        """

        :return:
        """
        for process in self.workers:
            process.terminate()
        self.running = False

    def url_for(self, _name: str, _external=False, *args, **kwargs) -> str:
        """

        :param _name:
        :param _external:
        :param args:
        :param kwargs:
        :return:
        """
        if not self.initialized:
            raise ValueError('Routes are not registered yet. Please run Vibora or call app.initialize().')
        route = self.router.reverse_index.get(_name)
        if not route:
            raise ReverseNotFound(_name)
        root = ''
        if _external:
            if not self.server_name or not self.url_scheme:
                raise Exception('Please configure the server_name and url_scheme to use external urls.')
            root = self.url_scheme + '://' + self.server_name
        return root + route.build_url(*args, **kwargs).decode()

    def __del__(self):
        self.clean_up()

    def _add_default_routes(self):
        """

        :return:
        """
        async def not_found_handler():
            raise NotFound()

        route_404 = Route(b'', not_found_handler, parent=self, limits=self.limits)
        self.router.default_handlers[404] = route_404

        async def method_not_allowed_handler(request: Request):
            raise MethodNotAllowed(request.context['allowed_methods'])

        route_405 = Route(b'', method_not_allowed_handler, parent=self, limits=self.limits)
        self.router.default_handlers[405] = route_405

        async def server_exception_handler(request: Request):
            raise request.context["exc"]

        route_500 = Route(b'', server_exception_handler, parent=self, limits=self.limits)
        self.router.default_handlers[500] = route_500

    def _add_default_error_handlers(self):

        @self.handle(MissingComponent)
        async def handle_missing_component(app: Application, error: MissingComponent):
            try:
                msg = f"{error.route.handler if error.route else 'A hook'} needs " \
                      f"{error.component} but there isn't any " \
                      f"component registered with this type."
                raise MissingComponent(msg)
            except Exception as e:
                if app.debug_mode:
                    traceback.print_exception(MissingComponent, e, e.__traceback__)
                else:
                    logger.error(
                        "Internal Server Error", exc_info=(MissingComponent, error, error.__traceback__)
                    )

            return Response(
                b'Internal Server Error', status_code=500,  headers={'Content-Type': 'text/html'}
            )

        @self.handle(BodyLimitError)
        async def handle_body_limit():
            return Response(b'HTTP request body is too big.', status_code=413)

        @self.handle(HeadersLimitError)
        async def handle_headers_limit():
            return Response(b'HTTP request headers are too big. '
                            b'Maybe there are too many, maybe just few big ones.', status_code=400)

        @self.handle(Exception)
        async def handle_internal_error(app: Application, error: Exception):
            if app.debug_mode:
                traceback.print_exception(MissingComponent, error, error.__traceback__)
            else:
                logger.error(
                    "Internal Server Error", exc_info=(MissingComponent, error, error.__traceback__)
                )
            return Response(b"Internal Server Error", status_code=500, headers={'Content-Type': 'text/html'})

        @self.handle(NotFound)
        async def internal_server_error():
            return Response(b'404 Not Found', status_code=404)

        @self.handle(MethodNotAllowed)
        async def internal_server_error(request: Request):
            return Response(b'Method Not Allowed', status_code=405,
                            headers={'Allow': request.context['allowed_methods']})

    def check_integrity(self):
        self.router.check_integrity()

    def initialize(self):
        self.components.add(self)
        self.add_blueprint(self, prefixes={'': ''})
        self._add_default_routes()
        self._add_default_error_handlers()
        self.check_integrity()
        self.initialized = True

    def run(self, host: str='127.0.0.1', port: int=5000, workers: int=None, debug: bool=True,
            block: bool=True, necromancer: bool=False, sock=None, startup_message: bool=True):
        """

        :param startup_message:
        :param host:
        :param port:
        :param workers:
        :param debug:
        :param block:
        :param necromancer:
        :param sock:
        :return:
        """
        self.debug_mode = debug

        # Starting workers.
        spawn_function = partial(RequestHandler, self, host, port, sock)
        for _ in range(0, (workers or cpu_count() + 2)):
            worker = spawn_function()
            worker.start()
            self.workers.append(worker)

        # Watch out for dead workers and bring new ones to life as needed.
        if necromancer:
            necromancer = Necromancer(self.workers, spawn_function=spawn_function,
                                      interval=self.server_limits.worker_timeout)
            necromancer.start()

        # Wait the server start accepting new connections.
        if not sock:
            wait_server_available(host, port)

        if startup_message:
            print('http://%s:%s' % (host, port))

        self.running = True
        if block:
            try:
                pause()
                self.running = False
            except KeyboardInterrupt:
                self.clean_up()
