# -*- coding: utf-8 -*-
"""
配置文件
"""
import importlib
import os

from rest_framework.conf import global_settings
from rest_framework.utils.lazy import LazyObject, empty


ENVIRONMENT_VARIABLE = "TORNADO_REST_SETTINGS_MODULE"


class LazySettings(LazyObject):
    """
    懒加载配置
    """

    def _setup(self, name=None):
        settings_module = os.environ.get(ENVIRONMENT_VARIABLE)
        self._wrapped = Settings(settings_module)

    def __repr__(self):
        if self._wrapped is empty:
            return '<LazySettings [Unevaluated]>'
        return '<LazySettings "%(settings_module)s">' % {
            'settings_module': self._wrapped.SETTINGS_MODULE,
        }

    def __getattr__(self, name):
        if self._wrapped is empty or (self._wrapped.SETTINGS_MODULE is None
                                      and os.environ.get(ENVIRONMENT_VARIABLE)):
            self._setup(name)

        val = getattr(self._wrapped, name)
        self.__dict__[name] = val
        return val

    def __setattr__(self, name, value):
        if name == '_wrapped':
            self.__dict__.clear()
        else:
            self.__dict__.pop(name, None)

        super(LazySettings, self).__setattr__(name, value)

    def __delattr__(self, name):
        super(LazySettings, self).__delattr__(name)
        self.__dict__.pop(name, None)

    @property
    def configured(self):
        """
        Returns True if the settings have already been configured.
        """
        return self._wrapped is not empty


class Settings:
    def __init__(self, settings_module):
        """
        默认加载系统配置的
        用户自定义的可能会覆盖系统默认的
        :param settings_module:
        """
        self.SETTINGS_MODULE = settings_module
        # 加载全局默认的配置
        for setting in dir(global_settings):
            if setting.isupper():
                setattr(self, setting, getattr(global_settings, setting))

        if self.SETTINGS_MODULE:
            mod = importlib.import_module(self.SETTINGS_MODULE)

            for setting in dir(mod):
                if setting.isupper():
                    setting_value = getattr(mod, setting)
                    setattr(self, setting, setting_value)

    def __repr__(self):
        return '<%(cls)s "%(settings_module)s">' % {
            'cls': self.__class__.__name__,
            'settings_module': self.SETTINGS_MODULE,
        }


settings = LazySettings()
