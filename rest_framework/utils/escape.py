# -*- coding: utf-8 -*-
import ujson as json

from rest_framework.utils.transcoder import force_text


def json_encode(value):
    return json.dumps(value).replace("</", "<\\/")


def json_decode(value):
    return json.loads(force_text(value))
