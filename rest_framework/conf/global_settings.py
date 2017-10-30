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

# 分页记录量
PAGE_SIZE = 10

# 数据库配置
DATABASES = {}
# model迁移
INSTALLED_APPS = []
# 密码加密方式
PASSWORD_HASHERS = [
    'rest_framework.helpers.hashers.PBKDF2PasswordHasher',
    'rest_framework.helpers.hashers.PBKDF2SHA1PasswordHasher',
    'rest_framework.helpers.hashers.Argon2PasswordHasher',
    'rest_framework.helpers.hashers.BCryptSHA256PasswordHasher',
    'rest_framework.helpers.hashers.BCryptPasswordHasher',
]
# 默认的字段异常key
FIELD_ERRORS_KEY = "field_errors"
