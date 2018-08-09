# -*- coding: utf-8 -*-
"""
命令工具
"""
from rest_framework.core.script.base import Manager
from rest_framework.core.script.db import MigrateCommand
from rest_framework.core.script.secretkey import SecretKeyCommand
from rest_framework.core.script.cli import prompt, prompt_pass, prompt_bool, prompt_choices

__all__ = [
    "manager",
    "Command",
    "Server",
    "StartProject",
    "Manager",
    "Group",
    "Option",
    "prompt",
    "prompt_pass",
    "prompt_bool",
    "prompt_choices"
]

manager = Manager()


def execute_from_command_line(commands=None):
    manager.run(commands)


manager.add_command('secretkey', SecretKeyCommand)
manager.add_command('db', MigrateCommand)