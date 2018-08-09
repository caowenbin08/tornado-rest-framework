# -*- coding: utf-8 -*-
from typing import Tuple, Iterable, Union


def clean_route_name(prefix: str, name: str) -> str:
    if prefix:
        if prefix[0] == ':':
            prefix = prefix[1:]
        if len(prefix) > 0:
            if prefix[len(prefix)-1] == ':':
                prefix = prefix[:len(prefix) - 1]
        if len(prefix) > 0:
            return prefix + '.' + name
    return name


def clean_methods(methods: Iterable[Union[str, bytes]]) -> Tuple[bytes]:
    """
    Prepares the HTTP methods tuple.
    :param methods: iter
    :return: A tuple of bytes with each HTTP method.
    """
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
