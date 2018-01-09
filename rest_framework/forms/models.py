# -*- coding: utf-8 -*-
from collections import OrderedDict

from rest_framework.core.db import models
from rest_framework.core.translation import gettext as _
from rest_framework.core.exceptions import ValidationError, FieldError, ImproperlyConfigured
from rest_framework.forms.fields import (
    CharField, DateTimeField, IntegerField, BooleanField, FloatField, DateField,
    TimeField, UUIDField, ChoiceField,
)
from rest_framework.forms.validators import UniqueTogetherValidator, UniqueValidator
from rest_framework.forms.forms import DeclarativeFieldsMetaclass, BaseForm
from rest_framework.utils.constants import ALL_FIELDS

__author__ = 'caowenbin'

__all__ = ('ModelForm', 'BaseModelForm')

MODEL_FORM_FIELD_MAPPINGS = {
    models.CharField: CharField,
    models.FixedCharField: CharField,
    models.TextField: CharField,
    models.DateTimeField: DateTimeField,
    models.IntegerField: IntegerField,
    models.BooleanField: BooleanField,
    models.FloatField: FloatField,
    models.DoubleField: FloatField,
    models.BigIntegerField: IntegerField,
    models.SmallIntegerField: IntegerField,
    models.PrimaryKeyField: IntegerField,
    models.ForeignKeyField: IntegerField,
    models.DateField: DateField,
    models.TimeField: TimeField,
    models.TimestampField: IntegerField,
    models.UUIDField: UUIDField,
}
FORM_CHOICE_FIELD = ChoiceField


def get_form_field(model_field, **kwargs):
    defaults = {
        'required': not (model_field.default is not None or model_field.null),
        'default': model_field.default,
        'null': model_field.null
    }

    if isinstance(model_field, models.PrimaryKeyField):
        defaults['disabled'] = True

    max_length = getattr(model_field, 'max_length', None)
    if max_length is not None and isinstance(model_field, (models.CharField, models.TextField)):
        defaults['max_length'] = max_length

    if getattr(model_field, 'unique', False):
        error_messages = kwargs.get("error_messages", {})
        unique_error_message = error_messages.get('unique', None)
        if unique_error_message:
            name = model_field.verbose_name if model_field.verbose_name else model_field.name
            unique_error_message = unique_error_message.format(name)

        validator = UniqueValidator(
            queryset=model_field.model_class.select(),
            message=unique_error_message)
        defaults['validators'] = [validator]

    choices = model_field.choices
    form_class = None
    if choices:
        defaults['choices'] = choices
        form_class = FORM_CHOICE_FIELD

    defaults.update(kwargs)
    if form_class is None:
        form_class = MODEL_FORM_FIELD_MAPPINGS.get(model_field.__class__, CharField)

    return form_class(**defaults)


def fields_for_model(model, fields=None, exclude=None, extra_kwargs=None, error_messages=None):
    """
    根据model字段转化为form字段
    :param model:
    :param fields:
    :param exclude:
    :param extra_kwargs:
    :param error_messages:
    :return:
    """
    opts = model._meta
    model_fields = opts.fields
    field_dict = OrderedDict()
    for field_name, field in model_fields.items():
        if fields is not None and field_name not in fields:
            continue
        if exclude and field_name in exclude:
            continue

        kwargs = extra_kwargs.get(field_name, {}) if extra_kwargs else {}
        if error_messages and field_name in error_messages:
            kwargs['error_messages'] = error_messages[field_name]

        field_dict[field_name] = get_form_field(field, **kwargs)
    return field_dict


class ModelFormOptions(object):
    def __init__(self, options=None):
        self.model = getattr(options, 'model', None)
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)
        self.extra_kwargs = getattr(options, 'extra_kwargs', None)
        self.error_messages = getattr(options, 'error_messages', None)


