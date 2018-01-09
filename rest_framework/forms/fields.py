# -*- coding: utf-8 -*-
import os
import copy
import datetime
import re
import uuid
import logging
import itertools
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit
from decimal import Decimal, DecimalException

from rest_framework.conf import settings
from rest_framework.core.translation import gettext as _
from rest_framework.core import validators
from rest_framework.utils import functional
from rest_framework.utils.lazy import lazy
from rest_framework.utils.transcoder import force_text
from rest_framework.core.safe import hashers
from rest_framework.core.exceptions import ValidationError
from rest_framework.utils.constants import EMPTY_VALUES, FILE_INPUT_CONTRADICTION

__author__ = 'caowenbin'

__all__ = (
    'Field', 'CharField', 'IntegerField',
    'DateField', 'TimeField', 'DateTimeField',
    'EmailField', 'FileField', 'ImageField', 'URLField',
    'BooleanField', 'NullBooleanField', 'ChoiceField', 'MultipleChoiceField',
    'MultiValueField', 'FloatField', 'DecimalField', 'SplitDateTimeField',
    'IPAddressField', 'FilePathField', 'UUIDField', 'PasswordField', 'IdentifierField'
)

rest_log = logging.getLogger("tornado.rest_framework")
empty = object()

REGEX_TYPE = type(re.compile(''))


class Field(object):
    default_validators = []  # Default set of validators
    default_error_messages = {
        'required': _('This field is required'),
        'null': _('This field may not be null.')
    }
    empty_values = list(EMPTY_VALUES)
    creation_counter = 0
    initial = None

    def __init__(self, required=True, verbose_name=None, default=empty, source=None,
                 error_messages=None, null=False, validators=(), disabled=False):
        """

        :param required: 默认情况下，每个 Field 类假定该值是必需的，因此如果您传递一个空值 - None 或空字符串（""），
        则 clean() 将引发 ValidationError 异常
        :param verbose_name: 描述性文本
        :param default: 初始值，即默认值
        :param error_messages: 错误信息
        :param validators:此字段的验证函数列表
        :param null: 值是否可以为None，默认不允许，True代表允许
        :param disabled: disabled 布尔参数设置为 True 时，
        用户篡改了字段的值提交到服务器，它也将被忽略，以支持表单初始数据的值
        """

        self.required = required
        self.verbose_name = verbose_name
        self.default = self.initial if (default is empty) else default
        self.null = null
        self.source = source
        self.disabled = disabled

        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1
        self.field_name = None
        self.parent = None
        messages = {}
        for c in reversed(self.__class__.__mro__):
            messages.update(getattr(c, 'default_error_messages', {}))
        messages.update(error_messages or {})
        self.error_messages = messages

        self.validators = list(itertools.chain(self.default_validators, validators))

        super(Field, self).__init__()

    def value_from_datadict(self, data, files):
        if data is None:
            data = {}

        return data.get(self.field_name, empty)

    def bind(self, field_name, parent):
        """
        Initializes the field name and parent for the field instance.
        Called when a field is added to the parent serializer instance.
        """
        self.field_name = field_name
        self.parent = parent

        # self.source should default to being the same as the field name.
        if self.source is None:
            self.source = field_name

        # self.source_attrs is a list of attributes that need to be looked up
        # when serializing the instance, or populating the validated data.
        if self.source == '*':
            self.source_attrs = []
        else:
            self.source_attrs = self.source.split('.')

    def prepare_value(self, value):
        return value

    def to_python(self, value):
        return value

    def validate(self, value):
        if value is empty and self.required:
            raise ValidationError(self.error_messages["required"], code="required")

        if value in self.empty_values and not self.null:
            raise ValidationError(self.error_messages["null"], code="null")

    def run_validators(self, value):
        if value in self.empty_values:
            return

        for v in self.validators:
            if hasattr(v, 'set_context'):
                v.set_context(self)

            try:
                v(value)
            except ValidationError as e:
                if hasattr(e, 'code') and e.code in self.error_messages:
                    e.message = self.error_messages[e.code]
                raise ValidationError(e)

    def get_customize_data(self, value):
        """
        1、当value为empty时,则处理对应的default，反之不处理default
        2、处理用户自定义的clean_**函数（**为表单字段名）
        :param value:
        :return:
        """
        if value is empty:
            if callable(self.default):
                if hasattr(self.default, 'set_context'):
                    self.default.set_context(self)
                value = self.default()
            else:
                value = self.default

        if hasattr(self, 'clean_%s' % self.field_name):
            customize_method = getattr(self, 'clean_%s' % self.field_name)
            if hasattr(customize_method, 'set_context'):
                customize_method.set_context(self)

            value = customize_method()

        return value

    def clean(self, value):
        """
        Validates the given value and returns its "cleaned" value as an
        appropriate Python object.

        Raises ValidationError for any errors.
        """
        value = self.get_customize_data(value)
        value = self.to_python(value)
        self.validate(value)
        self.run_validators(value)
        return value

    # def bound_data(self, data, initial):
    #     """
    #     Return the value that should be shown for this field on render of a
    #     bound form, given the submitted POST data for the field and the initial
    #     data, if any.
    #
    #     For most fields, this will simply be data; FileFields need to handle it
    #     a bit differently.
    #     """
    #     if self.disabled:
    #         return initial
    #     return data

    def has_changed(self, initial, data):
        """
        has_changed() 方法用于确定字段值是否已从初始值改变。返回 True 或 False
        :param initial:
        :param data:
        :return:
        """
        # Always return False if the field is disabled since self.bound_data
        # always uses the initial value in this case.
        if self.disabled:
            return False
        try:
            data = self.to_python(data)
            if hasattr(self, '_coerce'):
                return self._coerce(data) != self._coerce(initial)
        except ValidationError:
            return True
        # For purposes of seeing whether something has changed, None is
        # the same as an empty string, if the data or initial value we get
        # is None, replace it with ''.
        initial_value = initial if initial is not None else ''
        data_value = data if data is not None else ''
        return initial_value != data_value

    # def get_bound_field(self, form, field_name):
    #     """
    #     获取 Form 的实例和字段的名称。在访问模板中的字段时将使用返回值。很可能它将是 BoundField 的子类的实例。
    #     :param form:
    #     :param field_name:
    #     :return:
    #     """
    #     return BoundField(form, self, field_name)

    def __deepcopy__(self, memo):
        result = copy.copy(self)
        memo[id(self)] = result
        result.validators = self.validators[:]
        return result


