# -*- coding: utf-8 -*-
# import os
# import sys
# from types import ModuleType
from importlib import import_module
from rest_framework.conf import settings
from rest_framework.management.base import BaseCommand
from rest_framework.db import  database
from rest_framework import migrate

__author__ = 'caowenbin'

# CUR_DIR = os.getcwd()
# DEFAULT_MIGRATE_DIR = os.path.join(CUR_DIR, 'migrations')


class Command(BaseCommand):
    @property
    def short_desc(self):
        return "生成迁移文件"

    def add_arguments(self, parser):
        parser.add_argument(
            '-auto', '--auto', action='store', default=False,
            help='自动创建迁移'
        )

    def handle(self, **options):
        installed_apps = settings.INSTALLED_APPS
        for app in installed_apps:
            print("------app--", app, database)
            modules = import_module(app)
            migrate.generate('mysql', database, modules)

