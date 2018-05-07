# -*- coding: utf-8 -*-
import re
import os
import io
import sys
import stat
import errno
import shutil
import inspect
import argparse
import asyncio
from os.path import join
from importlib import import_module

import tornado.web
from tornado import template
from tornado.platform.asyncio import AsyncIOMainLoop
from rest_framework import conf
from rest_framework.conf import settings
from rest_framework.core.script.exceptions import CommandError
from rest_framework.core.singnals import app_closed

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


class TemplateMix(object):

    rewrite_template_suffixes = (
        ('.py.tpl', '.py'),
    )
    # 需要解析模板文件渲染参数的文件
    extra_files = ("settings.py.tpl", )
    stdout = sys.stdout
    stderr = sys.stderr

    def create(self, app_or_project, name, target=None, **options):
        self.validate_name(name)
        # 如果目标目录没有指定，则在当前目录下加项目名创建
        if target is None:
            top_dir = join(os.getcwd(), name)
            try:
                os.makedirs(top_dir)
            except OSError as e:
                raise CommandError("The directory ('%s') already exists" % top_dir
                                   if e.errno == errno.EEXIST else e)
        else:
            top_dir = os.path.abspath(os.path.expanduser(target))

        if not os.path.exists(top_dir):
            raise CommandError("The directory ('%s') does not exist. Please create this directory "
                               "first" % top_dir)

        template_dir = join(conf.__path__[0], 'templates', app_or_project)
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
                    self.stderr.write(
                        "Can not set permissions on %s, check file system settings." % new_path
                    )

    @staticmethod
    def validate_name(name):
        if name is None:
            raise CommandError("Project (or application) name can not be empty")

        if not PATTERN.match(name):
            raise CommandError("The project (or application) name must consist of a letter"
                               " or underscore, but the beginning or end must be a letter")

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


class Server(Command):
    help = description = "Start the service"

    def get_options(self):

        options = (

            Option('-p', '--port',
                   dest='port',
                   type=int,
                   help="Application port, the default is 5000",
                   default=5000),

            Option('-d', '--debug',
                   action='store_true',
                   help="Whether to start the debug mode",
                   default=None),

            Option('-s', '--settings',
                   type=str,
                   dest="settings",
                   help=(
                       'The Python path to a settings module, e.g. '
                       '"myproject.settings.main". If this isn\'t provided, the '
                       'TORNADO_REST_SETTINGS_MODULE environment variable will be used.'
                   )),

            Option("-r", "--rules", dest="rules", type=str,
                   help='Specifies mappings between URLs and handlers'),

        )

        return options

    def url_patterns(self, rules):
        urlconf_module = settings.ROOT_URLCONF if rules is None else rules
        if isinstance(urlconf_module, str):
            urlconf_module = import_module(urlconf_module)

        urlpatterns = getattr(urlconf_module, 'urlpatterns', [])

        url_specs = []
        for url_spec in urlpatterns:
            if isinstance(url_spec, list):
                url_specs.extend(url_spec)
            else:
                url_specs.append(url_spec)

        return url_specs

    def run(self, app, port, **kwargs):
        """
        :param app: 应用对象，目前为None
        :param port:
        :return:
        """
        settings_path = kwargs.get("settings", None)
        if settings_path:
            os.environ['TORNADO_REST_SETTINGS_MODULE'] = settings_path

        rules = kwargs.get("rules", None)
        urlpatterns = self.url_patterns(rules)
        app_settings = dict(
            gzip=True,
            debug=settings.DEBUG,
            xsrf_cookies=settings.XSRF_COOKIES
        )

        debug = kwargs.pop("debug", None)
        if debug is not None:
            app_settings["debug"] = debug

        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass

        AsyncIOMainLoop().install()
        loop = asyncio.get_event_loop()
        app = tornado.web.Application(urlpatterns, **app_settings)
        # xheaders 设为true,是获得设置代理也能获得客户端真正IP
        app.listen(port, xheaders=True)
        print("http://0.0.0.0:{port}".format(port=port))
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            sys.stderr.flush()
        finally:
            app_closed.send(self)
            loop.stop()
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


class StartProject(Command, TemplateMix):
    """
    必须给一个项目名在当前目录中或指定目录中创建，如果没有指定目录，则在当前目录下加项目名创建
    """
    help = "Create a project"
    description = ("Creates a project directory structure for the given project "
                   "name in the current directory or optionally in the given directory.")

    def get_options(self):

        options = (

            Option('-n', '--name',
                   dest='project_name',
                   type=str,
                   help="Project name",
                   default=""),

            Option('-d', '--directory',
                   dest='target',
                   nargs='?',
                   help="Optional destination directory"),
        )

        return options

    def run(self, app, project_name, target):
        # project_name, target = options.pop('name'), options.pop('directory')
        self.validate_name(project_name)
        try:
            import_module(project_name)
        except ImportError:
            pass
        else:
            raise CommandError(
                "{name} conflicts with the name of an existing Python module and cannot be used "
                "as a project name. Please try another name.".format(name=project_name)
            )

        options = dict(project_name=project_name)
        return self.create('project', project_name, target, **options)