class CharField(Field):
    """
    字符串类型
    """
    default_error_messages = {
        'invalid':  _('Not a valid string'),
    }
    initial = ''

    def __init__(self, max_length=None, min_length=None, strip=True, empty_value='', *args, **kwargs):
        self.max_length = max_length
        self.min_length = min_length
        self.strip = strip
        self.empty_value = empty_value
        super(CharField, self).__init__(*args, **kwargs)

        if min_length is not None:
            self.validators.append(validators.MinLengthValidator(int(min_length)))
        if max_length is not None:
            self.validators.append(validators.MaxLengthValidator(int(max_length)))

    def to_python(self, value):
        """
        Returns a Unicode object
        :param value:
        :return:
        """
        if value in self.empty_values:
            return self.empty_value
        value = force_text(value)
        if self.strip:
            value = value.strip()
        return value


class IntegerField(Field):
    default_error_messages = {
        'invalid': _('Enter a whole number'),
    }
    re_decimal = re.compile(r'\.0*\s*$')

    def __init__(self, max_value=None, min_value=None, *args, **kwargs):
        self.max_value, self.min_value = max_value, min_value
        super(IntegerField, self).__init__(*args, **kwargs)

        if max_value is not None:
            self.validators.append(validators.MaxValueValidator(max_value))
        if min_value is not None:
            self.validators.append(validators.MinValueValidator(min_value))

    def to_python(self, value):
        """
        Validates that int() can be called on the input. Returns the result
        of int(). Returns None for empty values.
        """
        value = super(IntegerField, self).to_python(value)
        if value in self.empty_values:
            return None
        try:
            value = int(self.re_decimal.sub('', force_text(value)))
        except (ValueError, TypeError):
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        return value


class FloatField(IntegerField):
    default_error_messages = {
        'invalid': _('Enter a number'),
    }

    def to_python(self, value):
        """
        Validates that float() can be called on the input. Returns the result
        of float(). Returns None for empty values.
        """
        value = super(IntegerField, self).to_python(value)
        if value in self.empty_values:
            return None
        try:
            value = float(value)
        except (ValueError, TypeError):
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        return value

    def validate(self, value):
        super(FloatField, self).validate(value)

        # Check for NaN (which is the only thing not equal to itself) and +/- infinity
        if value != value or value in (Decimal('Inf'), Decimal('-Inf')):
            raise ValidationError(self.error_messages['invalid'], code='invalid')

        return value


