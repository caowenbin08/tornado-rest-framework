# -*- coding: utf-8 -*-
import re
import os
import io
import sys
import stat
import errno
import shutil
from argparse import ArgumentParser
from os.path import join, basename
from tornado import template
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
    stdout = sys.stdout
    stderr = sys.stderr

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

    rewrite_template_suffixes = (
        ('.py.tpl', '.py'),
    )
    # 需要解析模板文件渲染参数的文件
    extra_files = ("settings.py.tpl", )

    def add_arguments(self, parser):
        parser.add_argument('name', help='项目名或应用名')
        parser.add_argument('directory', nargs='?', help='所在目录')

    def handle(self, app_or_project, name, target=None, **options):
        self.validate_name(name)
        # 如果目标目录没有指定，则在当前目录下加项目名创建
        if target is None:
            top_dir = join(os.getcwd(), name)
            try:
                os.makedirs(top_dir)
            except OSError as e:
                raise CommandError("'%s'目录已经存在" % top_dir if e.errno == errno.EEXIST else e)
        else:
            top_dir = os.path.abspath(os.path.expanduser(target))

        if not os.path.exists(top_dir):
            raise CommandError("'%s'目录不存在，请先创建此目录" % top_dir)

        template_dir = join(management.__path__[0], 'templates', app_or_project)
        prefix_length = len(template_dir) + 1

        for root, dirs, files in os.walk(template_dir):

            path_rest = root[prefix_length:]
            relative_dir = path_rest.replace(app_or_project, name)
            if relative_dir:
                target_dir = join(top_dir, relative_dir)
                if not os.path.exists(target_dir):
                    os.mkdir(target_dir)

            for dir_name in dirs[:]:
                if dir_name.startswith('.') or dir_name == '__pycache__':
                    dirs.remove(dir_name)

            for filename in files:
                if filename.endswith(('.pyo', '.pyc', '.py.class')):
                    continue
                old_path = join(root, filename)
                new_path = join(top_dir, relative_dir, filename.replace(app_or_project, name))

                for old_suffix, new_suffix in self.rewrite_template_suffixes:
                    if new_path.endswith(old_suffix):
                        new_path = new_path[:-len(old_suffix)] + new_suffix
                        break

                if filename in self.extra_files:
                    with io.open(old_path, 'rb') as template_file:
                        t = template.Template(template_file.read())
                        content = t.generate(**options)

                    with io.open(new_path, 'wb') as new_file:
                        new_file.write(content)
                else:

                    shutil.copyfile(old_path, new_path)

                try:
                    shutil.copymode(old_path, new_path)
                    self.make_writeable(new_path)
                except OSError:
                    self.stderr.write("无法设置权限在{path}，请检查文件系统设置".format(path=new_path))

    @staticmethod
    def validate_name(name):
        if name is None:
            raise CommandError("项目(或应用)名不能为空")

        if not PATTERN.match(name):
            raise CommandError("项目(或应用)名必须由字母或下划线组成，但开头或结尾必须为字母")

    @staticmethod
    def make_writeable(filename):
        """
        确保文件是可写的
        :param filename:
        :return:
        """
        if sys.platform.startswith('java'):
            return

        if not os.access(filename, os.W_OK):
            st = os.stat(filename)
            new_permissions = stat.S_IMODE(st.st_mode) | stat.S_IWUSR
            os.chmod(filename, new_permissions)
