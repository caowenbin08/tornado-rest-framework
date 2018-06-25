# -*- coding: utf-8 -*-
import os
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from rest_framework.core.exceptions import ValidationError
from rest_framework.utils.lazy import lazy_re_compile
from rest_framework.core.translation import lazy_translate as _
from rest_framework.utils.transcoder import force_text


class RegexValidator(object):
    regex = ''
    message = _('Enter a valid value')
    code = 'invalid'
    inverse_match = False
    flags = 0

    def __init__(self, regex=None, message=None, code=None, inverse_match=None, flags=None):
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
        """
        Validates that the input matches the regular expression
        if inverse_match is False, otherwise raises ValidationError.
        """
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


class URLValidator(RegexValidator):
    ul = '\u00a1-\uffff'  # unicode letters range (must be a unicode string, not a raw string)

    # IP patterns
    ipv4_re = r'(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|[0-1]?\d?\d)){3}'
    ipv6_re = r'\[[0-9a-f:\.]+\]'  # (simple regex, validated later)

    # Host patterns
    hostname_re = r'[a-z' + ul + r'0-9](?:[a-z' + ul + r'0-9-]{0,61}[a-z' + ul + r'0-9])?'
    # Max length for domain name labels is 63 characters per RFC 1034 sec. 3.1
    domain_re = r'(?:\.(?!-)[a-z' + ul + r'0-9-]{1,63}(?<!-))*'
    tld_re = (
        r'\.'                                # dot
        r'(?!-)'                             # can't start with a dash
        r'(?:[a-z' + ul + '-]{2,63}'         # domain label
        r'|xn--[a-z0-9]{1,59})'              # or punycode label
        r'(?<!-)'                            # can't end with a dash
        r'\.?'                               # may have a trailing dot
    )
    host_re = '(' + hostname_re + domain_re + tld_re + '|localhost)'

    regex = lazy_re_compile(
        r'^(?:[a-z0-9\.\-\+]*)://'  # scheme is validated separately
        r'(?:\S+(?::\S*)?@)?'  # user:pass authentication
        r'(?:' + ipv4_re + '|' + ipv6_re + '|' + host_re + ')'
        r'(?::\d{2,5})?'  # port
        r'(?:[/?#][^\s]*)?'  # resource path
        r'\Z', re.IGNORECASE)
    message = _('Enter a valid URL')
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

            # url = value

        # The maximum length of a full host name is 253 characters per RFC 1034
        # section 3.1. It's defined to be 255 bytes or less, but this includes
        # one byte for the length of the name and one byte for the trailing dot
        # that's used to indicate absolute names in DNS.
        if len(urlsplit(value).netloc) > 253:
            raise ValidationError(self.message, code=self.code)


integer_validator = RegexValidator(
    lazy_re_compile(r'^-?\d+\Z'),
    message=_('Enter a valid integer'),
    code='invalid',
)


def validate_integer(value):
    return integer_validator(value)


class EmailValidator(object):
    message = _('Enter a valid email address')
    code = 'invalid'
    user_regex = lazy_re_compile(
        r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*\Z"  # dot-atom
        r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])*"\Z)',  # quoted-string
        re.IGNORECASE)
    domain_regex = lazy_re_compile(
        # max length for domain name labels is 63 characters per RFC 1034
        r'((?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+)(?:[A-Z0-9-]{2,63}(?<!-))\Z',
        re.IGNORECASE)
    literal_regex = lazy_re_compile(
        # literal form, ipv4 or ipv6 address (SMTP 4.1.3)
        r'\[([A-f0-9:\.]+)\]\Z',
        re.IGNORECASE)
    domain_whitelist = ['localhost']

    def __init__(self, message=None, code=None, whitelist=None):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if whitelist is not None:
            self.domain_whitelist = whitelist

    def __call__(self, value):
        value = force_text(value)

        if not value or '@' not in value:
            raise ValidationError(self.message, code=self.code)

        user_part, domain_part = value.rsplit('@', 1)

        if not self.user_regex.match(user_part):
            raise ValidationError(self.message, code=self.code)

        if (domain_part not in self.domain_whitelist and
                not self.validate_domain_part(domain_part)):
            # Try for possible IDN domain-part
            try:
                domain_part = domain_part.encode('idna').decode('ascii')
                if self.validate_domain_part(domain_part):
                    return
            except UnicodeError:
                pass
            raise ValidationError(self.message, code=self.code)

    def validate_domain_part(self, domain_part):
        if self.domain_regex.match(domain_part):
            return True

        literal_match = self.literal_regex.match(domain_part)
        if literal_match:
            ip_address = literal_match.group(1)
            return IPAddressValidator.check_ipv4(ip_address) or IPAddressValidator.check_ipv6(ip_address)
        return False

    def __eq__(self, other):
        return (
            isinstance(other, EmailValidator) and
            (self.domain_whitelist == other.domain_whitelist) and
            (self.message == other.message) and
            (self.code == other.code)
        )


