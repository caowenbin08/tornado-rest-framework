import uuid
import hashlib
from collections import deque
from typing import get_type_hints
from inspect import iscoroutinefunction, signature
from .parser import PatternParser
from rest_framework.core.limits import RouteLimits
from rest_framework.utils.router import clean_route_name, clean_methods
from rest_framework.core.exceptions import ReverseNotFound, NotFound, MissingComponent, \
    MethodNotAllowed
from rest_framework.core.request.request import Request
from rest_framework.core.cache.cache import CacheEngine
from rest_framework.core.responses.responses import RedirectResponse


class RouterStrategy:
    STRICT = 1
    REDIRECT = 2
    CLONE = 3


class LRUCache:

    def __init__(self, max_size: int=256):
        self.values = {}
        self.queue = deque()
        self.max_size = max_size
        self.current_size = 0

    def set(self, key: str, route: 'Route'):
        if self.current_size > self.max_size:
            key = self.queue.pop()
            del self.values[key]
        self.queue.appendleft(key)
        self.values[key] = route
        self.current_size += 1


class Router:
    def __init__(self, strategy: int):
        self.strategy = strategy
        self.reverse_index = {}
        self.routes = {}
        self.dynamic_routes = []
        self.default_handlers = {}
        self.cache = LRUCache(max_size=1024 * 1024)

    def _add_route_to_cache(self, route: 'Route'):
        """

        :param route:
        :return:
        """
        if route.is_dynamic:
            self.dynamic_routes.append(route)
        else:
            m = hashlib.md5()
            m.update(route.pattern)
            cache_key = m.hexdigest()
            self.routes[cache_key] = route

        self.reverse_index[route.name] = route

    def add_route(self, route: 'Route', prefixes: dict = None, check_slashes: bool = True):
        if prefixes is None:
            prefixes = {'': ''}

        for name_prefix, pattern_prefix in prefixes.items():
            clone = route.clone(pattern=pattern_prefix.encode() + route.pattern,
                                name=clean_route_name(name_prefix, route.name))
            self._add_route_to_cache(clone)

            # Handling slashes strategy.
            conditions = [
                not clone.is_dynamic,
                check_slashes is True,
                b'GET' in clone.methods
            ]

            if all(conditions):
                if self.strategy == RouterStrategy.CLONE:
                    pattern = clone.pattern[:-1] if clone.pattern.endswith(b'/') \
                        else clone.pattern + b'/'
                    self.add_route(clone.clone(pattern), check_slashes=False, prefixes={'': ''})

                elif self.strategy == RouterStrategy.REDIRECT:
                    async def redirect_handler():
                        return RedirectResponse(clone.pattern.decode(), status_code=301)
                    redirect_route = clone.clone(
                        handler=redirect_handler, methods=('GET', ),
                        dynamic=False,
                        pattern=clone.pattern[:-1] if clone.pattern.endswith(b'/')
                        else clone.pattern + b'/'
                    )
                    self.add_route(redirect_route, check_slashes=False, prefixes={'': ''})

    def build_url(self, _name: str, *args, **kwargs):
        try:
            route = self.reverse_index[_name]
            return route.build_url(*args, **kwargs)
        except KeyError:
            raise ReverseNotFound('Failed to build url for {0}'.format(_name))

    @staticmethod
    def check_allowed_method(route: 'Route', method: bytes):
        methods = route.methods
        if method not in methods:
            raise MethodNotAllowed()

    def _find_route(self, url: bytes, method: bytes) -> 'Route':
        m = hashlib.md5()
        m.update(url)
        cache_key = m.hexdigest()
        route = self.cache.values.get(cache_key)
        if route:
            self.check_allowed_method(route, method)
            return route

        try:
            route = self.routes[cache_key]
            self.cache.set(cache_key, route)
            self.check_allowed_method(route, method)
            return route
        except KeyError:
            pass

        for route in self.dynamic_routes:
            if route.regex.fullmatch(url):
                self.cache.set(cache_key, route)
                self.check_allowed_method(route, method)
                return route

        raise NotFound()

    def get_route(self, request: Request) -> 'Route':
        try:
            route = self._find_route(request.parsed_url.path, request.method)
            return route
        except NotFound:
            return self.default_handlers[404]
        except MethodNotAllowed:
            return self.default_handlers[405]
        except Exception as e:
            request.context['exc'] = e
            return self.default_handlers[500]

    def check_integrity(self):
        for http_code in [404, 405, 500]:
            if self.default_handlers.get(http_code) is None:
                raise NotImplementedError(f'Please implement the default {http_code} route.')


class Route:

    def __init__(self, pattern: bytes, handler, methods=None, parent=None, app=None,  dynamic=None,
                 name: str = None, cache: CacheEngine = None, limits: RouteLimits=None):
        self.name = name or str(uuid.uuid4())
        self.handler = handler
        self.app = app
        self.parent = parent
        self.pattern = pattern
        self.components = self.extract_components(self.handler)
        self.receive_params = len(self.components)
        self.is_coroutine = iscoroutinefunction(handler)
        self.methods = clean_methods(methods)
        self.regex, self.params_book, self.simplified_pattern = PatternParser.extract_params(pattern)
        self.has_parameters = bool(self.params_book)
        if dynamic is None:
            self.is_dynamic = PatternParser.is_dynamic_pattern(self.regex.pattern)
        else:
            self.is_dynamic = dynamic
        # self.cache = cache
        # self.limits = limits

    def extract_components(self):
        hints = get_type_hints(self.handler)
        if not hints and len(signature(self.handler).parameters) > 0:
            raise Exception(f'Type hint your route ({self.name}) params so Vibora can optimize stuff.')
        return tuple(filter(lambda x: x[0] != 'return', hints.items()))

    def call_handler(self, request: Request, components):
        if not self.receive_params:
            return self.handler()
        else:
            if self.has_parameters:
                match = self.regex.match(request.url)
            function_params = {}
            try:
                for name, type_ in self.components:
                    if name in self.params_book:
                        function_params[name] = PatternParser.CAST[type_](match.group(name))
                    else:
                        function_params[name] = components.get(type_)
            except MissingComponent as error:
                error.route = self
                raise error
            if hasattr(self.handler, "view_class"):
                for name in self.params_book:
                    function_params[name] = match.group(name)

            return self.handler(**function_params)

    def build_url(self, **kwargs):
        if not self.is_dynamic:
            return self.pattern
        else:
            url = self.simplified_pattern
            for key, value in kwargs.items():
                url = url.replace('$' + key, str(value))
            return url

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return all([
                other.pattern == self.pattern,
                other.handler == self.handler,
                other.methods == self.methods
            ])
        return False

    def __str__(self):
        return '<Route ("{0}", methods={1})>'.format(self.pattern, self.methods)

    def clone(self, pattern=None, name=None, handler=None, methods=None, dynamic=None):
        return Route(pattern=pattern or self.pattern, handler=handler or self.handler,
                     methods=methods or self.methods, parent=self.parent, app=self.app,
                     dynamic=dynamic or self.is_dynamic,
                     name=name or self.name)
