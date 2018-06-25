# -*- coding: utf-8 -*-
import asyncio
import inspect
import re
import pytz
import uuid
import copy
import logging
import datetime
import itertools
import collections
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit
from decimal import Decimal, DecimalException

from rest_framework.conf import settings
from rest_framework.core.translation import lazy_translate as _
from rest_framework.core import validators
from rest_framework.forms.formsets import formset_factory
from rest_framework.utils import functional
from rest_framework.utils.cached_property import cached_property
from rest_framework.utils.lazy import lazy
from rest_framework.utils.transcoder import force_text
from rest_framework.core.safe import hashers
from rest_framework.core.exceptions import ValidationError
from rest_framework.utils.constants import EMPTY_VALUES, FILE_INPUT_CONTRADICTION, empty


__all__ = (
    'Field', 'CharField', 'IntegerField', 'FloatField', 'DecimalField',
    'DateField', 'TimeField', 'DateTimeField',
    'EmailField', 'FileField', 'ImageField', 'URLField',
    'BooleanField', 'NullBooleanField',
    'ChoiceField', 'MultipleChoiceField', 'MultiValueField', "ListField", 'DictField',
    'IPAddressField', 'UUIDField', 'PasswordField', 'IdentifierField',
    "BoundField", "FormModelField"
)

rest_log = logging.getLogger("tornado.rest_framework")

NOT_DISABLED_REQUIRED = 'May not set both `disabled` and `required`'
NOT_REQUIRED_DEFAULT = 'May not set both `required` and `default`'


class Field(object):
    default_validators = []  # Default set of validators
    default_error_messages = {
        'required': _('This field is required'),
        'null': _('This field may not be null')
    }
    empty_values = list(EMPTY_VALUES)
    creation_counter = 0
    initial = None

    def __init__(self, required=None, verbose_name=None, default=empty, initial=empty, source=None,
                 error_messages=None, null=False, validators=(), disabled=False, *args, **kwargs):
        """

        :param required: 默认情况下，每个 Field 类假定该值是必需的，因此如果您传递一个空值 - None 或空字符串（""），
        则 clean() 将引发 ValidationError 异常
        :param verbose_name: 描述性文本
        :param default: 默认值
        :param initial: 初始化值
        :param error_messages: 错误信息
        :param validators:此字段的验证函数列表
        :param null: 值是否可以为None，默认不允许，True代表允许
        :param disabled: disabled 布尔参数设置为 True 时，
        用户篡改了字段的值提交到服务器，它也将被忽略，以支持表单初始数据的值
        """
        if required is None:
            required = default is empty and not disabled

        assert not (disabled and required), NOT_DISABLED_REQUIRED
        assert not (required and default is not empty), NOT_REQUIRED_DEFAULT

        self.required = required
        self.verbose_name = verbose_name
        self.default = default
        self.initial = self.initial if (initial is empty) else initial
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

        if not isinstance(validators, (tuple, list)):
            validators = (validators, )

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

        if self.disabled is False and value in self.empty_values and not self.null:
            raise ValidationError(self.error_messages["null"], code="null")

    async def run_validators(self, value):
        if value in self.empty_values:
            return
        for v in self.validators:
            if hasattr(v, 'set_context'):
                v.set_context(self)

            try:
                ok = v(value)
                if asyncio.iscoroutine(ok):
                    await ok
            except ValidationError as e:
                old_error_code = e.code if hasattr(e, 'code') else None

                if old_error_code in self.error_messages:
                    e.message = self.error_messages[old_error_code]
                raise ValidationError(e, code=old_error_code)

    def get_default(self):
        if callable(self.default):
            if hasattr(self.default, 'set_context'):
                self.default.set_context(self)
            return self.default()
        return self.default

    async def clean(self, value=empty):
        """
        Validates the given value and returns its "cleaned" value as an
        appropriate Python object.

        Raises ValidationError for any errors.
        """
        if getattr(self.parent, "empty_permitted", False) and value is empty:
            return value

        self.validate(value)
        if value is empty:
            return self.get_default()
        value = self.to_python(value)
        await self.run_validators(value)
        return value

    def bound_data(self, data, initial):
        """
        Return the value that should be shown for this field on render of a
        bound form, given the submitted POST data for the field and the initial
        data, if any.

        For most fields, this will simply be data; FileFields need to handle it
        a bit differently.
        """
        if self.disabled:
            return initial
        return data

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

        if data is empty:
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

    def get_bound_field(self, form, field_name):
        """
        获取 Form 的实例和字段的名称。在访问模板中的字段时将使用返回值。很可能它将是 BoundField 的子类的实例。
        :param form:
        :param field_name:
        :return:
        """
        return BoundField(form, self, field_name)

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


