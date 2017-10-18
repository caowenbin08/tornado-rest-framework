import os
import re
import string
from os.path import join, exists, abspath
from shutil import ignore_patterns, move, copy2, copystat

from importlib import import_module

from rest_framework import management
from rest_framework.management.base import CommandError, TemplateCommand, CommandParser, BaseCommand

TEMPLATES_TO_RENDER = (
    ('scrapy.cfg',),
    ('manage.py.tmpl',),
    ('${project_name}', 'settings.py.tmpl'),
    ('${project_name}', 'items.py.tmpl'),
    ('${project_name}', 'pipelines.py.tmpl'),
    ('${project_name}', 'middlewares.py.tmpl'),
)

IGNORE = ignore_patterns('*.pyc', '.svn')

# from ..utils import get_random_secret_key
CAMELCASE_INVALID_CHARS = re.compile('[^a-zA-Z\d]')


class Command(TemplateCommand):
    help = "必须给一个项目名在当前目录中或指定目录中创建。"
    missing_args_message = "必须指定项目名称(name参数)。"

    @property
    def short_desc(self):
        return "创建项目"

    @property
    def templates_dir(self):
        _templates_base_dir = join(management.__path__[0], 'templates')
        return join(_templates_base_dir, "project")

    def _copytree(self, src, dst):
        """
        Since the original function always creates the directory, to resolve
        the issue a new function had to be created. It's a simple copy and
        was reduced for this case.

        More info at:
        https://github.com/scrapy/scrapy/pull/2005
        """
        ignore = IGNORE
        names = os.listdir(src)
        ignored_names = ignore(src, names)

        if not os.path.exists(dst):
            os.makedirs(dst)

        for name in names:
            if name in ignored_names:
                continue

            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            if os.path.isdir(srcname):
                self._copytree(srcname, dstname)
            else:
                copy2(srcname, dstname)
        copystat(src, dst)

    @staticmethod
    def string_camelcase(string):
        return CAMELCASE_INVALID_CHARS.sub('', string.title())

    @staticmethod
    def render_templatefile(path, **kwargs):
        with open(path, 'rb') as fp:
            raw = fp.read().decode('utf8')

        content = string.Template(raw).substitute(**kwargs)

        render_path = path[:-len('.tmpl')] if path.endswith('.tmpl') else path
        with open(render_path, 'wb') as fp:
            fp.write(content.encode('utf8'))
        if path.endswith('.tmpl'):
            os.remove(path)

    def handle(self, **options):
        print("---optionsoptions---=====", options)
        project_name, target = options.pop('name'), options.pop('directory')
        self.validate_name(project_name, "project")

        # Check that the project_name cannot be imported.
        try:
            import_module(project_name)
        except ImportError:
            pass
        else:
            raise CommandError(
                "%r conflicts with the name of an existing Python module and "
                "cannot be used as a project name. Please try another name." % project_name
            )

        # Create a random SECRET_KEY to put it in the main settings.
        options['secret_key'] = get_random_secret_key()

        super(Command, self).handle('project', project_name, target, **options)
        # project_name, target = options.pop('name'), options.pop('directory')
        # self.validate_name(project_name, "project")
        # print("---target-", target)
        # if target is None:
        #     project_dir = os.path.join(os.getcwd(), project_name)
        # else:
        #     project_dir = os.path.abspath(os.path.expanduser(target))
        # print("---project_dir-", project_dir)
        # if exists(join(project_dir, 'scrapy.cfg')):
        #     print('Error: scrapy.cfg already exists in %s' % abspath(project_dir))
        #     return
        #
        # try:
        #     import_module(project_name)
        # except ImportError:
        #     pass
        # else:
        #     return
        #
        # self._copytree(self.templates_dir, abspath(project_dir))
        # move(join(project_dir, 'module'), join(project_dir, project_name))
        # for paths in TEMPLATES_TO_RENDER:
        #     path = join(*paths)
        #     tplfile = join(project_dir,
        #         string.Template(path).substitute(project_name=project_name))
        #     self.render_templatefile(tplfile, project_name=project_name,
        #         ProjectName=self.string_camelcase(project_name))
        # print("New Scrapy project %r, using template directory %r, created in:" % \
        #       (project_name, self.templates_dir))
        # print("    %s\n" % abspath(project_dir))
        # print("You can start your first spider with:")
        # print("    cd %s" % project_dir)
        # print("    scrapy genspider example example.com")
        #

        # try:
        #     import_module(project_name)
        # except ImportError:
        #     pass
        # else:
        #     raise CommandError(
        #         "%r conflicts with the name of an existing Python module and "
        #         "cannot be used as a project name. Please try another name." % project_name
        #     )
        #
        # super(Command, self).handle('project', project_name, target, **options)
