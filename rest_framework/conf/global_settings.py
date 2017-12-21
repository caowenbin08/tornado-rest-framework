# -*- coding: utf-8 -*-

__author__ = 'caowenbin'

# 是否调试模式
DEBUG = False

# 是否开启XSRF防护, 默认不开启
XSRF_COOKIES = False

# 缓存配置
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
# 语言
LANGUAGE_CODE = 'en_US'
LANGUAGE_PATHS = []
# BABEL_DEFAULT_LOCALE = "en"
# BABEL_DEFAULT_TIMEZONE = "UTC"
# 数据库配置
DATABASES = {}
# model迁移
INSTALLED_APPS = []
# 解析
PARSER_CLASSES = (
    'rest_framework.core.parsers.JSONParser',
    'rest_framework.core.parsers.FormParser',
    'rest_framework.core.parsers.MultiPartParser'
)
# 注册密码加密方式
PASSWORD_HASHERS = [
    'rest_framework.core.safe.hashers.PBKDF2PasswordHasher',
    'rest_framework.core.safe.hashers.PBKDF2SHA1PasswordHasher',
    'rest_framework.core.safe.hashers.Argon2PasswordHasher',
    'rest_framework.core.safe.hashers.BCryptSHA256PasswordHasher',
    'rest_framework.core.safe.hashers.BCryptPasswordHasher',
]
# 默认的字段异常key
FIELD_ERRORS_KEY = "error_msg"
# 搜索框过滤类的参数变量名
SEARCH_PARAM = "search"
# 排序过滤类的参数变量名
ORDERING_PARAM = "ordering"
# 分页配置
PAGINATION = {
    # 页码分页模式
    "page_number": {
        # 默认分页列表条目数
        "page_size": 10,
        # 默认最大的列表条目数, 默认不限制
        "max_page_size": None,
        # 默认页码参数变量名
        "page_query_param": "page",
        # 默认页面记录大小参数变量名
        "page_size_query_param": None,
        # 默认可以作为第一页码的字符串集合
        "first_page_strings": ('first',),
        # 默认可以作为最后页码的字符串集合
        "last_page_strings": ('last',),
        # 当页码超过总页码时，是否允许返回空列表，True代表可以，False代表抛出APIException异常
        "allow_empty_page": True,
        # 当页码值小于1时，是否允许直接转为1返回第一页的数据，反之抛出APIException异常；True可以，False不可以
        "allow_first_page": True,
        # 当页码超过总页码时，是否允许返回最后一页的数据列表 True代表可以，False代表不处理
        "allow_last_page": True,
    },
    # limit分页模式
    "limit_offset": {
        # 默认分页列表条目数
        "default_limit": 10,
        # 默认最大的列表条目数, 默认不限制
        "max_limit": None,
        "limit_query_param": 'limit',
        "offset_query_param": 'offset'
    }
}
