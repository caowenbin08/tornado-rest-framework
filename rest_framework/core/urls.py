# -*- coding: utf-8 -*-
from importlib import import_module

from rest_framework.utils.functional import import_object


def url(pattern, handler, name=None, prefix='', **kwargs):
    if isinstance(handler, (list, tuple)):
        return [(pattern + p, h, k, n) for p, h, k, n in handler]

    elif hasattr(handler, 'urlpatterns'):
        return [(pattern + p, h, k, n) for p, h, k, n in getattr(handler, 'urlpatterns', [])]

    elif isinstance(handler, str):
        if prefix.strip():
            handler = prefix + '.' + handler

        handler = import_object(handler)
        return pattern, handler, kwargs, name

    elif callable(handler):
        return pattern, handler, kwargs, name
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

