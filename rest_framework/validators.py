# -*- coding: utf-8 -*-
import os
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from rest_framework.db import models
from rest_framework.exceptions import ValidationError
from rest_framework.helpers.encoding import force_text
from rest_framework.helpers.lazy import lazy_re_compile

__author__ = 'caowenbin'


EMPTY_VALUES = (None, '', [], (), {})


class RegexValidator(object):
    """
    正则表达式检查
    """
    regex = ''
    message = "参数不正确"
    code = 'invalid'
    inverse_match = False
    flags = 0

    def __init__(self, regex=None, message=None, code=None, inverse_match=None, flags=None):
        """

        :param regex:
        :param message:
        :param code:
        :param inverse_match: 逆匹配
        :param flags:
        """
        if regex is not None:
            self.regex = regex

        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

        if inverse_match is not None:
            self.inverse_match = inverse_match

        if flags is not None:
            self.flags = flags

        if self.flags and not isinstance(self.regex, str):
            raise TypeError("If the flags are set, regex must be a regular expression string.")

        self.regex = lazy_re_compile(self.regex, self.flags)

    def __call__(self, value):
        if not (self.inverse_match is not bool(self.regex.search(force_text(value)))):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other):
        return (
            isinstance(other, RegexValidator) and
            self.regex.pattern == other.regex.pattern and
            self.regex.flags == other.regex.flags and
            (self.message == other.message) and
            (self.code == other.code) and
            (self.inverse_match == other.inverse_match)
        )

    def __ne__(self, other):
        return not (self == other)


class URLValidator(RegexValidator):
    """
    url 地址判断
    """
    # unicode字母范围(必须是一个unicode字符串,而不是原始的字符串)
    ul = '\u00a1-\uffff'
    ipv4_re = r'(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}'
    ipv6_re = r'\[[0-9a-f:\.]+\]'
    hostname_re = r'[a-z' + ul + r'0-9](?:[a-z' + ul + r'0-9-]{0,61}[a-z' + ul + r'0-9])?'
    domain_re = r'(?:\.(?!-)[a-z' + ul + r'0-9-]{1,63}(?<!-))*'
    tld_re = r'\.(?!-)(?:[a-z' + ul + '-]{2,63}|xn--[a-z0-9]{1,59})(?<!-)\.?'
    host_re = '(' + hostname_re + domain_re + tld_re + '|localhost)'
    regex = lazy_re_compile(
        r'^(?:[a-z0-9\.\-\+]*)://'
        r'(?:\S+(?::\S*)?@)?'
        r'(?:' + ipv4_re + '|' + ipv6_re + '|' + host_re + ')'
        r'(?::\d{2,5})?'
        r'(?:[/?#][^\s]*)?'
        r'\Z', re.IGNORECASE)
    message = "输入一个有效的URL"
    schemes = ['http', 'https', 'ftp', 'ftps']

    def __init__(self, schemes=None, **kwargs):
        super(URLValidator, self).__init__(**kwargs)
        if schemes is not None:
            self.schemes = schemes

    def __call__(self, value):
        value = force_text(value)
        # Check first if the scheme is valid
        scheme = value.split('://')[0].lower()
        if scheme not in self.schemes:
            raise ValidationError(self.message, code=self.code)

        # Then check full URL
        try:
            super(URLValidator, self).__call__(value)
        except ValidationError as e:
            # Trivial case failed. Try for possible IDN domain
            if value:
                try:
                    scheme, netloc, path, query, fragment = urlsplit(value)
                except ValueError:  # for example, "Invalid IPv6 URL"
                    raise ValidationError(self.message, code=self.code)
                try:
                    netloc = netloc.encode('idna').decode('ascii')  # IDN -> ACE
                except UnicodeError:  # invalid domain part
                    raise e
                url = urlunsplit((scheme, netloc, path, query, fragment))
                super(URLValidator, self).__call__(url)
            else:
                raise
        else:
            # Now verify IPv6 in the netloc part
            host_match = re.search(r'^\[(.+)\](?::\d{2,5})?$', urlsplit(value).netloc)
            if host_match:
                potential_ip = host_match.groups()[0]
                if not IPAddressValidator.check_ipv6(potential_ip):
                    raise ValidationError(self.message, code=self.code)

        # 一个完整的主机名的最大长度是253个字符
        if len(urlsplit(value).netloc) > 253:
            raise ValidationError(self.message, code=self.code)


integer_validator = RegexValidator(
    regex=lazy_re_compile(r'^-?\d+\Z'),
    message="输入一个有效的整形值",
    code='invalid'
)


def validate_integer(value):
    return integer_validator(value)


class EmailValidator(object):
    """
    邮箱地址检查
    """
    message = "输入一个有效的电子邮件地址"
    code = 'invalid'
    email_regex = lazy_re_compile(r"^[\w-]+(\.[\w-]+)*@[\w-]+(\.[\w-]+)+$", flags=re.IGNORECASE)

    def __init__(self, message=None, code=None):
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

    def __call__(self, value):
        value = force_text(value)

        if not value or '@' not in value:
            raise ValidationError(self.message, code=self.code)

        if not self.email_regex.match(value):
            raise ValidationError(self.message, code=self.code)

