# -*- coding: utf-8 -*-
from threading import local

from rest_framework.conf import settings
from rest_framework.core.cache.backend.base import InvalidCacheBackendError
from rest_framework.utils.functional import import_object

__author__ = 'caowenbin'


__all__ = [
    'cache', 'DEFAULT_CACHE_ALIAS', 'InvalidCacheBackendError',
    'CacheKeyWarning', 'BaseCache',
]

DEFAULT_CACHE_ALIAS = 'default'


def _create_cache(backend, **kwargs):
    try:
        # Try to get the CACHES entry for the given backend name first
        try:
            conf = settings.CACHES[backend]
        except KeyError:
            try:
                import_object(backend)
            except ImportError as e:
                raise InvalidCacheBackendError("Could not find backend '%s': %s" % (backend, e))
            location = kwargs.pop('LOCATION', '')
            params = kwargs
        else:
            params = conf.copy()
            params.update(kwargs)
            backend = params.pop('BACKEND')
            location = params.pop('LOCATION', '')
        backend_cls = import_object(backend)
    except ImportError as e:
        raise InvalidCacheBackendError("Could not find backend '%s': %s" % (backend, e))

    return backend_cls(location, params)


class CacheHandler(object):
    """
    A Cache Handler to manage access to Cache instances.

    Ensures only one instance of each alias exists per thread.
    """
    def __init__(self):
        self._caches = local()

    def __getitem__(self, alias):
        try:
            return self._caches.caches[alias]
        except AttributeError:
            self._caches.caches = {}
        except KeyError:
            pass

        if alias not in settings.CACHES:
            raise InvalidCacheBackendError(
                "Could not find config for '%s' in settings.CACHES" % alias
            )

        cache_backend = _create_cache(alias)
        self._caches.caches[alias] = cache_backend
        return cache_backend

    def all(self):
        return getattr(self._caches, 'caches', {}).values()


caches = CacheHandler()


class DefaultCacheProxy(object):
    """
    Proxy access to the default Cache object's attributes.

    This allows the legacy `cache` object to be thread-safe using the new
    ``caches`` API.
    """
    def __getattr__(self, name):
        return getattr(caches[DEFAULT_CACHE_ALIAS], name)

    def __setattr__(self, name, value):
        return setattr(caches[DEFAULT_CACHE_ALIAS], name, value)

    def __delattr__(self, name):
        return delattr(caches[DEFAULT_CACHE_ALIAS], name)

    def __contains__(self, key):
        return key in caches[DEFAULT_CACHE_ALIAS]

    def __eq__(self, other):
        return caches[DEFAULT_CACHE_ALIAS] == other

    def __ne__(self, other):
        return caches[DEFAULT_CACHE_ALIAS] != other


cache = DefaultCacheProxy()

