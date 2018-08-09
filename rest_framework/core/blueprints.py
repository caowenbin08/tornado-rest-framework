from inspect import isclass
from rest_framework.core.exceptions import ExceptionHandler, DuplicatedBlueprint, ConflictingPrefixes
from rest_framework.core.router import Route
from rest_framework.core.hooks import Hook, Events
from rest_framework.core.responses import Response
from rest_framework.core.limits import RouteLimits


class Blueprint:
    def __init__(self, limits: RouteLimits=None):
        self.default_routes = {}
        self.routes = []
        self.hooks = {}
        self.async_hooks = {}
        self.exception_handlers = {}
        self.blueprints = {}
        self.limits = limits or RouteLimits()

        # Initializing cached events.
        for key in Events.ALL:
            self.hooks[key] = []
            self.async_hooks[key] = []

        # Runtime Hacks.
        self.app = None
        self.parent = None

    def handle(self, value, local: bool = True):
        """
        Decorator to register a hook.
        :return: None
        """
        if value in (Events.BEFORE_SERVER_START, Events.AFTER_SERVER_START, Events.BEFORE_SERVER_STOP):
            local = False

        def wrapper(*args):
            handler = args[0]
            values = value if isinstance(value, (list, tuple)) else [value]
            for v in values:
                if v in Events.ALL:
                    self.add_hook(Hook(v, args[0], local=local))
                elif isinstance(v, Exception) or (isclass(v) and issubclass(v, Exception)):
                    self.exception_handlers[v] = ExceptionHandler(handler, v, local=local)
                else:
                    raise SyntaxError('{0} is not allowed at @handle.'.format(v))
        return wrapper

    def register_view(self, pattern, handler, name=None, cache=None,
                      limits: RouteLimits=None, **kwargs):
        route_name = handler.__name__ if name is None else name
        view_func = handler.as_view(name=route_name, application=self, **kwargs)
        methods = getattr(view_func, 'methods', None) or ('GET',)
        methods = set(item.upper() for item in methods)

        if isinstance(pattern, str):
            encoded_pattern = pattern.encode()
        else:
            encoded_pattern = pattern
        chosen_cache = cache
        if cache is False:
            chosen_cache = None
        new_route = Route(encoded_pattern, view_func, methods, parent=self, name=route_name,
                          cache=chosen_cache, limits=limits or self.limits)
        self.add_route(new_route)
        return handler

    def route(self, pattern, methods=None, cache=None, name=None, hosts: list=None, limits: RouteLimits=None):
        def register(handler):
            chosen_cache = cache
            if cache is False:
                chosen_cache = None
            route_name = handler.__name__ if name is None else name

            # Patterns should be bytes.
            if isinstance(pattern, str):
                encoded_pattern = pattern.encode()
            else:
                encoded_pattern = pattern

            new_route = Route(encoded_pattern, handler, tuple(methods or (b'GET',)),
                              parent=self, name=route_name, cache=chosen_cache,
                              limits=limits or self.limits)
            self.add_route(new_route)
            return handler

        return register

    async def process_exception(self, exception, components) -> Response:
        """

        :param components:
        :param exception:
        :return:
        """
        # Trying specific hooks first.
        exception_handler = self.exception_handlers.get(exception.__class__)
        if exception_handler:
            response = await exception_handler.call(components)
            if response:
                return response

        # Then we can start calling the more generic ones.
        for exception_type, exception_handler in self.exception_handlers.items():
            if exception_type == exception.__class__:
                continue

            if isinstance(exception, exception_type) and exception != exception_type:
                response = await exception_handler.call(components)
                if response:
                    return response

        if self.parent:
            return await self.parent.process_exception(exception, components)

    def add_blueprint(self, blueprint, prefixes: dict=None):
        """
        Add a nested blueprint.
        :param blueprint: Blueprint instance.
        :param prefixes: prefixes to prepend on route patterns. (I.e: {"/v1/": "v1"})
        :return: None
        """
        if not prefixes:
            prefixes = {'': ''}

        if blueprint.parent:
            raise DuplicatedBlueprint(
                'You cannot add a blueprint twice. Use more prefixes or different hierarchy.')

        for key in prefixes.keys():
            for existent_prefix in self.blueprints.values():
                if key == existent_prefix:
                    raise ConflictingPrefixes(f'Prefix "{key}" conflicts with an already '
                                              f'existing prefix: {existent_prefix}')

        blueprint.parent = self
        self.blueprints[blueprint] = prefixes

    def add_hook(self, hook: Hook):
        """

        :param hook:
        :return:
        """
        collection = self.async_hooks if hook.is_async else self.hooks
        collection[hook.event_type].append(hook)

    def add_route(self, route: Route):
        """

        :param route:
        :return:
        """
        self.routes.append(route)

    def url_for(self, _name: str, _external=False, *args, **kwargs) -> str:
        """

        :param _external:
        :param _name:
        :param args:
        :param kwargs:
        :return:
        """
        return self.app.url_for(_name, _external=_external, *args, **kwargs)
