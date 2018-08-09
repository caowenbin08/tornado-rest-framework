# -*- coding: utf-8 -*-
from urllib.parse import urlparse, parse_qsl
from .peewee import *

from .mysql import AsyncMySQLDatabase
from .model import AsyncModel as Model
from .database import create_model_tables, drop_model_tables
from .query import *
schemes = {
    'mysql': AsyncMySQLDatabase,
}


def register_database(db_class, *names):
    global schemes
    for name in names:
        schemes[name] = db_class


def register_database(db_class, *names):
    global schemes
    for name in names:
        schemes[name] = db_class


def parse_url_to_dict(parsed):
    # urlparse in python 2.6 is broken so query will be empty and instead
    # appended to path complete with '?'
    path_parts = parsed.path[1:].split('?')
    try:
        query = path_parts[1]
    except IndexError:
        query = parsed.query

    connect_kwargs = {'database': path_parts[0]}
    if parsed.username:
        connect_kwargs['user'] = parsed.username
    if parsed.password:
        connect_kwargs['password'] = parsed.password
    if parsed.hostname:
        connect_kwargs['host'] = parsed.hostname
    if parsed.port:
        connect_kwargs['port'] = parsed.port

    # Get additional connection args from the query string
    qs_args = parse_qsl(query, keep_blank_values=True)
    for key, value in qs_args:
        if value.lower() == 'false':
            value = False
        elif value.lower() == 'true':
            value = True
        elif value.isdigit():
            value = int(value)
        elif '.' in value and all(p.isdigit() for p in value.split('.', 1)):
            try:
                value = float(value)
            except ValueError:
                pass
        elif value.lower() in ('null', 'none'):
            value = None

        connect_kwargs[key] = value

    return connect_kwargs


def connect(url, **connect_params):
    parsed = urlparse(url)
    connect_kwargs = parse_url_to_dict(parsed)
    connect_kwargs.update(connect_params)
    database_class = schemes.get(parsed.scheme)

    if database_class is None:
        if database_class in schemes:
            raise RuntimeError('Attempted to use "%s" but a required library '
                               'could not be imported.' % parsed.scheme)
        else:
            raise RuntimeError('Unrecognized or unsupported scheme: "%s".' % parsed.scheme)

    return database_class(**connect_kwargs)
