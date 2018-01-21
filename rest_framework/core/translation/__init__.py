# -*- coding: utf-8 -*-
import os
from gettext import NullTranslations

import rest_framework
from rest_framework.conf import settings
from rest_framework.core.translation.locale import load_gettext_translations
from rest_framework.utils.lazy import LazyString

LOAD_LANGUAGE = 0


def translation_directories():
    directories = [os.path.join(rest_framework.__path__[0], "translations")] + settings.LANGUAGE_PATHS

    for path in directories:
        if os.path.isabs(path):
            yield path
        else:
            yield os.path.join(os.getcwd(), path)


def get_translations():
    global LOAD_LANGUAGE
    setting_module = settings.SETTINGS_MODULE
    if LOAD_LANGUAGE == 0 or (LOAD_LANGUAGE == 1 and setting_module is not None):
        for directory in translation_directories():
            if not os.path.isdir(directory):
                continue
            load_gettext_translations(directory)
        LOAD_LANGUAGE += 1
    t = locale.get(settings.LANGUAGE_CODE).translations
    return None if isinstance(t, NullTranslations) else t


def gettext(string, **variables):
    """
    例子：
        gettext(u'Hello World!')
        gettext(u'Hello %(name)s!', name='World')
    :param string:
    :param variables:
    :return:
    """
    t = get_translations()
    if t is None:
        return string if not variables else string % variables
    s = t.ugettext(string)
    return s if not variables else s % variables
_ = gettext


def ngettext(singular, plural, num, **variables):
    """
    例子：ngettext(u'%(num)d Apple', u'%(num)d Apples', num=len(apples))
    :param singular:
    :param plural:
    :param num:
    :param variables:
    :return:
    """
    variables.setdefault('num', num)
    t = get_translations()
    if t is None:
        s = singular if num == 1 else plural
        return s if not variables else s % variables

    s = t.ungettext(singular, plural, num)
    return s if not variables else s % variables


def pgettext(context, string, **variables):
    t = get_translations()
    if t is None:
        return string if not variables else string % variables
    s = t.upgettext(context, string)
    return s if not variables else s % variables


def npgettext(context, singular, plural, num, **variables):
    variables.setdefault('num', num)
    t = get_translations()
    if t is None:
        s = singular if num == 1 else plural
        return s if not variables else s % variables
    s = t.unpgettext(context, singular, plural, num)
    return s if not variables else s % variables


def lazy_gettext(string, **variables):
    return LazyString(gettext, string, **variables)


def lazy_ngettext(singular, plural, number=None):
    return LazyString(ngettext, singular, plural, number)


def lazy_pgettext(context, string, **variables):
    return LazyString(pgettext, context, string, **variables)


def is_lazy_string(obj):
    return isinstance(obj, LazyString)


def make_lazy_gettext(lookup_func):
    def lazy_gettext_hanld(text_string, *args, **kwargs):
        if isinstance(text_string, LazyString):
            return text_string
        return LazyString(lookup_func(), text_string, *args, **kwargs)
    return lazy_gettext_hanld
