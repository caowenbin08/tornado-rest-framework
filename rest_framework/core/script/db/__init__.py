# -*- coding: utf-8 -*-
from importlib import import_module
from rest_framework.conf import settings
from rest_framework.core.db import models
from rest_framework.core.script import Manager



MigrateCommand = Manager(usage="Database related commands")


def get_table_models(module):
    """

    :param module:
    :return:
    """
    table_models = list(
        filter(
            lambda m: isinstance(m, type) and issubclass(m, models.Model)
            and hasattr(m, '_meta') and not getattr(getattr(m, "_meta"), "abstract", False),
            (getattr(module, model) for model in dir(module))
        )
    )

    return table_models


@MigrateCommand.command
async def init(*args, **kwargs):
    """
    Initialize the table structure
    """
    table_models = []
    installed_apps = settings.INSTALLED_APPS
    for app in installed_apps:
        module = import_module(app)
        table_models.extend(get_table_models(module=module))
    table_models = set(table_models)
    await models.create_model_tables(table_models, fail_silently=True)
    table_name_list = [model.__name__ for model in table_models]

    print("Create Table:\n", "\n".join(table_name_list))


@MigrateCommand.command
async def clean(*args, **kwargs):
    """
    Clear all table structure
    """
    installed_apps = settings.INSTALLED_APPS
    table_models = []
    for app in installed_apps:
        module = import_module(app)
        table_models.extend(get_table_models(module=module))
    table_models = set(table_models)
    await models.drop_model_tables(table_models, fail_silently=True)
    table_name_list = [model.__name__ for model in table_models]

    print("Drop Table:\n", "\n".join(table_name_list))
