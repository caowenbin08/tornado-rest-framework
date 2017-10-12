# -*- coding: utf-8 -*-
from rest_framework.db.conn import ConnectionHandler

__author__ = 'caowenbin'

DEFAULT_DB_ALIAS = 'default'
# 所有数据库连接
databases = ConnectionHandler()
# 默认数据库连接
database = databases[DEFAULT_DB_ALIAS]