class DecimalField(IntegerField):
    default_error_messages = {
        'invalid': _('Enter a number'),
    }

    def __init__(self, max_value=None, min_value=None, max_digits=None, decimal_places=None, *args, **kwargs):
        self.max_digits, self.decimal_places = max_digits, decimal_places
        super(DecimalField, self).__init__(max_value, min_value, *args, **kwargs)
        self.validators.append(validators.DecimalValidator(max_digits, decimal_places))

    def to_python(self, value):
        """
        Validates that the input is a decimal number. Returns a Decimal
        instance. Returns None for empty values. Ensures that there are no more
        than max_digits in the number, and no more than decimal_places digits
        after the decimal point.
        """
        if value in self.empty_values:
            return None
        value = force_text(value).strip()
        try:
            value = Decimal(value)
        except DecimalException:
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        return value

    def validate(self, value):
        super(DecimalField, self).validate(value)
        if value in self.empty_values:
            return
        # Check for NaN, Inf and -Inf values. We can't compare directly for NaN,
        # since it is never equal to itself. However, NaN is the only value that
        # isn't equal to itself, so we can use this to identify NaN
        if value != value or value == Decimal("Inf") or value == Decimal("-Inf"):
            raise ValidationError(self.error_messages['invalid'], code='invalid')


class BaseTemporalField(Field):

    def __init__(self, input_formats=None, *args, **kwargs):
        super(BaseTemporalField, self).__init__(*args, **kwargs)
        if input_formats is not None:
            self.input_formats = input_formats

    def to_python(self, value):
        # Try to coerce the value to unicode.
        unicode_value = force_text(value, strings_only=True)
        if isinstance(unicode_value, str):
            value = unicode_value.strip()
        # If unicode, try to strptime against each input format.
        if isinstance(value, str):
            for format in self.input_formats:
                try:
                    return self.strptime(value, format)
                except (ValueError, TypeError):
                    continue
        raise ValidationError(self.error_messages['invalid'], code='invalid')

    def strptime(self, value, format):
        raise NotImplementedError('Subclasses must define this method.')


def get_format(format_type):
    format_type = force_text(format_type)
    val = getattr(settings, format_type)
    return val


get_format_lazy = lazy(get_format, str, list, tuple)


class DateField(BaseTemporalField):
    input_formats = get_format_lazy('DATE_INPUT_FORMATS')
    default_error_messages = {
        'invalid': _('Enter a valid date'),
    }

    def to_python(self, value):
        """
        Validates that the input can be converted to a date. Returns a Python
        datetime.date object.
        """
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        return super(DateField, self).to_python(value)

    def strptime(self, value, format):
        return datetime.datetime.strptime(force_text(value), format).date()


class TimeField(BaseTemporalField):
    input_formats = get_format_lazy('TIME_INPUT_FORMATS')
    default_error_messages = {
        'invalid': _('Enter a valid time')
    }

    def to_python(self, value):
        """
        Validates that the input can be converted to a time. Returns a Python
        datetime.time object.
        """
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.time):
            return value
        return super(TimeField, self).to_python(value)

    def strptime(self, value, format):
        return datetime.datetime.strptime(force_text(value), format).time()


class DateTimeField(BaseTemporalField):
    input_formats = get_format_lazy('DATETIME_INPUT_FORMATS')
    default_error_messages = {
        'invalid': _('Enter a valid date/time'),
    }

    def to_python(self, value):
        """
        Validates that the input can be converted to a datetime. Returns a
        Python datetime.datetime object.
        """
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            result = datetime.datetime(value.year, value.month, value.day)
            return result
        result = super(DateTimeField, self).to_python(value)
        return result

    def strptime(self, value, format):
        return datetime.datetime.strptime(force_text(value), format)


class EmailField(CharField):
    default_validators = [validators.validate_email]

    def __init__(self, *args, **kwargs):
        super(EmailField, self).__init__(*args, strip=True, **kwargs)