validate_email = EmailValidator()


class IPAddressValidator(object):
    """
    ipv4 或ipv6 地址是否合法
    """

    message = {
        "both": "输入一个有效的ipv4或ipv6地址",
        "ipv4": "输入一个有效的ipv4地址",
        "ipv6": "输入一个有效的ipv6地址"
    }
    code = 'invalid'

    def __init__(self, protocol="both", message=None, code=None):
        self.protocol = protocol
        assert isinstance(message, (type(None), dict)), "message值必须为字典类型"
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

    def __call__(self, value):

        if not value or '\x00' in value:
            raise ValidationError(self.message[self.protocol], code=self.code)

        if self.protocol == "both":
            valid = self.is_valid_ip(value)

        elif self.protocol == "ipv4":
            valid = self.check_ipv4(value)

        elif self.protocol == "ipv6":
            valid = self.check_ipv6(value)

        if not valid:
            raise ValidationError(self.message[self.protocol], code=self.code)

    @classmethod
    def check_ipv4(cls, value):
        parts = value.split('.')

        if len(parts) == 4 and all(x.isdigit() for x in parts):
            numbers = list(int(x) for x in parts)
            return all(0 <= num < 256 for num in numbers)

        return False

    @classmethod
    def check_ipv6(cls, value):
        parts = value.split(':')
        if len(parts) > 8:
            return False

        num_blank = 0
        for part in parts:
            if not part:
                num_blank += 1
            else:
                try:
                    value = int(part, 16)
                except ValueError:
                    return False
                else:
                    if value < 0 or value >= 65536:
                        return False

        if num_blank < 2:
            return True
        elif num_blank == 2 and not parts[0] and not parts[1]:
            return True
        return False

    @classmethod
    def is_valid_ip(cls, ip):
        try:
            res = socket.getaddrinfo(
                host=ip,
                port=0,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=0,
                flags=socket.AI_NUMERICHOST
            )

            return bool(res)
        except socket.gaierror as e:
            if e.args[0] == socket.EAI_NONAME:
                return False
            return False

        return True


def int_list_validator(sep=',', message=None, code='invalid', allow_negative=False):
    regexp = lazy_re_compile(r'^%(neg)s\d+(?:%(sep)s%(neg)s\d+)*\Z' % {
        'neg': '(-)?' if allow_negative else '',
        'sep': re.escape(sep),
    })
    return RegexValidator(regexp, message=message, code=code)


validate_comma_separated_integer_list = int_list_validator(
    message='Enter only digits separated by commas.',
)


class BaseValidator(object):
    """
    校验基础处理类
    """
    message = '请输入参数为{limit_value}，目前是{show_value}.'
    code = 'limit_value'

    def __init__(self, limit_value, message=None):
        self.limit_value = limit_value
        if message:
            self.message = message

    def __call__(self, value):
        cleaned = self.clean(value)
        params = {'limit_value': self.limit_value, 'show_value': cleaned, 'value': value}
        if self.compare(cleaned, self.limit_value):
            raise ValidationError(detail=self.message.format(**params), code=self.code)

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            self.limit_value == other.limit_value and
            self.message == other.message and
            self.code == other.code
        )

    def compare(self, a, b):
        return a is not b

    def clean(self, x):
        return x


class MaxValueValidator(BaseValidator):
    """
    最大值校验
    """
    message = '请输入一个小于或等于{limit_value}值.'
    code = 'max_value'

    def compare(self, a, b):
        return a > b


class MinValueValidator(BaseValidator):
    """
    最小值校验
    """
    message = '请输入一个大于或等于{limit_value}值'
    code = 'min_value'

    def compare(self, a, b):
        return a < b


class MinLengthValidator(BaseValidator):
    """
    字符串最小长度检验
    """

    message = '请输入至少{limit_value}个字符，目前是{show_value}个.'
    code = 'min_length'

    def compare(self, a, b):
        return a < b

    def clean(self, x):
        return len(x)


class MaxLengthValidator(BaseValidator):
    """
    字符串最大长度检验
    """

    message = '最多输入{limit_value}个字符，目前是{show_value}个.'
    code = 'max_length'

    def compare(self, a, b):
        return a > b

    def clean(self, x):
        return len(x)


