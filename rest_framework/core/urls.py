# -*- coding: utf-8 -*-
from importlib import import_module

from rest_framework.utils.functional import import_object


class Url:
    def __init__(self, pattern, handler, name=None, **kwargs):
        self.pattern = pattern
        self.handler = handler
        self.name = name
        self.kwargs = kwargs


def url(pattern, handler, name=None, prefix='', **kwargs):
    if isinstance(handler, (list, tuple)) or hasattr(handler, 'urlpatterns'):
        urls = []
        if hasattr(handler, 'urlpatterns'):
            handler = getattr(handler, 'urlpatterns', [])

        for route in handler:
            if isinstance(route, (list, tuple)):
                temp = [url(pattern + r.pattern, r.handler, r.name, **r.kwargs) for r in route]
                urls.extend(temp)
            else:
                u = Url(pattern+route.pattern, route.handler, route.name, **route.kwargs)
                urls.append(u)
        return urls

    elif isinstance(handler, str):
        if prefix.strip():
            handler = prefix + '.' + handler

        handler = import_object(handler)
        return Url(pattern, handler, name, **kwargs)

    elif callable(handler):
        return Url(pattern, handler, name, **kwargs)
    else:
        raise TypeError('view must be a callable or a list/tuple in the case of include().')


def include(urlconf_module):
    if isinstance(urlconf_module, str):
        urlconf_module = import_module(urlconf_module)

    urlpatterns = getattr(urlconf_module, 'urlpatterns', [])

    return urlpatterns


def url_patterns(urlconf_module):
    if isinstance(urlconf_module, str):
        urlconf_module = import_module(urlconf_module)

    urlpatterns = getattr(urlconf_module, 'urlpatterns', [])

    url_specs = []
    for url_spec in urlpatterns:
        if isinstance(url_spec, list):
            url_specs.extend(url_spec)
        else:
            url_specs.append(url_spec)
    return url_specs