class FileField(Field):
    default_error_messages = {
        'invalid': _("No file was submitted， Check the encoding type on the form"),
        'missing': _("No file was submitted"),
        'empty': _("The submitted file is empty"),
        'max_length': _('Ensure this filename has at most %(max)d character (it has %(length)d)'),
        'contradiction': _('Please either submit a file or check the clear checkbox, not both')
    }

    def __init__(self, *args, **kwargs):
        self.max_length = kwargs.pop('max_length', None)
        self.allow_empty_file = kwargs.pop('allow_empty_file', False)
        super(FileField, self).__init__(*args, **kwargs)

    def to_python(self, data):
        if data in self.empty_values:
            return None

        try:
            file_name = data.name
            file_size = data.size
        except AttributeError:
            raise ValidationError(self.error_messages['invalid'], code='invalid')

        if self.max_length is not None and len(file_name) > self.max_length:
            params = {'max': self.max_length, 'length': len(file_name)}
            raise ValidationError(self.error_messages['max_length'], code='max_length', params=params)
        if not file_name:
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        if not self.allow_empty_file and not file_size:
            raise ValidationError(self.error_messages['empty'], code='empty')

        return data

    def clean(self, data, initial=None):
        # If the widget got contradictory inputs, we raise a validation error
        if data is FILE_INPUT_CONTRADICTION:
            raise ValidationError(self.error_messages['contradiction'], code='contradiction')
        # False means the field value should be cleared; further validation is
        # not needed.
        if data is False:
            if not self.required:
                return False
            # If the field is required, clearing is not possible (the widget
            # shouldn't return False data in that case anyway). False is not
            # in self.empty_value; if a False value makes it this far
            # it should be validated from here on out as None (so it will be
            # caught by the required check).
            data = None
        if not data and initial:
            return initial
        return super(FileField, self).clean(data)

    def bound_data(self, data, initial):
        if data in (None, FILE_INPUT_CONTRADICTION):
            return initial
        return data

    def has_changed(self, initial, data):
        if data is None:
            return False
        return True


class ImageField(FileField):
    default_error_messages = {
        'invalid_image': _(
            "Upload a valid image. The file you uploaded was either not an "
            "image or a corrupted image"
        ),
    }

    def to_python(self, data):
        """
        Checks that the file-upload field data contains a valid image (GIF, JPG,
        PNG, possibly others -- whatever the Python Imaging Library supports).
        """
        f = super(ImageField, self).to_python(data)
        if f is None:
            return None

        from PIL import Image

        # We need to get a file object for Pillow. We might have a path or we might
        # have to read the data into memory.
        if hasattr(data, 'temporary_file_path'):
            file = data.temporary_file_path()
        else:
            if hasattr(data, 'read'):
                file = BytesIO(data.read())
            else:
                file = BytesIO(data['content'])

        try:
            # load() could spot a truncated JPEG, but it loads the entire
            # image in memory, which is a DoS vector. See #3848 and #18520.
            image = Image.open(file)
            # verify() must be called immediately after the constructor.
            image.verify()

            # Annotating so subclasses can reuse it for their own validation
            f.image = image
            # Pillow doesn't detect the MIME type of all formats. In those
            # cases, content_type will be None.
            f.content_type = Image.MIME.get(image.format)
        except Exception:
            raise ValidationError(self.error_messages['invalid_image'],  code='invalid_image')

        if hasattr(f, 'seek') and callable(f.seek):
            f.seek(0)

        return f


class URLField(CharField):
    default_error_messages = {
        'invalid': _('Enter a valid URL'),
    }
    default_validators = [validators.URLValidator()]

    def __init__(self, *args, **kwargs):
        super(URLField, self).__init__(*args, strip=True, **kwargs)

    def to_python(self, value):

        def split_url(url):
            """
            Returns a list of url parts via ``urlparse.urlsplit`` (or raises a
            ``ValidationError`` exception for certain).
            """
            try:
                return list(urlsplit(url))
            except ValueError:
                raise ValidationError(self.error_messages['invalid'], code='invalid')

        value = super(URLField, self).to_python(value)
        if value:
            url_fields = split_url(value)
            if not url_fields[0]:
                # If no URL scheme given, assume http://
                url_fields[0] = 'http'
            if not url_fields[1]:
                # Assume that if no domain is provided, that the path segment
                # contains the domain.
                url_fields[1] = url_fields[2]
                url_fields[2] = ''
                # Rebuild the url_fields list, since the domain segment may now
                # contain the path too.
                url_fields = split_url(urlunsplit(url_fields))
            value = urlunsplit(url_fields)
        return value


