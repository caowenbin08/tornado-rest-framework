# -*- coding: utf-8 -*-
from contextlib import contextmanager
from datetime import datetime
from pytz import timezone
from importlib import import_module

from rest_framework.conf import settings
from rest_framework.core.exceptions import ImproperlyConfigured
from rest_framework.core.track.locator import DefaultContextLocator
from rest_framework.utils.functional import import_object

__author__ = 'caowenbin'
DEFAULT_TRACKER_NAME = 'default'
UNKNOWN_EVENT_TYPE = 'unknown'


class Tracker(object):
    def __init__(self, tracker_options):
        self._tracker_options = tracker_options
        self._backend = None
        self.context_locator = None
        self.load_backend()
        self.load_context_locator()

    @property
    def located_context(self):
        """
        The thread local context for this tracker.
        """
        return self.context_locator.get()

    def emit(self, name=None, data=None, log_level=None):
        """
        Emit an event annotated with the UTC time when this function was called.

        `name` is a unique identification string for an event that has
            already been registered.
        `data` is a dictionary mapping field names to the value to include in the event.
            Note that all values provided must be serializable.

        """
        event = {
            'name': name or UNKNOWN_EVENT_TYPE,
            'timestamp': datetime.now(timezone(settings.TIME_ZONE)),
            'data': data or {},
            'context': self.resolve_context()
        }
        self._backend.send(event, log_level)

    def resolve_context(self):
        """
        Create a new dictionary that corresponds to the union of all of the
        contexts that have been entered but not exited at this point.
        """
        merged = dict()
        for context in self.located_context.values():
            merged.update(context)
        return merged

    def enter_context(self, name, ctx):
        """
        Enter a named context.  Any events emitted after calling this
        method will contain all of the key-value pairs included in `ctx`
        unless overridden by a context that is entered after this call.
        """
        self.located_context[name] = ctx

    def exit_context(self, name):
        """
        Exit a named context.  This will remove all key-value pairs
        associated with this context from any events emitted after it
        is removed.
        """
        del self.located_context[name]

    @contextmanager
    def context(self, name, ctx):
        """
        Execute the block with the given context applied.  This manager
        ensures that the context is removed even if an exception is raised
        within the context.
        """
        self.enter_context(name, ctx)
        try:
            yield
        finally:
            self.exit_context(name)

    def load_context_locator(self):
        locator = self._tracker_options.get("LOCATOR", DefaultContextLocator)
        self.context_locator = import_object(locator)()

    def load_backend(self):
        engine = self._tracker_options['ENGINE']
        try:
            module = import_module(engine)
            options = self._tracker_options.get('OPTIONS', {})
            options["name"] = self._tracker_options['NAME']
            backend_instance = module.Backend(**options)
            if not hasattr(backend_instance, 'send') or not callable(backend_instance.send):
                raise ValueError('%s class does not have a callable "send" method.' % engine)
            self._backend = backend_instance
        except (ValueError, AttributeError, TypeError, ImportError) as e:
            raise ImproperlyConfigured("%s isn't an available track backend."
                                       "\nError was: %s" % (engine, e))


TRACKERS = {}


def register_tracker(tracker_name, tracker):
    global TRACKERS
    TRACKERS[tracker_name] = tracker


def load_trackers():
    _tracker_settings = settings.LOG_TRACKERS
    if DEFAULT_TRACKER_NAME not in _tracker_settings:
        raise ImproperlyConfigured("You must define a '%s' tracker" % DEFAULT_TRACKER_NAME)

    for tracker_name, tracker_options in _tracker_settings.items():
        tracker_options["NAME"] = tracker_name
        register_tracker(tracker_name, Tracker(tracker_options))

load_trackers()

trackers = TRACKERS
tracker = TRACKERS[DEFAULT_TRACKER_NAME]
