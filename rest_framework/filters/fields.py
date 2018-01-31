# -*- coding: utf-8 -*-
from collections import namedtuple


class Lookup(namedtuple('Lookup', ('value', 'lookup_type'))):
    def __len__(self):
        if not self.value:
            return 0