def to_utc_timezone(value):
    try:
        from_zone = pytz.timezone(settings.SHOW_TIME_ZONE)
        value = from_zone.localize(value)
        to_zone = pytz.timezone(settings.TIME_ZONE)
        value = value.astimezone(to_zone)
        return value
    except Exception:
        message = _(
            '%(datetime)s couldn\'t be interpreted '
            'in time zone %(current_timezone)s; it '
            'may be ambiguous or it may not exist.'
        )
        params = {'datetime': value, 'current_timezone': settings.TIME_ZONE}
        raise ValidationError(
            message,
            code='ambiguous_timezone',
            params=params,
        )

    return value


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
            return to_utc_timezone(value)
        if isinstance(value, datetime.date):
            result = datetime.datetime(value.year, value.month, value.day)
            return to_utc_timezone(result)
        result = super(DateTimeField, self).to_python(value)
        return to_utc_timezone(result)

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

    async def clean(self, data, initial=None):
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
        if data is empty:
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
        'invalid': _('"%s" is not a valid boolean')
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
            raise ValidationError(self.error_messages['invalid'], code='invalid', params=value)


class NullBooleanField(BooleanField):
    """
    A field whose valid values are None, True and False. Invalid values are
    cleaned to None.
    """
    default_error_messages = {
        'invalid': _('"%s" is not a valid boolean')
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
            raise ValidationError(self.error_messages['invalid'], code='invalid', params=value)


class ChoiceField(Field):
    """
    选项字段类型
    """
    default_error_messages = {
        'invalid_choice': "'%(input)s' is not in the options (%(choices)s)"
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
        'invalid_choice': _('"%(input)s" is not a valid choice'),
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


class _UnvalidatedField(Field):
    pass


class ListField(Field):
    """
    列表字段
    """
    child = _UnvalidatedField()
    initial = []
    default_error_messages = {
        'not_a_list': _('Expected a list of items but got type "%(input_type)s"'),
        'empty': _('This list may not be empty'),
        'min_length': _('Ensure this field has at least {min_length} elements'),
        'max_length': _('Ensure this field has no more than {max_length} elements')
    }

    def __init__(self, child=None, *args, **kwargs):
        self.child = copy.deepcopy(self.child) if child is None else child
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        self.allow_empty = kwargs.pop('allow_empty', True)
        self.max_length = kwargs.pop('max_length', None)
        self.min_length = kwargs.pop('min_length', None)
        self.child.source = None

        super(ListField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

        if self.max_length is not None:
            message = self.error_messages['max_length'].format(max_length=self.max_length)
            self.validators.append(validators.MaxLengthValidator(self.max_length, message=message))
        if self.min_length is not None:
            message = self.error_messages['min_length'].format(min_length=self.min_length)
            self.validators.append(validators.MinLengthValidator(self.min_length, message=message))

    def validate(self, value):
        pass

    async def clean(self, value):
        if value is empty:
            value = []
        elif isinstance(value, type('')) or isinstance(value, collections.Mapping)\
                or not hasattr(value, '__iter__'):
            raise ValidationError(
                self.error_messages['not_a_list'],
                code='not_a_list',
                params=dict(input_type=type(value).__name__)
            )

        if not self.allow_empty and len(value) == 0:
            raise ValidationError(self.error_messages['empty'], code='empty')
        return [await self.child.clean(item) for item in value]


class DictField(Field):
    """
    字典字段
    """
    child = _UnvalidatedField()
    initial = {}
    default_error_messages = {
        'not_a_dict': _('Expected a dictionary of items but got type "%(input_type)s"')
    }

    def __init__(self, *args, **kwargs):
        self.child = kwargs.pop('child', copy.deepcopy(self.child))
        assert not inspect.isclass(self.child), '`child` has not been instantiated.'
        self.child.source = None
        super(DictField, self).__init__(*args, **kwargs)
        self.child.bind(field_name='', parent=self)

    async def clean(self, data):
        if not isinstance(data, dict):
            raise ValidationError(
                self.error_messages['not_a_dict'],
                code='not_a_dict',
                params=dict(input_type=type(data).__name__)
            )

        return {str(key): await self.child.clean(value) for key, value in data.items()}


class MultiValueField(Field):
    """
    多字段组合，例如
    fields=(DateField(), TimeField())
    """
    fields = _UnvalidatedField()

    def __init__(self, fields=None, *args, **kwargs):
        self.require_all_fields = kwargs.pop('require_all_fields', True)
        self.null_all_fields = kwargs.pop('null_all_fields', True)
        fields = (copy.deepcopy(self.fields),) if fields is None else fields if isinstance(
            fields, (tuple, list)) else (fields, )
        self.max_length = kwargs.pop('max_length', None)
        self.min_length = kwargs.pop('min_length', None)
        super(MultiValueField, self).__init__(*args, **kwargs)
        self.fields = fields

    def bind(self, field_name, parent):
        super(MultiValueField, self).bind(field_name, parent)
        for i, f in enumerate(self.fields):
            f.source = None
            field_name = "%s_%s" % (self.field_name, i) if self.field_name else ""
            f.bind(field_name=field_name, parent=self)
            if self.require_all_fields:
                f.required = False
            if self.null_all_fields:
                f.null = True

    def __deepcopy__(self, memo):
        result = super(MultiValueField, self).__deepcopy__(memo)
        result.fields = tuple(x.__deepcopy__(memo) for x in self.fields)
        return result

    def validate(self, value):
        pass

    async def clean(self, form_data, form_files):
        """
        Validates every value in the given list. A value is validated against
        the corresponding Field in self.fields.

        For example, if this MultiValueField was instantiated with
        fields=(DateField(), TimeField()), clean() would call
        DateField.clean(value[0]) and TimeField.clean(value[1]).
        """
        clean_data = []
        errors = {}

        for field in self.fields:
            field_value = field.value_from_datadict(form_data, form_files)
            try:
                field_value = await field.clean(field_value)
                if field_value is empty:
                    continue
                clean_data.append(field_value)
            except ValidationError as e:
                errors[field.field_name] = e.detail

        if errors:
            raise ValidationError(errors)

        if self.required and not clean_data:
            raise ValidationError(self.error_messages['required'], code='required')

        out = self.compress(clean_data)
        self.validate(out)
        await self.run_validators(out)
        return out

    def compress(self, data_list):
        return data_list

    def decompress(self, initial):
        return [initial]

    def has_changed(self, initial, data):
        if getattr(self.parent, "empty_permitted", False) and data is empty:
            return False

        if initial is None:
            initial = ['' for _ in range(0, len(data))]
        else:
            if not isinstance(initial, list):
                initial = self.decompress(initial)

        for field, initial, data in zip(self.fields, initial, data):
            try:
                initial = field.to_python(initial)
            except ValidationError:
                return True

            if field.has_changed(initial, data):
                return True

        return False


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

    def __init__(self, protection='default', level="high", *args, **kwargs):
        """
        :param protection: 密码加密方式
                           default 默认，取settings PASSWORD_HASHERS的第1个
                           pbkdf2_sha256
                           pbkdf2_sha1
                           argon2
                           bcrypt_sha256
                           bcrypt

        :param level: 密码加密级别
                       any      任何版本，不限制
                       number   数字版本，6位数字密码
                       normal   普通版本，6-18位英文数字混合密码
                       high     增强版本，6-18位必须包含大小写字母/数字/符号任意两者组合密码
        :param args:
        :param kwargs:
        """
        if protection != "default":
            assert protection in hashers.get_hashers_by_algorithm().keys(), "protection不正确"
        assert level in ('any', "number", "normal", "high"), "level不正确"
        self.protection = protection.lower()
        self.level = level.lower()
        super(PasswordField, self).__init__(*args, **kwargs)
        self.validators.append(validators.PasswordValidator(self.level))

    async def clean(self, value):
        """
        Validates the given value and returns its "cleaned" value as an
        appropriate Python object.

        Raises ValidationError for any errors.
        """
        value = self.to_python(value)
        self.validate(value)
        await self.run_validators(value)
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


class BoundField(object):
    def __init__(self, form, field, name):
        self.form = form
        self.field = field
        self.name = name

    @property
    def errors(self):
        """
        Returns an ErrorList for this field. Returns an empty ErrorList
        if there are none.
        """
        return self.form.errors.get(self.name, ErrorList())

    @property
    def data(self):
        """
        Returns the data for this BoundField, or None if it wasn't given.
        """
        return self.field.value_from_datadict(self.form.data, self.form.files)

    def value(self):
        """
        Returns the value for this BoundField, using the initial value if
        the form is not bound or the data otherwise.
        """
        data = self.initial
        if self.form.is_bound:
            data = self.field.bound_data(self.data, data)
        return self.field.prepare_value(data)

    @cached_property
    def initial(self):
        data = self.form.get_initial_for_field(self.field, self.name)

        if isinstance(data, (datetime.datetime, datetime.time)):
            data = data.replace(microsecond=0)
        return data


class FormModelField(Field):
    default_error_messages = {
        'type_error': _('Expected a list or dictionary of items but got type "%(input_type)s"'),
        'empty': _('This value not be empty')
    }

    def __init__(self, form, many=True, allow_empty=False, *args, **kwargs):
        self.form_class = formset_factory(form)
        self.many = many
        self.allow_empty = allow_empty
        super(FormModelField, self).__init__(*args, **kwargs)

    def validate(self, value):
        pass

    async def clean(self, value):
        if self.required and value is empty:
            raise ValidationError(self.error_messages['required'], code='required')

        if value is empty:
            value = [] if self.many else {}

        elif not isinstance(value, (dict, list)):
            raise ValidationError(
                self.error_messages['type_error'],
                code='type_error',
                params=dict(input_type=type(value).__name__)
            )

        form_data_size = len(value)
        if self.allow_empty and form_data_size == 0:
            return [] if self.many else {}

        # elif form_data_size == 0:
        #     raise ValidationError(self.error_messages['empty'], code='empty')

        if isinstance(value, dict):
            value = [value]

        form_cls = self.form_class(data=value)
        is_valid = await form_cls.is_valid()

        if is_valid:
            result = await form_cls.cleaned_data
            return result if self.many else result[0]

        errors = await form_cls.errors
        raise ValidationError(errors)


