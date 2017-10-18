# -*- coding: utf-8 -*-
import re
import os
import sys
import errno
import shutil
from argparse import ArgumentParser
from os.path import join, basename

from rest_framework import management

PATTERN = re.compile('^[a-zA-Z]+[a-zA-Z_]*[a-zA-Z]$')


class CommandError(Exception):
    pass


class SystemCheckError(CommandError):
    pass


class CommandParser(ArgumentParser):
    """
    定制ArgumentParser类改善和防止一些错误消息直接导致系统退出
    """
    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        super(CommandParser, self).__init__(**kwargs)

    def parse_args(self, args=None, namespace=None):
        if (hasattr(self.cmd, 'missing_args_message') and
                not (args or any(not arg.startswith('-') for arg in args))):
            self.error(self.cmd.missing_args_message)
        return super(CommandParser, self).parse_args(args, namespace)

    def error(self, message):
        if self.cmd.called_from_command_line:
            super(CommandParser, self).error(message)
        else:
            raise CommandError("异常: %s" % message)


def handle_default_options(options):
    if options.settings:
        os.environ['TORNADO_REST_SETTINGS_MODULE'] = options.settings

    if options.pypath:
        sys.path.insert(0, options.pypath)


class BaseCommand(object):
    help = ''
    called_from_command_line = False

    def create_parser(self, process, command):
        """
        创建命令参数
        :param process: 运行载体，比如manage.py
        :param command: 命令标识
        :return:
        """
        parser = CommandParser(
            cmd=self,
            prog="{process} {command}".format(process=basename(process), command=command),
            description=self.help or None
        )
        parser.add_argument(
            '-settings', '--settings',
            help="设置配置(settings)模块的Python路径，如果没有设置，则TORNADO_REST_SETTINGS_MODULE环境变量将被使用",
        )
        parser.add_argument(
            '-pypath', '--pypath',
            help='一个目录添加到Python路径首位置, 例如："/opt/projects/myproject".',
        )
        self.add_arguments(parser)
        return parser

    def add_arguments(self, parser):
        """
        添加命令参数
        """
        pass

    def print_help(self, process, command):
        """
        输出帮助信息
        """
        parser = self.create_parser(process, command)
        parser.print_help()

    def run_from_argv(self, argv):
        """
        执行参数命令
        :param argv:
        :return:
        """
        self.called_from_command_line = True
        parser = self.create_parser(argv[0], argv[1])
        options = parser.parse_args(argv[2:])
        cmd_options = vars(options)
        args = cmd_options.pop('args', ())
        handle_default_options(options)
        try:
            self.execute(*args, **cmd_options)
        except Exception as e:
            self.stderr.write('%s: %s' % (e.__class__.__name__, e))
            sys.exit(1)

    def execute(self, *args, **options):
        """
        调用各个命令的执行函数
        """
        output = self.handle(*args, **options)
        return output

    def handle(self, *args, **options):
        """
        业务处理的抽象方法
        :param args:
        :param options:
        :return:
        """
        raise NotImplementedError('继承BaseCommand的子类必须实现handle()方法')


