# -*- coding: utf-8 -*-
from datetime import datetime
import pytz

from rest_framework.conf import settings

utc = pytz.utc


def now():
    now_time = datetime.now(tz=utc)
    to_zone = pytz.timezone(settings.TIME_ZONE)
    return now_time.astimezone(to_zone)