validate_email = EmailValidator()


class IPAddressValidator(object):
    """
    ipv4 或ipv6 地址是否合法
    """

    message = {
        "both": _('Enter a valid IPv4 or IPv6 address'),
        "ipv4": _('Enter a valid IPv4 address'),
        "ipv6": _('Enter a valid IPv6 address')
    }
    code = 'invalid'

    def __init__(self, protocol="both", message=None, code=None):
        self.protocol = protocol

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


class BaseValidator(object):
    message = _('Ensure this value is %(limit_value)s (it is %(show_value)s)')
    code = 'limit_value'

    def __init__(self, limit_value, message=None):
        self.limit_value = limit_value
        if message:
            self.message = message

    def __call__(self, value):
        cleaned = self.clean(value)
        params = {'limit_value': self.limit_value, 'show_value': cleaned, 'value': value}
        if self.compare(cleaned, self.limit_value):
            raise ValidationError(self.message, code=self.code, params=params)

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
    message = _('Ensure this value is less than or equal to %(limit_value)s')
    code = 'max_value'

    def compare(self, a, b):
        return a > b


class MinValueValidator(BaseValidator):
    message = _('Ensure this value is greater than or equal to %(limit_value)s')
    code = 'min_value'

    def compare(self, a, b):
        return a < b


class MinLengthValidator(BaseValidator):
    message = _('Ensure this value has at least %(limit_value)d character (it has %(show_value)d)')
    code = 'min_length'

    def compare(self, a, b):
        return a < b

    def clean(self, x):
        return len(x)


class MaxLengthValidator(BaseValidator):
    message = _('Ensure this value has at most %(limit_value)d character (it has %(show_value)d)')
    code = 'max_length'

    def compare(self, a, b):
        return a > b

    def clean(self, x):
        return len(x)


class DecimalValidator(object):
    """
    Validate that the input does not exceed the maximum number of digits
    expected, otherwise raise ValidationError.
    """
    messages = {
        'max_digits': _('Ensure that there are no more than %(max)s digit in total'),
        'max_decimal_places': _('Ensure that there are no more than %(max)s decimal place'),
        'max_whole_digits': _(
            'Ensure that there are no more than %(max)s digit before the decimal point'
        ),
    }

    def __init__(self, max_digits, decimal_places):
        self.max_digits = max_digits
        self.decimal_places = decimal_places

    def __call__(self, value):
        digit_tuple, exponent = value.as_tuple()[1:]
        decimals = abs(exponent)
        # digit_tuple doesn't include any leading zeros.
        digits = len(digit_tuple)
        if decimals > digits:
            # We have leading zeros up to or past the decimal point. Count
            # everything past the decimal point as a digit. We do not count
            # 0 before the decimal point as a digit since that would mean
            # we would not allow max_digits = decimal_places.
            digits = decimals
        whole_digits = digits - decimals

        if self.max_digits is not None and digits > self.max_digits:
            raise ValidationError(
                self.messages['max_digits'],
                code='max_digits',
                params={'max': self.max_digits},
            )
        if self.decimal_places is not None and decimals > self.decimal_places:
            raise ValidationError(
                self.messages['max_decimal_places'],
                code='max_decimal_places',
                params={'max': self.decimal_places},
            )
        if (self.max_digits is not None and self.decimal_places is not None and
                whole_digits > (self.max_digits - self.decimal_places)):
            raise ValidationError(
                self.messages['max_whole_digits'],
                code='max_whole_digits',
                params={'max': (self.max_digits - self.decimal_places)},
            )

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            self.max_digits == other.max_digits and
            self.decimal_places == other.decimal_places
        )


