# -*- coding: utf-8 -*-
from nose import with_setup
from rest_framework.conf import settings

__author__ = 'caowenbin'


def teardown_del_setting():
    empty = object()
    settings._wrapped = empty


@with_setup(teardown=teardown_del_setting)
def test_not_set_setting_path():
    dict_data = settings.dict_data
    assert settings.DEBUG is False
    assert dict_data
    assert dict_data["debug"] is False


def setup_reload_setting_setup():
    settings._setup()


@with_setup(setup=setup_reload_setting_setup)
def test_set_setting_path():
    assert settings.DEBUG
    assert hasattr(settings, "Tornado") is False
    assert hasattr(settings, "TORNADO_REST_VERSION")
    assert settings.TORNADO_REST_VERSION == "0.1"
    assert settings.dict_data["tornado_rest_version"] == "0.1"

