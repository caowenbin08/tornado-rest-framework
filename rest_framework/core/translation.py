# -*- coding: utf-8 -*-
import os
import logging
from babel import support, Locale

import rest_framework
from rest_framework.conf import settings

logger = logging.getLogger(__name__)
_translations = {}
_caches = {}
_locale_caches = {}


class LazyString:
    def __init__(self, func, string, **kwargs):
        self._func = func
        self._string = string
        self._kwargs = kwargs

    def __getattr__(self, attr):
        if attr == "__setstate__":
            raise AttributeError(attr)
        string = str(self)
        if hasattr(string, attr):
            return getattr(string, attr)
        raise AttributeError(attr)

    def __json__(self):
        global _caches
        k = hash((babel.locale, self._string))
        v = _caches.get(k, None)
        if v is None:
            v = '"%s"' % str(self)
            _caches[k] = v
        return v

    def __repr__(self):
        return "l'{0}'".format(str(self))

    def __str__(self):
        return str(self._func(self._string, **self._kwargs))

    def __len__(self):
        return len(str(self))

    def __getitem__(self, key):
        return str(self)[key]

    def __iter__(self):
        yield str(self)

    def __contains__(self, item):
        return item in str(self)

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)

    def __mul__(self, other):
        return str(self) * other

    def __rmul__(self, other):
        return other * str(self)

    def __lt__(self, other):
        return str(self) < other

    def __le__(self, other):
        return str(self) <= other

    def __eq__(self, other):
        return str(self) == other

    def __ne__(self, other):
        return str(self) != other

    def __gt__(self, other):
        return str(self) > other

    def __ge__(self, other):
        return str(self) >= other

    def __html__(self):
        return str(self)

    def __hash__(self):
        return hash(str(self))

    def __mod__(self, other):
        return str(self) % other

    def __rmod__(self, other):
        return other + str(self)


class Babel:

    _default_language_code = "en_US"
    _default_domain = "messages"
    _cache = {}

    def __init__(self):
        self._locale = None

    def gen_locale(self, language_code):
        lang = language_code.lower()
        lang = lang.replace("-", "_")
        try:
            locale = _locale_caches.setdefault(lang, Locale.parse(lang))
        except:
            lang = settings.LANGUAGE_CODE or self._default_language_code
            locale = _locale_caches.setdefault(lang, Locale.parse(lang))

        return locale

    def list_translations(self):
        result = []

        for dirname in self.translation_directories:
            if not os.path.isdir(dirname):
                continue

            for folder in os.listdir(dirname):
                locale_dir = os.path.join(dirname, folder, 'LC_MESSAGES')
                if not os.path.isdir(locale_dir):
                    continue

                if filter(lambda x: x.endswith('.mo'), os.listdir(locale_dir)):
                    locale = self.gen_locale(folder)
                    result.append(locale)

        if not result:
            result.append(self.default_locale)

        return result

    @property
    def default_locale(self):
        lang = settings.LANGUAGE_CODE or self._default_language_code
        locale = self.gen_locale(lang)
        return locale

    @property
    def domain(self):
        return settings.LANGUAGE_DOMAIN or self._default_domain

    @property
    def translation_directories(self):
        directories = [os.path.join(rest_framework.__path__[0], "translations")] + \
                      settings.LANGUAGE_PATHS
        for path in directories:
            if os.path.isabs(path):
                yield path
            else:
                yield os.path.join(os.getcwd(), path)

    @property
    def locale(self):
        if self._locale is None:
            self._locale = self.default_locale

        return self._locale

    @property
    def translation(self):
        if not _translations:
            return None

        return _translations.get(self.locale, None)

    def load_translations(self, *args, **kwargs):
        global _translations
        global _locale_caches
        for directory in self.translation_directories:
            if not os.path.exists(directory):
                continue

            for lang in os.listdir(directory):
                if lang.startswith('.'):
                    continue
                if os.path.isfile(os.path.join(directory, lang)):
                    continue
                try:
                    translation = support.Translations.load(directory, [lang], self.domain)
                    locale = self.gen_locale(lang)
                    if locale in _translations:
                        _translations[locale].merge(translation)
                    else:
                        _translations[locale] = translation

                except Exception as e:
                    logger.error("Cannot load translation for '%s': %s", lang, str(e))
                    continue

babel = Babel()


def lazy_translate(string, **variables):
    return LazyString(translate, string, **variables)


def translate(string, **variables):
    t = babel.translation
    if t is None:
        return string if not variables else string % variables
    s = t.ugettext(string)
    return s if not variables else s % variables
