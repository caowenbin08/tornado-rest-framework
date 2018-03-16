# -*- coding: utf-8 -*-
from collections import namedtuple

from rest_framework import forms


class Lookup(namedtuple('Lookup', ('value', 'lookup_type'))):
    def __len__(self):
        if not self.value:
            return 0


class RangeField(forms.MultiValueField):

    def __init__(self, fields=None, *args, **kwargs):
        if fields is None:
            fields = (forms.DecimalField(), forms.DecimalField())

        kwargs.setdefault("required", False)
        super(RangeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            return slice(*data_list)
        return None


class DateRangeField(RangeField):

    def __init__(self, *args, **kwargs):
        fields = (forms.DateField(), forms.DateField())
        super(DateRangeField, self).__init__(fields, *args, **kwargs)


class DateTimeRangeField(RangeField):

    def __init__(self, *args, **kwargs):
        fields = (forms.DateTimeField(), forms.DateTimeField())
        super(DateTimeRangeField, self).__init__(fields, *args, **kwargs)


class TimeRangeField(RangeField):

    def __init__(self, *args, **kwargs):
        fields = (forms.TimeField(), forms.TimeField())
        super(TimeRangeField, self).__init__(fields, *args, **kwargs)