class DecimalValidator(object):
    """
    金额类型，类似浮点型（float）
    """
    messages = {
        'max_digits': '确保没有超过{max}数字',
        'max_decimal_places': '确保没有超过{max}小数位',
        'max_whole_digits': '确保没有超过{max}小数点前的数字'
    }

    def __init__(self, max_digits, decimal_places):
        self.max_digits = max_digits
        self.decimal_places = decimal_places

    def __call__(self, value):
        digit_tuple, exponent = value.as_tuple()[1:]
        decimals = abs(exponent)
        digits = len(digit_tuple)
        if decimals > digits:
            digits = decimals
        whole_digits = digits - decimals

        if self.max_digits is not None and digits > self.max_digits:
            raise ValidationError(
                detail=self.messages['max_digits'].format(max=self.max_digits),
                code='max_digits'
            )
        if self.decimal_places is not None and decimals > self.decimal_places:
            raise ValidationError(
                detail=self.messages['max_decimal_places'].format(max=self.decimal_places),
                code='max_decimal_places'
            )
        if (self.max_digits is not None and self.decimal_places is not None and
                whole_digits > (self.max_digits - self.decimal_places)):
            raise ValidationError(
                detail=self.messages['max_whole_digits'].format(max=self.decimal_places),
                code='max_whole_digits'
            )

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            self.max_digits == other.max_digits and
            self.decimal_places == other.decimal_places
        )


class FileExtensionValidator(object):
    """
    文件名检验
    """
    message = "文件后缀名'{extension}'不在允许后缀名（'{allowed_extensions}'）之内"
    code = 'invalid_extension'

    def __init__(self, allowed_extensions=None, message=None, code=None):
        self.allowed_extensions = allowed_extensions
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code

    def __call__(self, value):
        extension = os.path.splitext(value.name)[1][1:].lower()
        if self.allowed_extensions is not None and extension not in self.allowed_extensions:
            raise ValidationError(
                detail=self.messages.format(
                    extension=extension,
                    allowed_extensions=', '.join(self.allowed_extensions)
                ),
                code=self.code
            )

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            self.allowed_extensions == other.allowed_extensions and
            self.message == other.message and
            self.code == other.code
        )


class UniqueValidator(object):
    """
    Validator that corresponds to `unique=True` on a model field.

    Should be applied to an individual field on the serializer.
    """
    message = 'This field must be unique.'

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
            return queryset.exclude(pk=self.instance.pk)
        return queryset

    def __call__(self, value):
        queryset = self.queryset
        queryset = self.filter_queryset(value, queryset)
        queryset = self.exclude_current_instance(queryset)
        if qs_exists(queryset):
            raise ValidationError(self.message, code='unique')

    # def __repr__(self):
    #     return '<%s(queryset=%s)>' % (
    #         self.__class__.__name__,
    #         smart_repr(self.queryset)
    #     )


def qs_exists(queryset):
    try:
        return queryset.exists()
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
    message = '资源数据已经存在，可能由字段（{field_names})组成的唯一索引集导致'
    missing_message = "该字段必须输入值"

    def __init__(self, queryset, fields, message=None):
        self.queryset = queryset
        self.fields = fields
        self.message = message or self.message
        self.instance = None

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
            return queryset.filter(getattr(self.instance, "_meta").primary_key != pk.value)

        return queryset

    def __call__(self, req_params):
        self.enforce_required_fields(req_params)
        queryset = self.queryset
        queryset = self.filter_queryset(req_params, queryset)
        queryset = self.exclude_current_instance(queryset)
        checked_values = [value for field, value in req_params.items() if field in self.fields]

        if None not in checked_values and qs_exists(queryset):
            field_names = ', '.join(self.fields)
            message = self.message.format(field_names=field_names)
            raise ValidationError(message, code='unique')

    def __repr__(self):
        return '<%s(queryset=%s, fields=%s)>' % (
            self.__class__.__name__,
            str(self.queryset),
            str(self.fields)
        )


class PasswordValidator(object):
    """
    密码是否合法
    """

    message = {
        "number": "输入一个有效的6位数字密码",
        "char_normal": "输入一个有效的6-18位英文数字混合密码",
        "char_english": "输入一个6-18位必须包含大小写字母/数字/符号任意两者组合密码"
    }
    code = 'invalid'

    def __init__(self, level="number", message=None, code=None):
        self.level = level
        assert isinstance(message, (type(None), dict)), "message值必须为字典类型"
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code
        if self.level == "number":
            self.password_regex = lazy_re_compile(r"^\d{6}$", flags=re.IGNORECASE)
        elif self.level == "char_normal":
            self.password_regex = lazy_re_compile(r"^(?![0-9]+$)(?![a-zA-Z]+$)[0-9A-Za-z]{6,18}$", flags=re.IGNORECASE)
        elif self.level == "char_english":
            re_str = r"^(?![0-9]+$)(?![a-z]+$)(?![A-Z]+$)(?!([^(0-9a-zA-Z)]|[\(\)])+$)" \
                     r"([^(0-9a-zA-Z)]|[\(\)]|[a-z]|[A-Z]|[0-9]){6,18}$"
            self.password_regex = lazy_re_compile(re_str, flags=re.IGNORECASE)

    def __call__(self, value):
        valid = self.password_regex.match(value)

        if not valid:
            raise ValidationError(self.message[self.level], code=self.code)

