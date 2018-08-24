import re
import hashlib
from collections import deque
from typing import Tuple, Iterable, Union
from inspect import iscoroutinefunction

from rest_framework.core.request import Request
from rest_framework.core.exceptions import RouteConfigurationError
from rest_framework.core.exceptions import ReverseNotFound, NotFound, MethodNotAllowed


class PatternParser:
    PARAM_REGEX = re.compile(b"(\(\?P<.*?>.*?\)|<.*?>)")
    DYNAMIC_CHARS = bytearray(b'*?.[]()<>')

    CAST = {
        str: lambda x: x.decode('utf-8'),
        int: lambda x: int(x),
        float: lambda x: float(x)
    }

    @classmethod
    def validate_param_name(cls, name: bytes):
        # TODO:
        if b':' in name:
            raise RouteConfigurationError(
                'Special characters are not allowed in param name. '
                'Use type hints in function parameters to cast the variable '
                'or regexes with named groups to ensure only a specific URL matches.'
            )

    @classmethod
    def extract_params(cls, pattern: bytes) -> tuple:
        """

        :param pattern:
        :return:
        """
        params = []
        new_pattern = pattern
        simplified_pattern = pattern
        groups = cls.PARAM_REGEX.findall(pattern)
        for group in groups:
            if group.startswith(b"(?P"):
                name = group[group.find(b"<") + 1: group.find(b">")]
                simplified_pattern = new_pattern
            else:
                name = group[1:-1]  # Removing <> chars
                simplified_pattern = simplified_pattern.replace(group, b'$' + name)
                new_pattern = new_pattern.replace(group, b'(?P<' + name + b'>[^/]+)')

            cls.validate_param_name(name)
            params.append(name.decode())
        return re.compile(new_pattern), params, simplified_pattern

    @classmethod
    def is_dynamic_pattern(cls, pattern: bytes) -> bool:
        for index, char in enumerate(pattern):
            if char in cls.DYNAMIC_CHARS:
                if index > 0 and pattern[index - 1] == '\\':
                    continue
                return True
        return False


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
    def __init__(self):
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

    def add_route(self, route: 'Route', check_slashes: bool = True):
        self._add_route_to_cache(route)
        conditions = [not route.is_dynamic, check_slashes is True]

        if all(conditions):
            pattern = route.pattern[:-1] if route.pattern.endswith(b'/') \
                else route.pattern + b'/'
            self.add_route(route.clone(pattern), check_slashes=False)

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
            route = self._find_route(request.url.path, request.method)
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


def clean_methods(methods: Iterable[Union[str, bytes]]) -> Tuple[bytes]:
    if methods:
        parsed_methods = set()
        for method in methods:
            if isinstance(method, str):
                parsed_methods.add(method.upper().encode())
            elif isinstance(method, bytes):
                parsed_methods.add(method.upper())
            else:
                raise Exception('Methods should be str or bytes.')
        return tuple(parsed_methods)
    return b'GET',


class Route:

    def __init__(self, pattern: bytes, handler, methods=None, parent=None, app=None,  dynamic=None,
                 name: str = None):
        self.name = name if name else handler.__name__
        self.handler = handler
        self.app = app
        self.parent = parent
        self.pattern = pattern
        self.is_coroutine = iscoroutinefunction(handler)
        self.methods = clean_methods(methods)
        self.regex, self.params_book, self.simplified_pattern = PatternParser.extract_params(pattern)
        self.has_parameters = bool(self.params_book)
        if dynamic is None:
            self.is_dynamic = PatternParser.is_dynamic_pattern(self.regex.pattern)
        else:
            self.is_dynamic = dynamic

    def call_handler(self, request: Request):
        if self.has_parameters:
            match = self.regex.match(request.url.path)
            function_params = {name: match.group(name) for name in self.params_book}
            return self.handler(request, **function_params)

        return self.handler(request)

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