class BooleanField(Field):
    default_error_messages = {
        'invalid': _('"{input}" is not a valid boolean')
    }
    initial = False
    TRUE_VALUES = {
        't', 'T',
        'y', 'Y', 'yes', 'YES',
        'true', 'True', 'TRUE',
        'on', 'On', 'ON',
        '1', 1,
        True
    }
    FALSE_VALUES = {
        'f', 'F',
        'n', 'N', 'no', 'NO',
        'false', 'False', 'FALSE',
        'off', 'Off', 'OFF',
        '0', 0, 0.0,
        False
    }

    def to_python(self, value):
        """Returns a Python boolean object."""
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        else:
            raise ValidationError(self.error_messages['invalid'], code='invalid')


class NullBooleanField(BooleanField):
    """
    A field whose valid values are None, True and False. Invalid values are
    cleaned to None.
    """
    default_error_messages = {
        'invalid': _('"{input}" is not a valid boolean')
    }
    initial = None
    TRUE_VALUES = {'t', 'T', 'true', 'True', 'TRUE', '1', 1, True}
    FALSE_VALUES = {'f', 'F', 'false', 'False', 'FALSE', '0', 0, 0.0, False}
    NULL_VALUES = {'n', 'N', 'null', 'Null', 'NULL', '', None}

    def to_python(self, value):
        if value in self.TRUE_VALUES:
            return True
        elif value in self.FALSE_VALUES:
            return False
        elif value in self.NULL_VALUES:
            return None
        else:
            raise ValidationError(self.error_messages['invalid'], code='invalid')


class ChoiceField(Field):
    """
    选项字段类型
    """
    default_error_messages = {
        'invalid_choice': "'{input}' is not in the options ({choices})"
    }

    def __init__(self, choices, *args, **kwargs):
        self.grouped_choices = functional.to_choices_dict(choices)
        self.choices = functional.flatten_choices_dict(self.grouped_choices)
        self.choice_strings_to_values = {force_text(key): key for key in self.choices.keys()}
        super(ChoiceField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        try:
            return self.choice_strings_to_values[force_text(value)]
        except KeyError:
            choices = ', '.join(self.choice_strings_to_values.keys())
            raise ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'choices': choices, "input": value},
            )


class MultipleChoiceField(ChoiceField):
    default_error_messages = {
        'invalid_choice': _('"{input}" is not a valid choice'),
        'invalid_list': _('Enter a list of values'),
    }

    def to_python(self, value):
        if not value:
            return []
        elif not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages['invalid_list'], code='invalid_list')
        return [force_text(val) for val in value]

    def validate(self, value):
        """
        Validates that the input is a list or tuple.
        """
        if self.required and not value:
            raise ValidationError(self.error_messages['required'], code='required')
        # Validate that each value in the value list is in self.choices.
        for val in value:
            if not self.valid_value(val):
                raise ValidationError(
                    self.error_messages['invalid_choice'],
                    code='invalid_choice',
                    params={'input': val},
                )

    def has_changed(self, initial, data):
        if initial is None:
            initial = []
        if data is None:
            data = []
        if len(initial) != len(data):
            return True
        initial_set = set(force_text(value) for value in initial)
        data_set = set(force_text(value) for value in data)
        return data_set != initial_set


