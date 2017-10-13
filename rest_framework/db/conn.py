# -*- coding: utf-8 -*-
from threading import local
from importlib import import_module

from rest_framework.conf import settings
from rest_framework.exceptions import ImproperlyConfigured
from rest_framework.helpers.cached_property import cached_property

__author__ = 'caowenbin'

DEFAULT_DB_ALIAS = 'default'


class ConnectionDoesNotExist(Exception):
    pass


class ConnectionHandler(object):
    def __init__(self, databases=None):
        """
        :param databases: 是一个可选的字典，结构请查看settings.DATABASES的定义
        """
        self._databases = databases
        self._connections = local()

    @cached_property
    def databases(self):
        if self._databases is None:
            self._databases = settings.DATABASES

        if DEFAULT_DB_ALIAS not in self._databases:
            raise ImproperlyConfigured("You must define a '%s' database" % DEFAULT_DB_ALIAS)

        return self._databases

    def ensure_defaults(self, alias):
        """
        确保数据库的连接参数存在，如果没有则设置默认值
        """
        try:
            conn = self.databases[alias]
        except KeyError:
            raise ConnectionDoesNotExist("The connection %s doesn't exist" % alias)

        conn.setdefault('POOL', False)
        conn.setdefault("CHARSET", "utf8")

        if conn["POOL"]:
            conn.setdefault("MAX_CONNECTIONS", 5)  # 连接池最大连接数
            conn.setdefault("STALE_TIMEOUT", 100)  # 僵尸连接超时间，单位为秒

        for setting in ['NAME', 'USER', 'PASSWORD', 'HOST', 'PORT']:
            conn.setdefault(setting, '')

    @staticmethod
    def load_backend(backend_name):
        """
        加载数据库连接处理块，如果不存在，则抛出异常
        :param backend_name:
        :return:
        """
        try:
            return import_module(backend_name)
        except ImportError as e_user:
            raise ImproperlyConfigured(
                "{backend_name} isn't an available database backend."
                "\nError was: {msg}".format(
                    backend_name=backend_name, msg=e_user
                )
            )

    def __getitem__(self, alias):
        if hasattr(self._connections, alias):
            return getattr(self._connections, alias)

        self.ensure_defaults(alias)
        db = self.databases[alias]
        backend = self.load_backend(db['ENGINE'])
        conn = backend.DatabaseWrapper(db, alias).connection
        setattr(self._connections, alias, conn)
        return conn

    def __setitem__(self, key, value):
        setattr(self._connections, key, value)

    def __delitem__(self, key):
        delattr(self._connections, key)

    def __iter__(self):
        return iter(self.databases)

