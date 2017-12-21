# -*- coding: utf-8 -*-
import peewee

from rest_framework.core.db.conn import ConnectionHandler, DEFAULT_DB_ALIAS

__author__ = 'caowenbin'
models = peewee
# 所有数据库连接
databases = ConnectionHandler()


class DefaultConnectionProxy(object):
    def __getattr__(self, item):
        return getattr(databases[DEFAULT_DB_ALIAS], item)

    def __setattr__(self, name, value):
        return setattr(databases[DEFAULT_DB_ALIAS], name, value)

    def __delattr__(self, name):
        return delattr(databases[DEFAULT_DB_ALIAS], name)

    def __eq__(self, other):
        return databases[DEFAULT_DB_ALIAS] == other

    def __ne__(self, other):
        return databases[DEFAULT_DB_ALIAS] != other

# 默认数据库连接
database = DefaultConnectionProxy()
