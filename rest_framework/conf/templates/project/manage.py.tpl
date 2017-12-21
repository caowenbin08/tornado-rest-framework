# -*- coding: utf-8 -*-
import os
from rest_framework.management import execute_from_command_line


if __name__ == "__main__":
    os.environ.setdefault("TORNADO_REST_SETTINGS_MODULE", "settings")
    execute_from_command_line()
