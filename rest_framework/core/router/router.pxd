# cython: language_level=3, boundscheck=False, wraparound=False, annotation_typing=False
import cython

############################################
# C IMPORTS
# noinspection PyUnresolvedReferences
from rest_framework.core.request.request cimport Request
# noinspection PyUnresolvedReferences
from rest_framework.core.cache.cache cimport CacheEngine
# noinspection PyUnresolvedReferences
from rest_framework.core.responses.responses cimport Response, RedirectResponse
# noinspection PyUnresolvedReferences
from rest_framework.core.components.components cimport ComponentsEngine
############################################


cdef class LRUCache:
    cdef:
        dict values
        object queue
        int max_size
        int current_size

    cdef set(self, str key, Route route)


cdef class Route:

    cdef:
        public str name
        public object handler
        public object app
        public object parent
        public bytes pattern
        public tuple components
        public bint receive_params
        public bint is_coroutine
        readonly tuple methods
        public object regex
        public list params_book
        public object simplified_pattern
        public bint has_parameters
        public bint is_dynamic
        CacheEngine cache
        public object limits

    cdef inline object call_handler(self, Request request, ComponentsEngine components)


cdef class Router:
    cdef:
        int strategy
        readonly dict reverse_index
        dict routes
        dict dynamic_routes
        public dict default_handlers
        LRUCache cache

    cdef Route get_route(self, Request request)

    @cython.locals(key=tuple, route=Route)
    cdef Route _find_route(self, bytes url, bytes method)
