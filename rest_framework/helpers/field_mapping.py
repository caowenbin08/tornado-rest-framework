# -*- coding: utf-8 -*-
import inspect
# import peewee
from rest_framework.db import models
# from django.core import validators
# from django.db import models
# from django.utils.text import capfirst
#
# from rest_framework.compat import DecimalValidator, JSONField
# from rest_framework.validators import UniqueValidator
from rest_framework.validators import UniqueValidator

NUMERIC_FIELD_TYPES = (models.IntegerField, models.FloatField, models.DecimalField)


class ClassLookupDict(object):
    """
    Takes a dictionary with classes as keys.
    Lookups against this object will traverses the object's inheritance
    hierarchy in method resolution order, and returns the first matching value
    from the dictionary or raises a KeyError if nothing matches.
    """
    def __init__(self, mapping):
        self.mapping = mapping

    def __getitem__(self, key):
        if hasattr(key, '_proxy_class'):
            # Deal with proxy classes. Ie. BoundField behaves as if it
            # is a Field instance when using ClassLookupDict.
            base_class = key._proxy_class
        else:
            base_class = key.__class__

        for cls in inspect.getmro(base_class):
            if cls in self.mapping:
                return self.mapping[cls]
        raise KeyError('Class %s not found in lookup.' % base_class.__name__)

    def __setitem__(self, key, value):
        self.mapping[key] = value


def get_field_kwargs(field_name, model_field):
    """
    Creates a default instance of a basic non-relational field.
    """
    kwargs = {}
    validator_kwarg = []

    # 是否必须，False代表非必选项
    if model_field.default is not None or model_field.null:
        kwargs['required'] = False

    kwargs["default"] = model_field.default

    if model_field.null:
        kwargs['null'] = True

    if model_field.choices:
        kwargs['choices'] = model_field.choices

    if isinstance(model_field, models.PrimaryKeyField):
        kwargs['read_only'] = True
        return kwargs

    # rather than as a validator.
    max_length = getattr(model_field, 'max_length', None)
    if max_length is not None and isinstance(model_field, (models.CharField, models.TextField)):
        kwargs['max_length'] = max_length
        # validator_kwarg = [
        #     validator for validator in validator_kwarg
        #     if not isinstance(validator, validators.MaxLengthValidator)
        # ]

    if getattr(model_field, 'unique', False):
        # unique_error_message = model_field.error_messages.get('unique', None)
        # if unique_error_message:
        #     unique_error_message = unique_error_message % {
        #         'model_name': model_field.model._meta.verbose_name,
        #         'field_label': model_field.verbose_name
        #     }
        validator = UniqueValidator(
            queryset=model_field.model._default_manager,
            message="不能重复")
        validator_kwarg.append(validator)

    if validator_kwarg:
        kwargs['validators'] = validator_kwarg

    return kwargs

