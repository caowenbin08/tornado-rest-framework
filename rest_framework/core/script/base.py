# -*- coding: utf-8 -*-
import os
import re
import sys
import types
import logging
import argparse

from rest_framework.core.script.commands import Option, Command, Server
from rest_framework.core.script.exceptions import CommandError


LOG_HANDLER = logging.StreamHandler()
LOG_HANDLER.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(LOG_HANDLER)

iteritems = lambda d: iter(d.items())

safe_actions = (
    getattr(argparse, "_StoreAction"),
    getattr(argparse, "_StoreConstAction"),
    getattr(argparse, "_StoreTrueAction"),
    getattr(argparse, "_StoreFalseAction"),
    getattr(argparse, "_AppendAction"),
    getattr(argparse, "_AppendConstAction"),
    getattr(argparse, "_CountAction"),
)

try:
    import argcomplete

    ARGCOMPLETE_IMPORTED = True
except ImportError:
    ARGCOMPLETE_IMPORTED = False


def add_help(parser, help_args):
    if not help_args:
        return

    parser.add_argument(
        *help_args,
        action='help',
        default=argparse.SUPPRESS,
        help='show this help message and exit'
    )


class Manager(object):
    help_args = ('-h', '--help')

    def __init__(self, with_default_commands=None, usage=None, help=None, description=None,
                 disable_argcomplete=False):
        """

        :param with_default_commands:
        :param usage:
        :param help:
        :param description:
        :param disable_argcomplete:
        """

        self._commands = dict()
        self._options = list()

        self.usage = usage
        self.help = help if help is not None else usage
        self.description = description if description is not None else usage
        self.disable_argcomplete = disable_argcomplete
        self.with_default_commands = with_default_commands

        self.parent = None

    def add_default_commands(self):

        if "runserver" not in self._commands:
            self.add_command("runserver", Server())

    def add_option(self, *args, **kwargs):
        self._options.append(Option(*args, **kwargs))

    def create_parser(self, prog, func_stack=(), parent=None):
        """
        Creates an ArgumentParser instance from options returned
        by get_options(), and subparser for the given commands.
        """
        prog = os.path.basename(prog)
        func_stack = func_stack + (self,)

        options_parser = argparse.ArgumentParser(add_help=False)
        for option in self.get_options():
            options_parser.add_argument(*option.args, **option.kwargs)

        parser = argparse.ArgumentParser(
            prog=prog,
            usage=self.usage,
            description=self.description,
            parents=[options_parser],
            add_help=False
        )

        add_help(parser, self.help_args)

        self._patch_argparser(parser)

        subparsers = parser.add_subparsers()

        for name, command in self._commands.items():
            usage = getattr(command, 'usage', None)
            help = getattr(command, 'help', None)
            if help is None: help = command.__doc__
            description = getattr(command, 'description', None)
            if description is None: description = command.__doc__

            command_parser = command.create_parser(name, func_stack=func_stack, parent=self)

            subparser = subparsers.add_parser(
                name,
                usage=usage,
                help=help,
                description=description,
                parents=[command_parser],
                add_help=False
            )

            if isinstance(command, Manager):
                self._patch_argparser(subparser)

        ## enable autocomplete only for parent parser when argcomplete is
        ## imported and it is NOT disabled in constructor
        if parent is None and ARGCOMPLETE_IMPORTED and not self.disable_argcomplete:
            argcomplete.autocomplete(parser, always_complete_options=True)

        self.parser = parser
        return parser

    # def foo(self, app, *args, **kwargs):
    #     print(args)

    def _patch_argparser(self, parser):
        """
        Patches the parser to print the full help if no arguments are supplied
        """

        def _parse_known_args(self, arg_strings, *args, **kw):
            if not arg_strings:
                self.print_help()
                self.exit(2)

            return self._parse_known_args2(arg_strings, *args, **kw)

        parser._parse_known_args2 = parser._parse_known_args
        parser._parse_known_args = types.MethodType(_parse_known_args, parser)

    def get_options(self):
        return self._options

    def add_command(self, *args, **kwargs):
        """
        Adds command to registry.

        :param command: Command instance
        :param name: Name of the command (optional)
        :param namespace: Namespace of the command (optional; pass as kwarg)
        """

        if len(args) == 1:
            command = args[0]
            name = None

        else:
            name, command = args

        if name is None:
            if hasattr(command, 'name'):
                name = command.name

            else:
                name = type(command).__name__.lower()
                name = re.sub(r'command$', '', name)

        if isinstance(command, Manager):
            command.parent = self

        if isinstance(command, type):
            command = command()

        namespace = kwargs.get('namespace')
        if not namespace:
            namespace = getattr(command, 'namespace', None)

        if namespace:
            if namespace not in self._commands:
                self.add_command(namespace, Manager())

            self._commands[namespace]._commands[name] = command

        else:
            self._commands[name] = command

    def command(self, func):
        """
        装饰程序，向注册表添加命令功能.

        :param func: command function.Arguments depend on the
                     options.

        """

        command = Command(func)
        self.add_command(func.__name__, command)

        return func

    def option(self, *args, **kwargs):
        """
        Decorator to add an option to a function. Automatically registers the
        function - do not use together with ``@command``. You can add as many
        ``@option`` calls as you like, for example::

            @option('-n', '--name', dest='name')
            @option('-u', '--url', dest='url')
            def hello(name, url):
                print "hello", name, url

        Takes the same arguments as the ``Option`` constructor.
        """

        option = Option(*args, **kwargs)

        def decorate(func):
            name = func.__name__

            if name not in self._commands:
                command = Command()
                command.run = func
                command.__doc__ = func.__doc__
                command.option_list = []

                self.add_command(name, command)

            self._commands[name].option_list.append(option)
            return func

        return decorate

    def set_defaults(self):
        if self.with_default_commands is None:
            self.with_default_commands = self.parent is None
        if self.with_default_commands:
            self.add_default_commands()
        self.with_default_commands = False

    def __call__(self, app=None, **kwargs):
        return "app"

    def handle(self, prog, args=None):
        self.set_defaults()
        app_parser = self.create_parser(prog)
        args = list(args or [])
        app_namespace, remaining_args = app_parser.parse_known_args(args)
        # get the handle function and remove it from parsed options
        kwargs = app_namespace.__dict__
        func_stack = kwargs.pop('func_stack', None)

        if not func_stack:
            app_parser.error('too few arguments')

        last_func = func_stack[-1]
        if remaining_args and not getattr(last_func, 'capture_all_args', False):
            app_parser.error('too many arguments')

        args = []
        for handle in func_stack:

            # get only safe config options
            config_keys = [action.dest for action in handle.parser._actions
                           if handle is last_func or action.__class__ in safe_actions]

            # pass only safe app config keys
            config = dict((k, v) for k, v in iteritems(kwargs)
                          if k in config_keys)

            # remove application config keys from handle kwargs
            kwargs = dict((k, v) for k, v in iteritems(kwargs)
                          if k not in config_keys)

            if handle is last_func and getattr(last_func, 'capture_all_args', False):
                args.append(remaining_args)

            try:
                res = handle(*args, **config)
            except TypeError as err:
                err.args = ("{}: {}".format(handle, str(err)),)
                raise

            args = [res]

        assert not kwargs
        return res

    def run(self, commands=None):
        if commands:
            self._commands.update(commands)

        try:
            result = self.handle(sys.argv[0], sys.argv[1:])
        except KeyboardInterrupt as e:
            result = 0
        except SystemExit as e:
            result = e.code
        except CommandError as e:
            LOGGER.error(e)
            result = 1

        sys.exit(result or 0)