class MultiValueField(Field):
    """
    A Field that aggregates the logic of multiple Fields.

    Its clean() method takes a "decompressed" list of values, which are then
    cleaned into a single value according to self.fields. Each value in
    this list is cleaned by the corresponding field -- the first value is
    cleaned by the first field, the second value is cleaned by the second
    field, etc. Once all fields are cleaned, the list of clean values is
    "compressed" into a single value.

    Subclasses should not have to implement clean(). Instead, they must
    implement compress(), which takes a list of valid values and returns a
    "compressed" version of those values -- a single value.

    You'll probably want to use this with MultiWidget.
    """
    default_error_messages = {
        'invalid': _('Enter a list of values'),
        'incomplete': _('Enter a complete value'),
    }

    def __init__(self, fields=(), *args, **kwargs):
        self.require_all_fields = kwargs.pop('require_all_fields', True)
        super(MultiValueField, self).__init__(*args, **kwargs)
        for f in fields:
            f.error_messages.setdefault('incomplete',
                                        self.error_messages['incomplete'])
            if self.require_all_fields:
                # Set 'required' to False on the individual fields, because the
                # required validation will be handled by MultiValueField, not
                # by those individual fields.
                f.required = False
        self.fields = fields

    def __deepcopy__(self, memo):
        result = super(MultiValueField, self).__deepcopy__(memo)
        result.fields = tuple(x.__deepcopy__(memo) for x in self.fields)
        return result

    def validate(self, value):
        pass

    def clean(self, value):
        """
        Validates every value in the given list. A value is validated against
        the corresponding Field in self.fields.

        For example, if this MultiValueField was instantiated with
        fields=(DateField(), TimeField()), clean() would call
        DateField.clean(value[0]) and TimeField.clean(value[1]).
        """
        clean_data = []
        errors = []
        if not value or isinstance(value, (list, tuple)):
            if not value or not [v for v in value if v not in self.empty_values]:
                if self.required:
                    raise ValidationError(self.error_messages['required'], code='required')
                else:
                    return self.compress([])
        else:
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        for i, field in enumerate(self.fields):
            try:
                field_value = value[i]
            except IndexError:
                field_value = None
            if field_value in self.empty_values:
                if self.require_all_fields:
                    # Raise a 'required' error if the MultiValueField is
                    # required and any field is empty.
                    if self.required:
                        raise ValidationError(self.error_messages['required'], code='required')
                elif field.required:
                    # Otherwise, add an 'incomplete' error to the list of
                    # collected errors and skip field cleaning, if a required
                    # field is empty.
                    if field.error_messages['incomplete'] not in errors:
                        errors.append(field.error_messages['incomplete'])
                    continue
            try:
                clean_data.append(field.clean(field_value))
            except ValidationError as e:
                # Collect all validation errors in a single list, which we'll
                # raise at the end of clean(), rather than raising a single
                # exception for the first error we encounter. Skip duplicates.
                errors.extend(m for m in e.error_list if m not in errors)
        if errors:
            raise ValidationError(errors)

        out = self.compress(clean_data)
        self.validate(out)
        self.run_validators(out)
        return out

    def compress(self, data_list):
        """
        Returns a single value for the given list of values. The values can be
        assumed to be valid.

        For example, if this MultiValueField was instantiated with
        fields=(DateField(), TimeField()), this might return a datetime
        object created by combining the date and time in data_list.
        """
        raise NotImplementedError('Subclasses must implement this method.')

    def has_changed(self, initial, data):
        if initial is None:
            initial = ['' for x in range(0, len(data))]
        else:
            if not isinstance(initial, list):
                initial = self.widget.decompress(initial)
        for field, initial, data in zip(self.fields, initial, data):
            try:
                initial = field.to_python(initial)
            except ValidationError:
                return True
            if field.has_changed(initial, data):
                return True
        return False


class FilePathField(ChoiceField):
    def __init__(self, path, match=None, recursive=False, allow_files=True,
                 allow_folders=False, required=True, *args, **kwargs):
        self.path, self.match, self.recursive = path, match, recursive
        self.allow_files, self.allow_folders = allow_files, allow_folders
        super(FilePathField, self).__init__(
            choices=(), required=required, *args, **kwargs
        )

        if self.required:
            self.choices = []
        else:
            self.choices = [("", "---------")]

        if self.match is not None:
            self.match_re = re.compile(self.match)

        if recursive:
            for root, dirs, files in sorted(os.walk(self.path)):
                if self.allow_files:
                    for f in files:
                        if self.match is None or self.match_re.search(f):
                            f = os.path.join(root, f)
                            self.choices.append((f, f.replace(path, "", 1)))
                if self.allow_folders:
                    for f in dirs:
                        if f == '__pycache__':
                            continue
                        if self.match is None or self.match_re.search(f):
                            f = os.path.join(root, f)
                            self.choices.append((f, f.replace(path, "", 1)))
        else:
            try:
                for f in sorted(os.listdir(self.path)):
                    if f == '__pycache__':
                        continue
                    full_file = os.path.join(self.path, f)
                    if (((self.allow_files and os.path.isfile(full_file)) or
                             (self.allow_folders and os.path.isdir(full_file))) and
                            (self.match is None or self.match_re.search(f))):
                        self.choices.append((full_file, f))
            except OSError:
                pass


