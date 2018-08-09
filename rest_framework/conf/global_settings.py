# -*- coding: utf-8 -*-

# 是否调试模式
DEBUG = False
# 存表为时间区
TIME_ZONE = 'UTC'
# 显示的时间区
SHOW_TIME_ZONE = "UTC"

# 是否开启XSRF防护, 默认不开启
XSRF_COOKIES = False

# 缓存配置
CACHES = {
    "default": {
        "BACKEND": "rest_framework.core.cache.backend.simple",
        "LOCATION": "",
        "KEY_PREFIX": "",
        "DEFAULT_TIMEOUT": 300,  # 默认过期时间（秒）
        "OPTIONS": {
            "THRESHOLD": 500
        }
    }
}
# 语言
LANGUAGE_CODE = 'en_US'
LANGUAGE_DOMAIN = "messages"
LANGUAGE_PATHS = []
# 数据库配置
DATABASES = {}
# model迁移
INSTALLED_APPS = []

# 注册密码加密方式
PASSWORD_HASHERS = [
    'rest_framework.core.safe.hashers.PBKDF2PasswordHasher',
    # 'rest_framework.core.safe.hashers.PBKDF2SHA1PasswordHasher',
    # 'rest_framework.core.safe.hashers.Argon2PasswordHasher',
    # 'rest_framework.core.safe.hashers.BCryptSHA256PasswordHasher',
    # 'rest_framework.core.safe.hashers.BCryptPasswordHasher',
]
# 默认的字段异常
NON_FIELD_ERRORS = "__all__"
# 搜索框过滤类的参数变量名
SEARCH_PARAM = "search"
# 排序过滤类的参数变量名
ORDERING_PARAM = "ordering"

DATE_INPUT_FORMATS = [
    '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y',  # '2006-10-25', '10/25/2006', '10/25/06'
    '%b %d %Y', '%b %d, %Y',             # 'Oct 25 2006', 'Oct 25, 2006'
    '%d %b %Y', '%d %b, %Y',             # '25 Oct 2006', '25 Oct, 2006'
    '%B %d %Y', '%B %d, %Y',             # 'October 25 2006', 'October 25, 2006'
    '%d %B %Y', '%d %B, %Y',             # '25 October 2006', '25 October, 2006'
]

TIME_INPUT_FORMATS = [
    '%H:%M:%S',     # '14:30:59'
    '%H:%M:%S.%f',  # '14:30:59.000200'
    '%H:%M',        # '14:30'
]

DATETIME_INPUT_FORMATS = [
    '%Y-%m-%d %H:%M:%S',     # '2006-10-25 14:30:59'
    '%Y-%m-%d %H:%M:%S.%f',  # '2006-10-25 14:30:59.000200'
    '%Y-%m-%d %H:%M',        # '2006-10-25 14:30'
    '%Y-%m-%d',              # '2006-10-25'
    '%m/%d/%Y %H:%M:%S',     # '10/25/2006 14:30:59'
    '%m/%d/%Y %H:%M:%S.%f',  # '10/25/2006 14:30:59.000200'
    '%m/%d/%Y %H:%M',        # '10/25/2006 14:30'
    '%m/%d/%Y',              # '10/25/2006'
    '%m/%d/%y %H:%M:%S',     # '10/25/06 14:30:59'
    '%m/%d/%y %H:%M:%S.%f',  # '10/25/06 14:30:59.000200'
    '%m/%d/%y %H:%M',        # '10/25/06 14:30'
    '%m/%d/%y',              # '10/25/06'
]

LOGGING = {}
