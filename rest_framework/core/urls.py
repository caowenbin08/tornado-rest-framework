# -*- coding: utf-8 -*-
from importlib import import_module

from rest_framework.utils.functional import import_object


def url(pattern, handler, kwargs=None, name=None, prefix=''):
    """
    指定URL和处理程序之间的映射，即tornado.web.URLSpec
    """
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
