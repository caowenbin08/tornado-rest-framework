# -*- coding: utf-8 -*-
from playhouse.db_url import connect

from rest_framework.core.db import DEFAULT_DB_ALIAS

__author__ = 'caowenbin'


class DatabaseWrapper(object):
    def __init__(self, db_settings, alias=DEFAULT_DB_ALIAS):
        """
        数据库的配置如下：
             'default': {
                 'ENGINE': 'rest_framework.db.backend.mysql',
                 'NAME': 'orders',
                 'USER': 'root',
                 'PASSWORD': '',
                 'HOST': '127.0.0.1',
                 'PORT': '3306',
                 'POOL': True
            }
        :param db_settings: 为default的值
        :param alias: 为default
        """
        self.db_settings = db_settings
        self.alias = alias

    @property
    def connection(self):
        """
        :return:
        """
        pool = self.db_settings.get("POOL", False)
        connect_params = dict(
            charset=self.db_settings.get("CHARSET", "utf8")
        )
        if pool:
            db_url_tpl = "{scheme}://{user}:{pwd}@{host}:{port}/{db}"
            connect_params["max_connections"] = self.db_settings.get("MAX_CONNECTIONS", 5)
            connect_params["stale_timeout"] = self.db_settings.get("STALE_TIMEOUT", 100)
            scheme = "mysql+pool"
        else:
            db_url_tpl = "{scheme}://{user}:{pwd}@{host}:{port}/{db}"
            scheme = "mysql"

        db_url = db_url_tpl.format(
            scheme=scheme,
            user=self.db_settings.get("USER", ""),
            pwd=self.db_settings.get("PASSWORD", ""),
            host=self.db_settings.get("HOST", "127.0.0.1"),
            port=self.db_settings.get("PORT", 3306),
            db=self.db_settings.get("NAME", "")
        )

        database = connect(url=db_url, **connect_params)

        return database
