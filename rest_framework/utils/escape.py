import json

from rest_framework.core.translation import LazyString
from rest_framework.utils import jsonlib, has_ujson
from rest_framework.utils.transcoder import force_text


class LazyStringEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, LazyString):
            return force_text(o)
        else:
            return super().default(o)


def json_encode(value):
    if not has_ujson:
        options = {
            "ensure_ascii": False,
            "allow_nan": False,
            "indent": None,
            "separators": (",", ":"),
            "cls": LazyStringEncoder
        }
        return jsonlib.dumps(value, **options)

    return jsonlib.dumps(value, escape_forward_slashes=False)


def json_decode(value):
    return jsonlib.loads(value)
