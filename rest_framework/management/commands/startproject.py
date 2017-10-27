# -*- coding: utf-8 -*-

from importlib import import_module

from rest_framework.management.base import CommandError, TemplateCommand


class Command(TemplateCommand):
    help = "必须给一个项目名在当前目录中或指定目录中创建。"
    missing_args_message = "必须指定项目名称(name参数)。"

    @property
    def short_desc(self):
        return "创建项目"

    def handle(self, **options):
        project_name, target = options.pop('name'), options.pop('directory')
        self.validate_name(project_name)
        try:
            import_module(project_name)
        except ImportError:
            pass
        else:
            raise CommandError("{name}与现有的Python模块的名称冲突,不能作为项目名称".format(name=project_name))

        options['project_name'] = project_name
        super(Command, self).handle('project', project_name, target, **options)