class FileExtensionValidator(object):
    message = _(
        "File extension '%(extension)s' is not allowed. "
        "Allowed extensions are: '%(allowed_extensions)s'."
    )
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
                self.message,
                code=self.code,
                params={
                    'extension': extension,
                    'allowed_extensions': ', '.join(self.allowed_extensions)
                }
            )

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and
            self.allowed_extensions == other.allowed_extensions and
            self.message == other.message and
            self.code == other.code
        )


class PasswordValidator(object):
    """
    密码是否合法
    """
    message = {
        "number": _("Enter a valid 6-digit password"),
        "normal": _("Enter a valid 6-18-digit alphanumeric password"),
        "high": _("Enter a 6-18 bit must contain any combination of "
                  "upper and lower case letters, numbers, symbols password")
    }
    code = 'invalid'

    def __init__(self, level="number", message=None, code=None, regex=None):
        self.level = level

        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

        self.password_regex = lazy_re_compile(regex, flags=re.IGNORECASE) \
            if regex is not None else None

        if self.level == "number":
            self.password_regex = lazy_re_compile(r"^\d{6}$", flags=re.IGNORECASE)
        elif self.level == "normal":
            self.password_regex = lazy_re_compile(r"^(?![0-9]+$)(?![a-zA-Z]+$)[0-9A-Za-z]{6,18}$",
                                                  flags=re.IGNORECASE)
        elif self.level == "high":
            re_str = r"^(?![0-9]+$)(?![a-z]+$)(?![A-Z]+$)(?!([^(0-9a-zA-Z\u4e00-\u9fa5\s)])+$)" \
                     r"([^(0-9a-zA-Z\u4e00-\u9fa5\s)]|[a-z]|[A-Z]|[0-9]){6,18}$"
            self.password_regex = lazy_re_compile(re_str, flags=re.IGNORECASE)

    def __call__(self, value):
        if self.level == "any" or self.password_regex is None:
            return

        valid = self.password_regex.match(value)

        if not valid:
            raise ValidationError(self.message[self.level], code=self.code)


class PhoneValidator(object):
    """
    手机号码检查
    移动号段：
    134 135 136 137 138 139 147 148 150 151 152 157 158 159 172 178 182 183 184 187 188 198
    联通号段：
    130 131 132 145 146 155 156 166 171 175 176 185 186
    电信号段：
    133 149 153 173 174 177 180 181 189 199
    虚拟运营商:
    170
    2017-08-08：工信部新批号段：电信199/移动198/联通166 ，146联通，148移动

    精准的匹配：^(13[0-9]|14[5-9]|15[0-9]|16[6]|17[0-8]|18[0-9]|19[8-9])\d{8}$
    粗准匹配：^1(3|4|5|7|8|9)[0-9]{9}$
    """
    message = _("Enter a valid phone number")
    code = 'invalid'
    phone_regex = lazy_re_compile(
        r"^(13[0-9]|14[5-9]|15[0-9]|16[6]|17[0-8]|18[0-9]|19[8-9])\d{8}$",
        flags=re.IGNORECASE
    )

    def __init__(self, message=None, code=None):
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

    def __call__(self, value):
        value = force_text(value)

        if not value or not value.isdigit():
            raise ValidationError(self.message, code=self.code)

        if not self.phone_regex.match(value):
            raise ValidationError(self.message, code=self.code)

validate_phone = PhoneValidator()


class IdentifierValidator(object):
    """
    手机号码或邮箱地址是否合法
    """

    message = {
        "both": _("Enter a valid phone number or email address"),
        "phone": _("Enter a valid phone number"),
        "email": _("Enter a valid email address")
    }
    code = 'invalid'

    def __init__(self, protocol="both", message=None, code=None):
        self.protocol = protocol
        # assert isinstance(message, (type(None), dict)), "message值必须为字典类型"
        if message is not None:
            self.message = message

        if code is not None:
            self.code = code

    def __call__(self, value):
        if not value:
            raise ValidationError(self.message[self.protocol], code=self.code)

        if self.protocol == "both":
            if "@" in value:
                validate_email(value)
            elif value.isdigit():
                validate_phone(value)
            else:
                raise ValidationError(self.message[self.protocol], code=self.code)

        elif self.protocol == "email":
            validate_email(value)

        elif self.protocol == "phone":
            validate_phone(value)
