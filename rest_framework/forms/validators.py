# -*- coding: utf-8 -*-
import asyncio
from rest_framework.core.db import models
from rest_framework.core.exceptions import ValidationError
from rest_framework.core.translation import lazy_translate as _


class UniqueValidator(object):
    """
    model模型字段设置了unique=True，进行唯一索引检查
    """

    message = _("This data already exists")

    def __init__(self, queryset, message=None, lookup='exact'):
        self.queryset = queryset
        self.serializer_field = None
        self.message = message or self.message
        self.lookup = lookup

    def set_context(self, serializer_field):
        """
        This hook is called by the serializer instance,
        prior to the validation call being made.
        """
        # Determine the underlying model field name. This may not be the
        # same as the serializer field name if `source=<>` is set.
        self.field_name = serializer_field.source_attrs[-1]
        # Determine the existing instance, if this is an update operation.
        self.instance = getattr(serializer_field.parent, 'instance', None)

    def filter_queryset(self, value, queryset):
        """
        Filter the queryset to all instances matching the given attribute.
        """
        filter_kwargs = {'%s__%s' % (self.field_name, self.lookup): value}
        return qs_filter(queryset, **filter_kwargs)

    def exclude_current_instance(self, queryset):
        """
        If an instance is being updated, then do not include
        that instance itself as a uniqueness conflict.
        """
        if self.instance is not None:
            pk_field = self.instance._meta.primary_key
            return queryset.exclude(**{pk_field.name: getattr(self.instance, pk_field.name)})
        return queryset

    @asyncio.coroutine
    def __call__(self, value):
        queryset = self.queryset
        queryset = self.filter_queryset(value, queryset)
        queryset = self.exclude_current_instance(queryset)
        if (yield from qs_exists(queryset)):
            raise ValidationError(self.message, code='unique')

    def __repr__(self):
        return '<%s(queryset=%s)>' % (
            self.__class__.__name__,
            str(self.queryset),
        )


async def qs_exists(queryset):
    try:
        qs = queryset.exists()
        if asyncio.iscoroutine(qs):
            return await qs
        return qs
    except (TypeError, ValueError, models.DataError):
        return False


def qs_filter(queryset, **kwargs):
    try:
        return queryset.filter(**kwargs)
    except (TypeError, ValueError, models.DataError):
        if isinstance(queryset, models.SelectQuery):
            return queryset.model_class.noop()
        else:
            return queryset.noop()


class UniqueTogetherValidator(object):
    """
    联合唯一索引校验，主要作用于Model的`Meta.indexes`中定义的唯一索引列表
    """
    message = _("This data already exists")
    missing_message = _('This field is required')

    def __init__(self, queryset, fields, message=None, error_field=None):
        """

        :param queryset:
        :param fields: 用于检查的字段
        :param message: 错误信息
        :param error_field: 错误信息绑定那个字段上，默认取settings.NON_FIELD_ERRORS
        """
        self.queryset = queryset
        self.fields = fields
        self.message = message or self.message
        self.instance = None
        self.error_field = error_field

    def set_context(self, form):
        """
        这个钩子由表单程序实例调用，并在进行验证调用之前
        :param form:
        :return:
        """
        self.instance = getattr(form, 'instance', None)

    def enforce_required_fields(self, req_params):
        if self.instance is not None:
            return

        missing_items = {
            field_name: self.missing_message
            for field_name in self.fields
            if field_name not in req_params
        }
        if missing_items:
            raise ValidationError(missing_items, code='required')

    def filter_queryset(self, req_params, queryset):
        if self.instance is not None:
            for field_name in self.fields:
                if field_name not in req_params:
                    req_params[field_name] = getattr(self.instance, field_name)

        filter_kwargs = {
            field_name: req_params[field_name]
            for field_name in self.fields
        }

        return qs_filter(queryset, **filter_kwargs)

    def exclude_current_instance(self, queryset):
        if self.instance is not None:
            pk = getattr(self.instance, "_meta").primary_key
            return queryset.filter(pk != getattr(self.instance, pk.name))

        return queryset

    @asyncio.coroutine
    def __call__(self, req_params):
        self.enforce_required_fields(req_params)
        queryset = self.queryset
        queryset = self.filter_queryset(req_params, queryset)
        queryset = self.exclude_current_instance(queryset)
        checked_values = [value for field, value in req_params.items() if field in self.fields]

        if None not in checked_values and (yield from qs_exists(queryset)):
            raise ValidationError(self.message, code='unique', field=self.error_field)

    def __repr__(self):
        return '<%s(queryset=%s, fields=%s)>' % (
            self.__class__.__name__,
            str(self.queryset),
            str(self.fields)
        )