class ModelFormMetaclass(DeclarativeFieldsMetaclass):

    def __new__(mcs, name, bases, attrs):
        new_class = super(ModelFormMetaclass, mcs).__new__(mcs, name, bases, attrs)

        if bases == (BaseModelForm,):
            return new_class

        opts = new_class._meta = ModelFormOptions(getattr(new_class, 'Meta', None))

        if opts.model:
            # If a model is defined, extract form fields from it.
            if opts.fields is None and opts.exclude is None:
                raise ImproperlyConfigured(
                    "Creating a ModelForm without either the 'fields' attribute "
                    "or the 'exclude' attribute is prohibited; form %s "
                    "needs updating." % name
                )

            if opts.fields == ALL_FIELDS:
                opts.fields = None

            fields = fields_for_model(
                model=opts.model,
                fields=opts.fields,
                exclude=opts.exclude,
                extra_kwargs=opts.extra_kwargs,
                error_messages=opts.error_messages
            )

            # make sure opts.fields doesn't specify an invalid field
            none_model_fields = [k for k, v in fields.items() if not v]
            missing_fields = (set(none_model_fields) - set(new_class.declared_fields.keys()))
            if missing_fields:
                message = 'Unknown field(s) (%s) specified for %s'
                message = message % ', '.join(missing_fields), opts.model.__name__
                raise FieldError(message)
            # Override default model fields with any custom declared ones
            # (plus, include all the other declared fields).
            fields.update(new_class.declared_fields)
        else:
            fields = new_class.declared_fields

        new_class.base_fields = fields

        return new_class


class BaseModelForm(BaseForm):
    def __init__(self, request=None, data=None, files=None, initial=None, empty_permitted=False,
                 instance=None):
        opts = self._meta
        if opts.model is None:
            raise ValueError('ModelForm has no model class specified.')

        if instance is None:
            self.instance = opts.model()
            object_data = {}
        else:
            self.instance = instance
            object_data = self.model_to_dict()

        if initial is not None:
            object_data.update(initial)

        super(BaseModelForm, self).__init__(
            request=request,
            data=data,
            files=files,
            initial=object_data,
            empty_permitted=empty_permitted
        )

    def model_to_dict(self):
        opts = self.instance._meta
        model_fields = opts.fields
        data = {}
        fields, exclude = self._meta.fields, self._meta.exclude
        for field_name, field in model_fields.items():
            if fields and field_name not in fields:
                continue
            if exclude and field_name in exclude:
                continue
            data[field_name] = getattr(self.instance, field_name)
        return data

    @property
    def validators(self):
        indexes = getattr(getattr(self.Meta.model, "_meta", None), "indexes", [])
        model_unique_together_list = (index[0] for index in indexes if index[1] is True)
        field_names = {f.source for f in self.fields.values() if (f.source != '*')
                       and ('.' not in f.source)}
        validators = []
        for unique_together in model_unique_together_list:
            if field_names.issuperset(unique_together):
                validator = UniqueTogetherValidator(
                    queryset=self.Meta.model.select(),
                    fields=unique_together
                )
                validators.append(validator)
        form_validators = getattr(getattr(self, 'Meta', None), 'validators', [])
        validators.extend(form_validators)
        return validators

    def create(self, validated_data):
        model_class = self.Meta.model
        instance = model_class.create(**validated_data)
        return instance

    def update(self, validated_data):
        """
        修改
        :param validated_data:
        :return:
        """
        for attr, value in validated_data.items():
            setattr(self.instance, attr, value)
        self.instance.save()

        return self.instance

    def save(self, **kwargs):
        """
        保存或变更请求
        :param kwargs:
        :return:
        """
        if not self.is_valid():
            raise ValidationError(message=_("The form has errors"))

        validated_data = dict(list(self.cleaned_data.items()) + list(kwargs.items()))

        if self.instance is not None:
            self.instance = self.update(validated_data)
            assert self.instance is not None, '`update()` did not return an object instance.'

        else:
            self.instance = self.create(validated_data)
            assert self.instance is not None, '`create()` did not return an object instance.'

        return self.instance


class ModelForm(BaseModelForm, metaclass=ModelFormMetaclass):
    pass
