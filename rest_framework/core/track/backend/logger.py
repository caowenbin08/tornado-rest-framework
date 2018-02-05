# -*- coding: utf-8 -*-
from rest_framework.conf import settings
from datetime import datetime
from datetime import date
import json

from pytz import timezone

from rest_framework.core.logger import get_logger

MAX_EVENT_SIZE = 1024  # 1 KB


class Backend(object):
    """
    Event tracker backend that uses a python logger.

    Events are logged to the INFO level as JSON strings.
    """

    def __init__(self, **kwargs):
        """
        Event tracker backend that uses a python logger.

        `name` is an identifier for the logger, which should have
            been configured using the default python mechanisms.
        """
        logger_name = kwargs.pop('name', None)
        log_file = kwargs.pop('log_file', None)
        level = kwargs.pop('level', "DEBUG")
        self._logger = get_logger(logger_name, log_file, level, **kwargs)
        self.default_log = getattr(self._logger, level.lower())

    def send(self, event, log_level=None):
        """Send the event to the standard python logger"""
        event_str = json.dumps(event, cls=DateTimeJSONEncoder)
        if log_level is not None:
            self.log = getattr(self._logger, log_level.lower(), self.default_log)
        else:
            self.log = self.default_log
        self.log(event_str)


class DateTimeJSONEncoder(json.JSONEncoder):
    """JSON encoder aware of datetime.datetime and datetime.date objects"""

    def default(self, obj):  # lint-amnesty, pylint: disable=arguments-differ, method-hidden
        """
        Serialize datetime and date objects of iso format.

        datatime objects are converted to UTC.
        """
        if isinstance(obj, datetime):
            if obj.tzinfo is None:
                obj = timezone(settings.TIME_ZONE).localize(obj)
            else:
                obj = obj.astimezone(timezone(settings.TIME_ZONE))
            return obj.isoformat(sep=" ")
        elif isinstance(obj, date):
            return obj.isoformat()

        return super(DateTimeJSONEncoder, self).default(obj)
