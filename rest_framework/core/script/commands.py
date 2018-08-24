# -*- coding: utf-8 -*-
import re
import inspect
import argparse
import asyncio
from rest_framework.core import singnals
from rest_framework.core.application import get_application

PATTERN = re.compile('^[a-zA-Z]+[a-zA-Z_]*[a-zA-Z]$')


class Group(object):
    """
    Stores argument groups and mutually exclusive groups for
    `ArgumentParser.add_argument_group <http://argparse.googlecode.com/svn/trunk/doc/other-methods.html#argument-groups>`
    or `ArgumentParser.add_mutually_exclusive_group <http://argparse.googlecode.com/svn/trunk/doc/other-methods.html#add_mutually_exclusive_group>`.

    Note: The title and description params cannot be used with the exclusive
    or required params.

    :param options: A list of Option classes to add to this group
    :param title: A string to use as the title of the argument group
    :param description: A string to use as the description of the argument
                        group
    :param exclusive: A boolean indicating if this is an argument group or a
                      mutually exclusive group
    :param required: A boolean indicating if this mutually exclusive group
                     must have an option selected
    """

    def __init__(self, *options, **kwargs):
        self.option_list = options

        self.title = kwargs.pop("title", None)
        self.description = kwargs.pop("description", None)
        self.exclusive = kwargs.pop("exclusive", None)
        self.required = kwargs.pop("required", None)

        if ((self.title or self.description) and
                (self.required or self.exclusive)):
            raise TypeError("title and/or description cannot be used with "
                            "required and/or exclusive.")

        super(Group, self).__init__(**kwargs)

    def get_options(self):
        """
        By default, returns self.option_list. Override if you
        need to do instance-specific configuration.
        """
        return self.option_list


class Option(object):
    """
    Stores positional and optional arguments for `ArgumentParser.add_argument
    <http://argparse.googlecode.com/svn/trunk/doc/add_argument.html>`_.

    :param name_or_flags: Either a name or a list of option strings,
                          e.g. foo or -f, --foo
    :param action: The basic type of action to be taken when this argument
                   is encountered at the command-line.
    :param nargs: The number of command-line arguments that should be consumed.
    :param const: A constant value required by some action and nargs selections.
    :param default: The value produced if the argument is absent from
                    the command-line.
    :param type: The type to which the command-line arg should be converted.
    :param choices: A container of the allowable values for the argument.
    :param required: Whether or not the command-line option may be omitted
                     (optionals only).
    :param help: A brief description of what the argument does.
    :param metavar: A name for the argument in usage messages.
    :param dest: The name of the attribute to be added to the object
                 returned by parse_args().
    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class Command(object):
    option_list = ()
    help_args = None

    def __init__(self, func=None):
        if func is None:
            if not self.option_list:
                self.option_list = []
            return

        args, varargs, keywords, defaults = inspect.getargspec(func)

        if inspect.ismethod(func):
            args = args[1:]

        options = []

        # first arg is always "app" : ignore

        defaults = defaults or []
        kwargs = dict(zip(*[reversed(l) for l in (args, defaults)]))

        for arg in args:

            if arg in kwargs:

                default = kwargs[arg]

                if isinstance(default, bool):
                    options.append(
                        Option(
                            '-%s' % arg[0],
                            '--%s' % arg,
                            action="store_true",
                            dest=arg,
                            required=False,
                            default=default
                        )
                    )
                else:
                    options.append(
                        Option(
                            '-%s' % arg[0],
                            '--%s' % arg,
                            dest=arg,
                            type=str,
                            required=False,
                            default=default
                        )
                    )

            else:
                options.append(Option(arg, type=str))

        self.run = func
        self.__doc__ = func.__doc__
        self.option_list = options

    @property
    def description(self):
        description = self.__doc__ or ''
        return description.strip()

    def add_option(self, option):
        """
        Adds Option to option list.
        """
        self.option_list.append(option)

    def get_options(self):
        """
        By default, returns self.option_list. Override if you
        need to do instance-specific configuration.
        """
        return self.option_list

    def create_parser(self, *args, **kwargs):
        func_stack = kwargs.pop('func_stack', ())
        parent = kwargs.pop('parent', None)
        parser = argparse.ArgumentParser(*args, add_help=False, **kwargs)
        help_args = self.help_args
        while help_args is None and parent is not None:
            help_args = parent.help_args
            parent = getattr(parent, 'parent', None)

        if help_args:
            from rest_framework.core.script.base import add_help
            add_help(parser, help_args)

        for option in self.get_options():
            if isinstance(option, Group):
                if option.exclusive:
                    group = parser.add_mutually_exclusive_group(
                        required=option.required,
                    )
                else:
                    group = parser.add_argument_group(
                        title=option.title,
                        description=option.description,
                    )
                for opt in option.get_options():
                    group.add_argument(*opt.args, **opt.kwargs)
            else:
                parser.add_argument(*option.args, **option.kwargs)

        parser.set_defaults(func_stack=func_stack + (self,))

        self.parser = parser
        self.parent = parent
        return parser

    def __call__(self, *args, **kwargs):
        if asyncio.iscoroutinefunction(self.run):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.run(*args, **kwargs))
        else:
            return self.run(*args, **kwargs)

    def run(self):
        raise NotImplementedError


class Server(Command):
    help = description = "Start the service"

    def get_options(self):

        options = (
            Option('-host', '--host',
                   dest='host',
                   type=str,
                   help="Application address",
                   default="0.0.0.0"),
            Option('-p', '--port',
                   dest='port',
                   type=int,
                   help="Application port, the default is 5000",
                   default=5000),

        )

        return options

    def run(self, app, host, port, **kwargs):
        app = get_application()
        singnals.app_started.send(self)
        app.run(host=host, port=port)