class TemplateCommand(BaseCommand):

    def __init__(self):
        self.app_or_project = None
        self.paths_to_remove = None
        self.settings = None

    def add_arguments(self, parser):
        parser.add_argument('name', help='项目名或应用名')
        parser.add_argument('directory', nargs='?', help='所在目录')

    @staticmethod
    def templates_dir(app_or_project):
        _templates_base_dir = join(management.__path__[0], 'templates')
        return join(_templates_base_dir, app_or_project)

    def handle(self, app_or_project, name, target=None, **options):
        # self.app_or_project = app_or_project
        # self.paths_to_remove = []
        # self.verbosity = options['verbosity']

        self.validate_name(name)
        # 如果目标目录没有指定，则在当前目录下创建
        if target is None:
            top_dir = os.path.join(os.getcwd(), name)
            try:
                os.makedirs(top_dir)
            except OSError as e:
                raise CommandError("'%s'目录已经存在" % top_dir if e.errno == errno.EEXIST else e)
        else:
            top_dir = os.path.abspath(os.path.expanduser(target))

            if not os.path.exists(top_dir):
                raise CommandError("'%s'目录不存在，请先创建此目录" % top_dir)

        # extensions = tuple(handle_extensions(options['extensions']))
        # extra_files = []
        # for file in options['files']:
        #     extra_files.extend(map(lambda x: x.strip(), file.split(',')))
        # if self.verbosity >= 2:
        #     self.stdout.write("Rendering %s template files with "
        #                       "extensions: %s\n" %
        #                       (app_or_project, ', '.join(extensions)))
        #     self.stdout.write("Rendering %s template files with "
        #                       "filenames: %s\n" %
        #                       (app_or_project, ', '.join(extra_files)))

        # base_name = '%s_name' % app_or_project
        # base_subdir = '%s_template' % app_or_project
        # base_directory = '%s_directory' % app_or_project
        # camel_case_name = 'camel_case_%s_name' % app_or_project
        # camel_case_value = ''.join(x for x in name.title() if x != '_')

        # context = Context(dict(options, **{
        #     base_name: name,
        #     base_directory: top_dir,
        #     camel_case_name: camel_case_value,
        #     'docs_version': get_docs_version(),
        #     'django_version': django.__version__,
        #     'unicode_literals': '' if six.PY3 else '# -*- coding: utf-8 -*-\n'
        #                                            'from __future__ import unicode_literals\n\n',
        # }), autoescape=False)

        # Setup a stub settings environment for template rendering
        # if not settings.configured:
        #     settings.configure()
        #     django.setup()

        template_dir = os.path.join(management.__path__[0], 'templates', app_or_project)
        prefix_length = len(template_dir) + 1

        for root, dirs, files in os.walk(template_dir):

            path_rest = root[prefix_length:]
            relative_dir = path_rest.replace(app_or_project, name)
            if relative_dir:
                target_dir = os.path.join(top_dir, relative_dir)
                if not os.path.exists(target_dir):
                    os.mkdir(target_dir)

            for dirname in dirs[:]:
                if dirname.startswith('.') or dirname == '__pycache__':
                    dirs.remove(dirname)

            for filename in files:
                if filename.endswith(('.pyo', '.pyc', '.py.class')):
                    # Ignore some files as they cause various breakages.
                    continue
                old_path = os.path.join(root, filename)
                new_path = os.path.join(top_dir, relative_dir, filename.replace(app_or_project, name))
                print(old_path, "==new_path===", new_path)
                # for old_suffix, new_suffix in self.rewrite_template_suffixes:
                #     if new_path.endswith(old_suffix):
                #         new_path = new_path[:-len(old_suffix)] + new_suffix
                #         break  # Only rewrite once

                if os.path.exists(new_path):
                    raise CommandError("%s already exists, overlaying a "
                                       "project or app into an existing "
                                       "directory won't replace conflicting "
                                       "files" % new_path)

                # Only render the Python files, as we don't want to
                # accidentally render Django templates files
                # if new_path.endswith(extensions) or filename in extra_files:
                #     with io.open(old_path, 'r', encoding='utf-8') as template_file:
                #         content = template_file.read()
                #     template = Engine().from_string(content)
                #     content = template.render(context)
                #     with io.open(new_path, 'w', encoding='utf-8') as new_file:
                #         new_file.write(content)
                shutil.copyfile(old_path, new_path)

                # if self.verbosity >= 2:
                #     self.stdout.write("Creating %s\n" % new_path)
                try:
                    shutil.copymode(old_path, new_path)
                    self.make_writeable(new_path)
                except OSError:
                    self.stderr.write(
                        "Notice: Couldn't set permission bits on %s. You're "
                        "probably using an uncommon filesystem setup. No "
                        "problem." % new_path, self.style.NOTICE)

        # if self.paths_to_remove:
        #     if self.verbosity >= 2:
        #         self.stdout.write("Cleaning up temporary files.\n")
        #     for path_to_remove in self.paths_to_remove:
        #         if path.isfile(path_to_remove):
        #             os.remove(path_to_remove)
        #         else:
        #             shutil.rmtree(path_to_remove)

    @staticmethod
    def validate_name(name):
        if name is None:
            raise CommandError("项目(或应用)名不能为空")

        if not PATTERN.match(name):
            raise CommandError("项目(或应用)名必须由字母或下划线组成，但开头或结尾必须为字母")
