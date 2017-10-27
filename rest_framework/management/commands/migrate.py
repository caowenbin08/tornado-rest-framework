# -*- coding: utf-8 -*-

from importlib import import_module
from rest_framework.conf import settings
from rest_framework.management.base import BaseCommand
from rest_framework.db import  database
from rest_framework import migrate

__author__ = 'caowenbin'


class Command(BaseCommand):
    @property
    def short_desc(self):
        return "升级表结构"

    def add_arguments(self, parser):
        parser.add_argument(
            '-auto', '--auto', action='store', default=False,
            help='自动创建迁移'
        )

    def handle(self, **options):
        pass