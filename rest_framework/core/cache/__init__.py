# -*- coding: utf-8 -*-
from importlib import import_module
from threading import local

from rest_framework.conf import settings
from rest_framework.core.exceptions import ImproperlyConfigured

DEFAULT_CACHE_ALIAS = 'default'


def _create_cache(cache_config, **kwargs):
    try:
        params = cache_config
        params.update(kwargs)
        backend = params.get('BACKEND')
        location = params.get('LOCATION', '')
        backend_module = import_module(backend)
    except ImportError as e:
        raise ImproperlyConfigured("Could not find backend '%s': %s" % (backend, e))

    return backend_module.CacheWrapper(location, params)


class CacheHandler:
    def __init__(self):
        self._caches = local()

    def __getitem__(self, alias):
        try:
            return self._caches.caches[alias]
        except AttributeError:
            self._caches.caches = {}
        except KeyError:
            pass

        cache_configs = settings.CACHES
        if alias not in cache_configs:
            raise ImproperlyConfigured(
                "Could not find config for '%s' in settings.CACHES" % alias
            )

        cache_backend = _create_cache(cache_configs[alias])
        self._caches.caches[alias] = cache_backend
        return cache_backend

    def all(self):
        return getattr(self._caches, 'caches', {}).values()


caches = CacheHandler()


class DefaultCacheProxy:
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

