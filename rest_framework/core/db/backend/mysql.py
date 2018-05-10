# -*- coding: utf-8 -*-
from rest_framework.lib.orm import connect
from rest_framework.core.db import DEFAULT_DB_ALIAS


class DatabaseWrapper:
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
        connect_params = {k.lower(): v for k, v in options.items()}
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

