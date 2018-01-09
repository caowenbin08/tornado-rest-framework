# -*- coding: utf-8 -*-
from rest_framework.lib.peewee.playhouse.db_url import connect

from rest_framework.core.db import DEFAULT_DB_ALIAS

__author__ = 'caowenbin'


class DatabaseWrapper(object):
    def __init__(self, db_settings, alias=DEFAULT_DB_ALIAS):
        """
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
        options = self.db_settings.get("OPTIONS", {})
        is_pool = options.pop("POOL", False)
        connect_params = {k.lower(): v for k, v in options.items()}
        db_url_tpl = "{scheme}://{user}:{pwd}@{host}:{port}/{db}"

        if is_pool:  # 同步且连接池
            scheme = "mysql+pool"
        else:
            scheme = "mysql"
            self.remove_invalid_params(connect_params, ("max_connections", ))

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

    @staticmethod
    def remove_invalid_params(connect_params, invalid_params):
        for p in invalid_params:
            connect_params.pop(p, None)