class SplitDateTimeField(MultiValueField):
    default_error_messages = {
        'invalid_date': _('Enter a valid date'),
        'invalid_time': _('Enter a valid time'),
    }

    def __init__(self, input_date_formats=None, input_time_formats=None, *args, **kwargs):
        errors = self.default_error_messages.copy()
        if 'error_messages' in kwargs:
            errors.update(kwargs['error_messages'])
        localize = kwargs.get('localize', False)
        fields = (
            DateField(input_formats=input_date_formats,
                      error_messages={'invalid': errors['invalid_date']},
                      localize=localize),
            TimeField(input_formats=input_time_formats,
                      error_messages={'invalid': errors['invalid_time']},
                      localize=localize),
        )
        super(SplitDateTimeField, self).__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            # Raise a validation error if time or date is empty
            # (possible if SplitDateTimeField has required=False).
            if data_list[0] in self.empty_values:
                raise ValidationError(self.error_messages['invalid_date'], code='invalid_date')
            if data_list[1] in self.empty_values:
                raise ValidationError(self.error_messages['invalid_time'], code='invalid_time')
            result = datetime.datetime.combine(*data_list)
            return result
        return None


class UUIDField(CharField):
    default_error_messages = {
        'invalid': _('Enter a valid UUID'),
    }

    def prepare_value(self, value):
        if isinstance(value, uuid.UUID):
            return value.hex
        return value

    def to_python(self, value):
        value = super(UUIDField, self).to_python(value)
        if value in self.empty_values:
            return None
        if not isinstance(value, uuid.UUID):
            try:
                value = uuid.UUID(value)
            except ValueError:
                raise ValidationError(self.error_messages['invalid'], code='invalid')
        return value


class IPAddressField(CharField):
    """IP地址字段，包括ipv4或ipv6"""

    default_error_messages = {
        'invalid': 'Enter a valid IPv4 or IPv6 address'
    }

    def __init__(self, protocol='both', *args, **kwargs):
        """
        :param protocol: ip地址类型 both（包括ipv4、ipv6）、ipv4、ipv6
        :param kwargs:
        """
        self.protocol = protocol.lower()
        super(IPAddressField, self).__init__(*args, **kwargs)
        self.validators.append(validators.IPAddressValidator(self.protocol))


class PasswordField(CharField):
    """
    密码字段类型
    """
    default_error_messages = {
        'invalid': _('Please enter a valid password')
    }

    def __init__(self, protection='default', level="number", *args, **kwargs):
        """
        :param protection: 密码加密方式
                           default 默认，取settings PASSWORD_HASHERS的第1个
                           pbkdf2_sha256
                           pbkdf2_sha1
                           argon2
                           bcrypt_sha256
                           bcrypt

        :param level: 密码加密级别
                       number   数字版本，6位数字密码
                       normal   普通版本，6-18位英文数字混合密码
                       high     增强版本，6-18位必须包含大小写字母/数字/符号任意两者组合密码
        :param args:
        :param kwargs:
        """
        if protection != "default":
            assert protection in hashers.get_hashers_by_algorithm().keys(), "protection不正确"
        assert level in ("number", "normal", "high"), "level不正确"
        self.protection = protection.lower()
        self.level = level.lower()
        super(PasswordField, self).__init__(*args, **kwargs)
        self.validators.append(validators.PasswordValidator(self.level))

    def clean(self, value):
        """
        Validates the given value and returns its "cleaned" value as an
        appropriate Python object.

        Raises ValidationError for any errors.
        """
        value = self.to_python(value)
        self.validate(value)
        self.run_validators(value)
        return hashers.make_password(password=value, hasher=self.protection)


class IdentifierField(CharField):
    """
    用户认证字段类型，比如手机登录、邮箱认证
    """
    default_error_messages = {
        'invalid': _("Please enter a valid phone number or email address")
    }

    def __init__(self, protocol='both', *args, **kwargs):
        """
        :param protocol: 注册类型
                         both（包括phone、email）
                         phone 手机注册
                         email 邮箱注册
        :param kwargs:
        """
        self.protocol = protocol.lower()
        assert self.protocol in ("both", "phone", "email"), "`IdentifierField.protocol`不正确"
        super(IdentifierField, self).__init__(*args, **kwargs)
        self.validators.append(validators.IdentifierValidator(self.protocol))
