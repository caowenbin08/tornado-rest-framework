# -*- coding: utf-8 -*-
import functools
import os
import pkgutil
import sys
from collections import defaultdict
from importlib import import_module

from rest_framework.management.base import CommandParser, CommandError, BaseCommand


__author__ = 'caowenbin'


class ManagementUtility(object):
    """
    命令的执行类
    """
    def __init__(self, argv=None):
        self.argv = argv or sys.argv[:]
        # 执行体的文件名
        self.process_name = os.path.basename(self.argv[0])
        self.settings_exception = None

    def main_help_text(self, commands_only=False):
        """
        Returns the script's main help text, as a string.
        """
        if commands_only:
            usage = sorted(self.get_commands().keys())
        else:
            usage = [
                "",
                "执行 '{name} help <command>' 或 '{name} <command> -h' 查看<command>的帮助信息".format(name=self.process_name),
                "",
                "命令集(commands):",
            ]
            commands_dict = defaultdict(lambda: [])
            for name, app in self.get_commands().items():
                app = app.rpartition('.')[-1]
                commands_dict[app].append(name)
            for app in sorted(commands_dict.keys()):
                usage.append("")
                usage.append("[%s]" % app)
                for name in sorted(commands_dict[app]):
                    usage.append("    %s   %s" % (name, self.fetch_command(name).short_desc))

        return '\n'.join(usage)

    @staticmethod
    def find_commands(management_dir):
        """
        根据当前管理目录查找commands目录下的命令
        :param management_dir:
        :return:
        """
        command_dir = os.path.join(management_dir, 'commands')
        return [name for _, name, is_pkg in pkgutil.iter_modules([command_dir])
                if not is_pkg and not name.startswith('_')]

    @staticmethod
    def load_command_class(app_name, name):
        """
        动态初化加载命令处理类实例
        :param app_name:
        :param name: 命令文件名
        :return:
        """
        module = import_module('%s.management.commands.%s' % (app_name, name))
        return module.Command()

    @functools.lru_cache(maxsize=None)
    def get_commands(self):
        """
        获得命令处理集合
        """
        commands = {name: 'rest_framework' for name in self.find_commands(__path__[0])}

        return commands

    def fetch_command(self, command):
        """
        根据命令标识发现返回命令处理类实例
        :param command:
        :return:
        """
        commands = self.get_commands()
        try:
            app_name = commands[command]
        except KeyError:
            sys.stderr.write(
                "未知命令: %r\n请运行 '%s help' 查看支持的命令集.\n"
                % (command, self.process_name)
            )
            sys.exit(1)

        if isinstance(app_name, BaseCommand):
            process_class = app_name
        else:
            process_class = self.load_command_class(app_name, command)

        return process_class

    def execute(self):
        try:
            command = self.argv[1]
        except IndexError:
            command = 'help'

        parser = CommandParser(None, add_help=False)
        parser.add_argument('-settings', '--settings')
        parser.add_argument('args', nargs='*')
        try:
            options, args = parser.parse_known_args(self.argv[2:])
        except CommandError:
            pass

        if command == 'help':
            if len(options.args) < 1:
                sys.stdout.write(self.main_help_text() + '\n')
            else:
                self.fetch_command(options.args[0]).print_help(self.process_name, options.args[0])

        elif self.argv[1:] in (['--help'], ['-h']):
            sys.stdout.write(self.main_help_text() + '\n')
        else:
            cmd = self.fetch_command(command)
            cmd.run_from_argv(self.argv)


def execute_from_command_line(argv=None):
    """
    主要用于对外执行命令.
    """
    utility = ManagementUtility(argv)
    utility.execute()
