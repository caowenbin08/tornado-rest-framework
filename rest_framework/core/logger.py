# -*- coding: utf-8 -*-
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
__author__ = 'caowenbin'

LEVEL_MAPS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARN,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "FATAL": logging.FATAL,
}


def get_logger(logger_name, log_file=None, level='DEBUG', **kwargs):
    logger_ = logging.getLogger(logger_name)
    logger_.propagate = False
    level = level.upper()
    logger_.setLevel(LEVEL_MAPS.get(level, logging.DEBUG))
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(message)s')

    if log_file:
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        when = kwargs.get("when", "1D")
        interval = when[:-1]
        backup_count = int(kwargs.get("backup_count", 0))
        handler = TimedRotatingFileHandler(
            filename=log_file,
            when=when[-1],
            interval=int(interval) if interval else 1,
            backupCount=backup_count
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        logger_.addHandler(handler)

    # 同时输到屏幕，便于实施观察
    handle_for_screen = logging.StreamHandler(sys.stdout)
    handle_for_screen.setFormatter(formatter)
    logger_.addHandler(handle_for_screen)

    return logger_


def add_log_server(logger, server_host, server_port, server_path='/logging', method='GET',
                   level='ERROR'):
    if server_host and server_port:
        http_handler = logging.handlers.HTTPHandler(
            '%s:%s' % (server_host, server_port),
            server_path,
            method=method,
        )
        http_handler.setLevel(LEVEL_MAPS.get(level, logging.ERROR))

        logger.addHandler(http_handler)
